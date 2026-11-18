"""Razorpay architecture (no extra packages needed).

Flow
 1. checkout   -> we create an Order (payment_status='unpaid') and a Razorpay
                  order for the ADVANCE amount only. Prices come from the DB.
 2. pay page   -> browser opens Razorpay Checkout with that order_id.
 3. callback   -> browser posts payment_id + signature to /payment/verify/.
                  We verify the HMAC signature on the server, mark the order
                  'paid' and show the token.
 4. webhook    -> Razorpay also calls /payment/webhook/ (payment.captured /
                  order.paid). This marks the order paid even if the customer
                  closed the tab after paying. Both paths are idempotent.
"""
import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Order

logger = logging.getLogger(__name__)

API_URL = 'https://api.razorpay.com/v1/orders'
REFUND_API_URL = 'https://api.razorpay.com/v1/payments/{}/refund'


class PaymentError(Exception):
    pass


def keys_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def to_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def advance_for(total, percent):
    return (Decimal(total) * percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _auth_header():
    auth = base64.b64encode(
        f'{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}'.encode()
    ).decode()
    return {'Content-Type': 'application/json', 'Authorization': f'Basic {auth}'}


def _post(url, payload, idempotency_key=None):
    headers = _auth_header()
    if idempotency_key:
        # Razorpay dedupes retried refund/order calls that reuse this header,
        # so a network timeout followed by our own retry never double-charges
        # or double-refunds the customer.
        headers['X-Razorpay-Idempotency'] = idempotency_key
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PaymentError(str(exc)) from exc


def create_order(order):
    """Create a Razorpay order for the order's advance amount. Returns the JSON."""
    return _post(API_URL, {
        'amount': to_paise(order.advance_amount),
        'currency': 'INR',
        'receipt': f'ehomely-{order.pk}',
        'notes': {'order_pk': str(order.pk), 'name': order.name[:40]},
    })


def create_refund(payment_id, amount_paise, idempotency_key):
    """Refund (part of) a captured payment. Returns the Razorpay refund JSON."""
    return _post(REFUND_API_URL.format(payment_id), {
        'amount': amount_paise,
        'speed': 'optimum',
        'notes': {'reason': 'order cancelled'},
    }, idempotency_key=idempotency_key)


def _hmac(secret, message):
    # message must be bytes for hmac.new(). Coerce here so callers that pass
    # a plain str (e.g. verify_signature before the .encode() was added) never
    # crash with a TypeError and silently fail to verify payment signatures.
    if isinstance(message, str):
        message = message.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(rzp_order_id, payment_id, signature):
    if not (rzp_order_id and payment_id and signature and settings.RAZORPAY_KEY_SECRET):
        return False
    expected = _hmac(settings.RAZORPAY_KEY_SECRET, f'{rzp_order_id}|{payment_id}'.encode())
    return hmac.compare_digest(expected, signature)


def verify_webhook(body, signature):
    if not (signature and settings.RAZORPAY_WEBHOOK_SECRET):
        return False
    return hmac.compare_digest(_hmac(settings.RAZORPAY_WEBHOOK_SECRET, body), signature)


def refund_order(order):
    """Refund the advance paid for `order`, if it has one coming.

    Safe to call more than once (idempotent): a non-paid or already-refunded
    order is left untouched. Returns True once the order is in state
    'refunded' (whether this call did the work or it was already done),
    False if a refund is owed but could not be completed right now (e.g. the
    Razorpay API is unreachable) - callers should let staff retry later via
    the manual "Refund" action rather than losing track of the money owed.
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().filter(pk=order.pk).first()
        if locked is None:
            return False
        if locked.payment_status == 'refunded':
            return True
        if locked.payment_status != 'paid':
            return False   # nothing was ever charged - nothing to give back

        if not keys_configured():
            # Dev "test mode": no real payment was taken, so just flip the
            # status so the rest of the app (daily limits, the token page)
            # treats the advance as given back.
            locked.payment_status = 'refunded'
            locked.refunded_at = timezone.now()
            locked.save(update_fields=['payment_status', 'refunded_at'])
            return True

        try:
            resp = create_refund(
                locked.razorpay_payment_id,
                to_paise(locked.advance_amount),
                idempotency_key=f'ehomely-refund-{locked.pk}',
            )
        except PaymentError:
            logger.exception('refund_order: Razorpay refund failed for order %s (pk=%s)',
                             locked.order_no, locked.pk)
            return False

        locked.payment_status = 'refunded'
        locked.razorpay_refund_id = resp.get('id', '')
        locked.refunded_at = timezone.now()
        locked.save(update_fields=['payment_status', 'razorpay_refund_id', 'refunded_at'])
        return True


def mark_paid(rzp_order_id, payment_id, amount_paise=None):
    """Mark the order paid. Safe to call twice. Returns the order or None."""
    import logging
    logger = logging.getLogger(__name__)
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(razorpay_order_id=rzp_order_id).first()
        if order is None:
            logger.warning('mark_paid: unknown razorpay_order_id %s', rzp_order_id)
            return None
        if amount_paise is not None and amount_paise != to_paise(order.advance_amount):
            logger.error(
                'mark_paid: amount mismatch for order %s (pk=%s): '
                'expected %s paise, got %s paise — order NOT marked paid',
                rzp_order_id, order.pk, to_paise(order.advance_amount), amount_paise,
            )
            return None
        if order.payment_status != 'paid':
            order.payment_status = 'paid'
            order.razorpay_payment_id = payment_id
            order.paid_at = timezone.now()
            order.save(update_fields=['payment_status', 'razorpay_payment_id', 'paid_at'])
        return order
