import json
from datetime import datetime, timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required as _staff_member_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from . import payments
from .models import OPEN_STATUSES, Dish, Order, OrderItem, SiteSetting
from .ui import render_ui

# A customer may cancel only before the kitchen starts cooking.
CANCELLABLE = ['new', 'out_of_stock']

MEAL_INFO = {
    'breakfast': {'label': 'Breakfast', 'start': '07:00', 'end': '10:30',
                  'blurb': 'Hot and filling, quick before class.'},
    'lunch': {'label': 'Lunch', 'start': '12:00', 'end': '15:00',
              'blurb': 'The main meal of the day, packed fresh.'},
    'dinner': {'label': 'Dinner', 'start': '19:00', 'end': '22:00',
               'blurb': 'Comfort food to end the day.'},
}


# ---------------------------------------------------------------- helpers
def nice_time(hhmm):
    return datetime.strptime(hhmm, '%H:%M').strftime('%I:%M %p').lstrip('0')


def meal_list():
    return [
        {**info, 'key': key,
         'start_label': nice_time(info['start']),
         'end_label': nice_time(info['end'])}
        for key, info in MEAL_INFO.items()
    ]


def to_minutes(hhmm):
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)


def meal_state(key):
    # 'open' = serving now, 'later' = starts later today, 'closed' = finished for today.
    now = timezone.localtime()
    cur = now.hour * 60 + now.minute
    info = MEAL_INFO[key]
    if to_minutes(info['start']) <= cur < to_minutes(info['end']):
        return 'open'
    return 'later' if cur < to_minutes(info['start']) else 'closed'


def for_tomorrow(key):
    """True once today's window for this meal has passed: new orders are pre-orders for tomorrow."""
    return meal_state(key) == 'closed'


def pickup_date(key):
    today = timezone.localdate()
    return today + timedelta(days=1) if for_tomorrow(key) else today


def cart_meal(lines):
    """Return the meal key that all dishes in this cart belong to, or None if mixed/empty."""
    meals = {Dish.objects.filter(pk=l['dish_id']).values_list('meal', flat=True).first() for l in lines}
    meals.discard(None)
    return meals.pop() if len(meals) == 1 else None


def limit_errors(lines):
    """Return a list of error strings for dishes that have hit their daily cap."""
    errors = []
    today = timezone.localdate()
    for line in lines:
        dish = Dish.objects.filter(pk=line['dish_id']).first()
        if not dish or not dish.daily_limit:
            continue
        already = (OrderItem.objects
                   .filter(dish=dish, order__payment_status='paid', order__created__date=today)
                   .exclude(order__status='cancelled')
                   .values_list('quantity', flat=True))
        sold_today = sum(already)
        remaining = dish.daily_limit - sold_today
        if remaining <= 0:
            errors.append(f'{dish.name} is sold out for today (daily limit reached).')
        elif line['qty'] > remaining:
            errors.append(f'Only {remaining} portion(s) of {dish.name} left today.')
    return errors


def clean_phone(raw):
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    elif len(digits) > 10 and digits.startswith('91'):
        digits = digits[-10:]
    return digits if len(digits) == 10 else None


def advance_options():
    # Force full payment (100%) – no advance options
    return [100]


def grant(request, pk):
    """Remember in the browser session that this visitor owns order pk."""
    ids = request.session.get('orders', [])
    if pk not in ids:
        ids.append(pk)
        request.session['orders'] = ids


def owns(request, pk):
    return pk in request.session.get('orders', [])


# Orders this browser has started checking out but not yet been shown the token
# for. A list (not a single id) so a second checkout, a second tab or the Back
# button does not invalidate the first pay page.
PENDING_LIMIT = 5


def remember_pending(request, pk):
    ids = [i for i in request.session.get('pay_orders', []) if i != pk]
    ids.append(pk)
    request.session['pay_orders'] = ids[-PENDING_LIMIT:]


def is_pending(request, pk):
    return (pk in request.session.get('pay_orders', [])
            or request.session.get('pay_order') == pk)   # sessions from before this change


def forget_pending(request, pk):
    request.session['pay_orders'] = [i for i in request.session.get('pay_orders', []) if i != pk]
    if request.session.get('pay_order') == pk:
        request.session.pop('pay_order')


def claim(request, pk):
    """May this browser see the token for PAID order pk?

    Yes if it already owns it, or if it is the browser that started the checkout.
    The second case matters when the payment was confirmed by Razorpay's webhook
    (UPI app switch, closed tab, lost callback) instead of this browser's callback."""
    if owns(request, pk):
        return True
    if is_pending(request, pk):
        grant(request, pk)
        forget_pending(request, pk)
        return True
    return False


# ---------------------------------------------------------------- menu pages

def welcome(request):
    # Landing splash is now the first section of home.html, so scrolling
    # continues straight into the live homepage. Same view as menu(), plus
    # the flag that turns the splash section on.
    return render_ui(request, 'home.html', {
        'meals': meal_list(),
        'accepting': SiteSetting.load().accepting_orders,
        'advance_text': ' or '.join(f'{p}%' for p in advance_options()),
        'show_landing': True,
    })


def menu(request):
    return render_ui(request, 'home.html', {
        'meals': meal_list(),
        'accepting': SiteSetting.load().accepting_orders,
        'advance_text': ' or '.join(f'{p}%' for p in advance_options()),
        # Home button/nav land here too — keep show_landing on so the
        # landing splash stays in the page and scroll-up still reaches it.
        'show_landing': True,
    })

def about(request):
    return render_ui(request, 'about.html', {})

def location(request):
    return render_ui(request, 'location.html', {})


def meal_menu(request, meal):
    if meal not in MEAL_INFO:
        raise Http404
    info = next(m for m in meal_list() if m['key'] == meal)
    dishes = Dish.objects.filter(meal=meal).order_by('category', 'name')
    state = meal_state(meal)
    return render_ui(request, 'menu.html', {
        'dishes': dishes,
        'meal': info,
        'meals': meal_list(),
        'accepting': SiteSetting.load().accepting_orders,
        'serving': state == 'open',
        'for_tomorrow': state == 'closed',
        'state_label': {
            'open': 'Serving now',
            'later': 'Starts later today',
            'closed': 'Pre-order for tomorrow',
        }[state],
    })


def stock_json(request):
    dishes = Dish.objects.order_by('category', 'name')
    return JsonResponse({'dishes': [
        {'id': d.id, 'name': d.name, 'meal': d.meal, 'category': d.category,
         'price': str(d.price), 'available': d.is_available}
        for d in dishes
    ]})


# ---------------------------------------------------------------- checkout
def parse_cart(raw):
    # Prices always come from the database, never from the browser.
    try:
        cart = json.loads(raw)
    except ValueError:
        return [], Decimal('0'), []
    if not isinstance(cart, dict):
        return [], Decimal('0'), []

    lines, total, sold_out = [], Decimal('0'), []
    for dish_id, qty in cart.items():
        try:
            qty = int(qty)
            dish = Dish.objects.get(pk=int(dish_id))
        except (ValueError, TypeError, Dish.DoesNotExist):
            continue
        if not 1 <= qty <= 20:
            continue
        if not dish.is_available:
            sold_out.append(dish.name)
            continue
        lines.append({'dish_id': dish.id, 'name': dish.name, 'qty': qty, 'price': str(dish.price)})
        total += dish.price * qty
    return lines, total, sold_out


def render_checkout(request, error=None, name='', phone='', existing_orders=None, meal_window=None):
    dishes = [
        {'id': d.id, 'name': d.name, 'price': str(d.price), 'image': ''}
        for d in Dish.objects.all()
    ]
    # Pass meal window info so the page can tell the customer when to collect.
    meal_info = MEAL_INFO.get(meal_window) if meal_window else None
    if meal_info:
        meal_label = meal_info['label']
        meal_time = f"{nice_time(meal_info['start'])} – {nice_time(meal_info['end'])}"
        meal_state_val = meal_state(meal_window)
    else:
        meal_label = meal_time = meal_state_val = None

    return render_ui(request, 'checkout.html', {
        'error': error,
        'dishes': dishes,
        'advance_options': advance_options(),
        'name': name,
        'phone': phone,
        'existing_orders': existing_orders or [],
        'meal_label': meal_label,
        'meal_time': meal_time,
        'meal_state': meal_state_val,
    })


def checkout_error(request, error, name='', phone='', meal_window=None, show_existing=False):
    """Post/Redirect/Get for form errors.

    Re-rendering the page straight from the POST makes the browser's Back and
    Forward buttons show a "Confirm form resubmission" prompt (or re-send the
    order). Instead we remember the message for one page view and redirect to
    the normal GET page, so history stays clean and Back always works."""
    request.session['checkout_flash'] = {
        'error': error, 'name': name, 'phone': phone,
        'meal_window': meal_window, 'show_existing': show_existing,
    }
    return redirect('checkout')


def checkout(request):
    if not SiteSetting.load().accepting_orders:
        return redirect('menu')
    if request.method != 'POST':
        flash = request.session.pop('checkout_flash', None) or {}
        # Show reminder if this browser already has open orders.
        owned_pks = request.session.get('orders', [])
        existing = list(
            Order.objects.filter(pk__in=owned_pks, payment_status='paid', status__in=OPEN_STATUSES)
                         .order_by('created')
        ) if owned_pks else []
        if flash.get('show_existing') and clean_phone(flash.get('phone', '')):
            existing = list(
                Order.objects.filter(phone=clean_phone(flash['phone']), payment_status='paid',
                                     status__in=OPEN_STATUSES).order_by('created')
            )
        return render_checkout(request, flash.get('error'), name=flash.get('name', ''),
                               phone=flash.get('phone', ''), existing_orders=existing,
                               meal_window=flash.get('meal_window'))

    name = request.POST.get('name', '').strip()[:100]
    raw_phone = request.POST.get('phone', '')
    phone = clean_phone(raw_phone)
    lines, total, sold_out = parse_cart(request.POST.get('cart', '{}'))

    percent = 100  # always full payment online

    if sold_out:
        return checkout_error(request, 'Sorry, just sold out: ' + ', '.join(sold_out)
                              + '. Go back to the menu and remove it.', name=name, phone=raw_phone)

    if not (name and phone and lines):
        return checkout_error(request, 'Add a dish and enter a valid name and 10-digit phone number.',
                              name=name, phone=raw_phone)

    # All dishes in a cart must belong to the same meal.
    meal_key = cart_meal(lines)
    if not meal_key:
        return checkout_error(request, 'Your cart has dishes from different meal times. '
                              'Please order one meal at a time.', name=name, phone=raw_phone)

    # Daily limit check (e.g. Biriyani / Meals capped at 75).
    cap_errors = limit_errors(lines)
    if cap_errors:
        return checkout_error(request, ' '.join(cap_errors), name=name, phone=raw_phone,
                              meal_window=meal_key)

    # Existing open orders for this phone — block at 2, warn at 1.
    existing = list(
        Order.objects.filter(phone=phone, payment_status='paid', status__in=OPEN_STATUSES)
                     .order_by('created')
    )
    if len(existing) >= 2:
        return checkout_error(request,
                              'You already have 2 open orders. Please pick those up or cancel one first.',
                              name=name, phone=raw_phone, meal_window=meal_key, show_existing=True)

    if not payments.keys_configured() and not settings.ALLOW_FAKE_PAYMENTS:
        return checkout_error(request, 'Online payment is not set up yet. Please ask at the counter.',
                              name=name, phone=raw_phone)

    # Tidy up abandoned, never-paid orders.
    Order.objects.filter(payment_status='unpaid',
                         created__lt=timezone.now() - timedelta(hours=2)).delete()

    with transaction.atomic():
        order = Order.objects.create(
            name=name, phone=phone, total=total,
            meal=meal_key,
            for_date=pickup_date(meal_key),
            advance_percent=percent,
            advance_amount=payments.advance_for(total, percent),
        )
        for line in lines:
            OrderItem.objects.create(order=order, dish_id=line['dish_id'],
                                     quantity=line['qty'], price=Decimal(line['price']))

    if payments.keys_configured():
        try:
            rzp = payments.create_order(order)
        except payments.PaymentError:
            order.delete()
            return checkout_error(request, 'We could not start the payment. '
                                  'Please try again in a minute.', name=name, phone=raw_phone)
        order.razorpay_order_id = rzp['id']
    else:  # fake-pay path (ALLOW_FAKE_PAYMENTS)
        order.razorpay_order_id = f'demo_{order.pk}'
    order.save(update_fields=['razorpay_order_id'])

    remember_pending(request, order.pk)
    return redirect('pay', pk=order.pk)


# ---------------------------------------------------------------- payment
@never_cache
def pay(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.payment_status == 'paid':
        # Already paid (maybe by webhook): go straight to the token.
        if claim(request, pk):
            return redirect('order_done', pk=pk)
        raise Http404
    if not is_pending(request, pk) or order.payment_status != 'unpaid':
        raise Http404
    return render_ui(request, 'pay.html', {
        'order': order,
        'key_id': settings.RAZORPAY_KEY_ID,
        'amount_paise': payments.to_paise(order.advance_amount),
        'demo': not payments.keys_configured(),
        'failed': request.GET.get('failed') == '1',
    })


@require_POST
def payment_verify(request):
    rzp_order_id = request.POST.get('razorpay_order_id', '')
    payment_id = request.POST.get('razorpay_payment_id', '')
    signature = request.POST.get('razorpay_signature', '')

    order = Order.objects.filter(razorpay_order_id=rzp_order_id).first()
    if order is None:
        raise Http404
    if not payments.verify_signature(rzp_order_id, payment_id, signature):
        if order.payment_status == 'paid' and claim(request, order.pk):
            return redirect('order_done', pk=order.pk)      # webhook got there first
        if is_pending(request, order.pk):
            return redirect(reverse('pay', args=[order.pk]) + '?failed=1')
        return redirect('checkout')

    payments.mark_paid(rzp_order_id, payment_id)
    grant(request, order.pk)
    forget_pending(request, order.pk)
    return redirect('order_done', pk=order.pk)


@require_POST
def payment_demo(request, pk):
    # Fake-pay path. Never works with real keys configured, or with
    # ALLOW_FAKE_PAYMENTS off.
    if payments.keys_configured() or not settings.ALLOW_FAKE_PAYMENTS:
        raise Http404
    order = get_object_or_404(Order, pk=pk)
    if not is_pending(request, pk):
        raise Http404
    payments.mark_paid(order.razorpay_order_id, f'demo_pay_{pk}')
    grant(request, pk)
    forget_pending(request, pk)
    return redirect('order_done', pk=pk)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    if not payments.verify_webhook(request.body, request.headers.get('X-Razorpay-Signature', '')):
        return HttpResponseBadRequest('bad signature')
    try:
        event = json.loads(request.body)
        if event.get('event') in ('payment.captured', 'order.paid'):
            entity = event['payload']['payment']['entity']
            payments.mark_paid(entity['order_id'], entity['id'], entity.get('amount'))
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest('bad payload')
    return HttpResponse('ok')


# ---------------------------------------------------------------- token page
def order_done(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.payment_status not in ('paid', 'refunded'):
        if order.payment_status == 'unpaid' and is_pending(request, pk):
            return redirect('pay', pk=pk)
        raise Http404
    if not claim(request, pk):
        raise Http404
    # Render token page instead of done.html
    meal_info = MEAL_INFO.get(order.meal, {})
    return render_ui(request, 'token.html', {
        'order': order,
        'items': order.items.select_related('dish'),
        'can_cancel': order.status in CANCELLABLE,
        'refunded': order.payment_status == 'refunded',
        'meal_label': meal_info.get('label', ''),
        'meal_start': nice_time(meal_info['start']) if meal_info else '',
        'meal_end': nice_time(meal_info['end']) if meal_info else '',
        'meal_state': ('later' if order.for_date and order.for_date > timezone.localdate() else meal_state(order.meal)) if order.meal else '',
        'for_tomorrow': bool(order.for_date and order.for_date > timezone.localdate()),
    })


def order_status(request, pk):
    # Polled by the token page every few seconds. 'refunded' is included
    # alongside 'paid' here because cancelling a paid order refunds it
    # (see cancel_order / payments.refund_order) - the token page still
    # needs to keep polling (and show the refund) after that happens.
    order = get_object_or_404(Order, pk=pk)
    if order.payment_status not in ('paid', 'refunded') or not claim(request, pk):
        raise Http404
    return JsonResponse({
        'status': order.status,
        'label': order.get_status_display(),
        'can_cancel': order.status in CANCELLABLE,
        'refunded': order.payment_status == 'refunded',
    })


@require_POST
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.payment_status != 'paid' or not claim(request, pk):
        raise Http404
    updated = Order.objects.filter(pk=pk, status__in=CANCELLABLE).update(status='cancelled')
    if updated:
        # Give the advance back. If Razorpay can't be reached right now this
        # returns False but the order stays cancelled - staff can retry the
        # refund from the kitchen dashboard, nothing is lost track of.
        payments.refund_order(order)
    return redirect('order_done', pk=pk)


# ---------------------------------------------------------------- staff
# Not signed in (or not staff) -> our own login page, not the stock Django admin one.
staff_member_required = _staff_member_required(login_url='staff_login')

@staff_member_required
def staff_orders(request):
    return render(request, 'orders/staff.html')


@staff_member_required
def staff_orders_json(request):
    # Only paid orders reach the kitchen. Tokens never expire, so every open
    # paid order shows until it is picked up or cancelled. A cancelled order
    # whose advance could not be auto-refunded (Razorpay unreachable at the
    # time) also stays visible here, still marked 'paid', so staff can see
    # it owes a refund and retry it - it would otherwise vanish from view
    # the moment it's cancelled.
    orders = (
        Order.objects
        .filter(Q(status__in=OPEN_STATUSES) | Q(status='cancelled'), payment_status='paid')
        .prefetch_related('items__dish')
        .order_by('created')
    )
    data = []
    today = timezone.localdate()
    for o in orders:
        meal_info = MEAL_INFO.get(o.meal, {})
        data.append({
            'id': o.id,
            'order_no': o.order_no,
            'name': o.name,
            'phone': o.phone,
            'meal': o.meal,
            'meal_label': meal_info.get('label', ''),
            'is_tomorrow': bool(o.for_date and o.for_date > today),
            'for_date': o.for_date.strftime('%a %d %b') if o.for_date else '',
            'status': o.status,
            'status_label': o.get_status_display(),
            'payment_status': o.payment_status,
            'note': o.note,
            'total': str(o.total),
            'paid': str(o.advance_amount),
            'balance': str(o.balance),
            'time': timezone.localtime(o.created).strftime('%I:%M %p').lstrip('0'),
            'items': [
                {'text': f'{i.quantity} x {i.dish.name}', 'sold_out': not i.dish.is_available}
                for i in o.items.all()
            ],
        })
    return JsonResponse({'orders': data})


@staff_member_required
@require_POST
def set_status(request, pk):
    status = request.POST.get('status')
    if status not in dict(Order.STATUS):
        return JsonResponse({'ok': True})
    updated = Order.objects.filter(pk=pk).update(status=status)
    if updated and status == 'cancelled':
        # Staff cancelling (e.g. a dish went out of stock) owes the advance
        # back too, same as a customer cancelling their own order.
        order = Order.objects.filter(pk=pk).first()
        if order:
            payments.refund_order(order)
    return JsonResponse({'ok': True})


@staff_member_required
@require_POST
def refund_order_view(request, pk):
    # Manual/retry button for the kitchen dashboard: used when an automatic
    # refund-on-cancel above couldn't reach Razorpay, or for any other order
    # that is cancelled but still shows as paid.
    order = get_object_or_404(Order, pk=pk)
    ok = payments.refund_order(order)
    order.refresh_from_db(fields=['payment_status'])
    return JsonResponse({'ok': ok, 'payment_status': order.payment_status})


@staff_member_required
def staff_menu(request):
    current = next((m['key'] for m in meal_list() if meal_state(m['key']) == 'open'), 'lunch')
    return render(request, 'orders/staff_menu.html', {'meals': meal_list(), 'current_meal': current})


@staff_member_required
@require_POST
def set_stock(request, pk):
    available = request.POST.get('available') == '1'
    Dish.objects.filter(pk=pk).update(is_available=available)
    return JsonResponse({'ok': True})


@staff_member_required
@require_POST
def add_dish(request):
    name = request.POST.get('name', '').strip()[:100]
    category = request.POST.get('category', '').strip()[:50]
    meal = request.POST.get('meal', '')
    price = request.POST.get('price', '').strip()
    image = request.FILES.get('image')

    if not (name and category and meal in dict(Dish.MEALS) and price):
        return JsonResponse({'ok': False, 'error': 'All fields required.'}, status=400)

    try:
        price = Decimal(price)
        if price <= 0:
            raise ValueError
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid price.'}, status=400)

    dish = Dish.objects.create(
        name=name, category=category, meal=meal, price=price, is_available=True
    )
    if image:
        dish.image = image
        dish.save(update_fields=['image'])

    return JsonResponse({'ok': True, 'id': dish.id, 'name': dish.name})
