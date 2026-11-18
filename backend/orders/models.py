import random
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Open = not collected and not cancelled yet. Tokens never expire, so an order
# stays open until staff mark it picked up or cancelled.
OPEN_STATUSES = ['new', 'preparing', 'ready', 'out_of_stock']

# Dish photos uploaded in the admin are shrunk to this size and saved as WebP,
# so a 5 MB phone photo never ends up on the server.
DISH_IMAGE_MAX_PX = 800
DISH_IMAGE_QUALITY = 80


def _shrink_image(field_file):
    """Return (name, ContentFile) with a resized WebP copy, or None if the file
    can't be read as an image (then it is saved untouched)."""
    from PIL import Image
    try:
        field_file.file.seek(0)
        im = Image.open(field_file.file)
        im.load()
    except Exception:
        return None
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert('RGB')
    im.thumbnail((DISH_IMAGE_MAX_PX, DISH_IMAGE_MAX_PX))
    buf = BytesIO()
    im.save(buf, 'WEBP', quality=DISH_IMAGE_QUALITY, method=6)
    return Path(field_file.name).stem + '.webp', ContentFile(buf.getvalue())


class Dish(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=7, decimal_places=2)
    is_available = models.BooleanField(default=True)
    MEALS = [('breakfast', 'Breakfast'), ('lunch', 'Lunch'), ('dinner', 'Dinner')]
    meal = models.CharField(max_length=10, choices=MEALS, default='lunch')
    image = models.ImageField(upload_to='dishes/', blank=True)
    # 0 means no limit. Set to e.g. 75 for Biriyani/Meals to cap daily orders.
    daily_limit = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Only a freshly uploaded file needs shrinking (not one already stored).
        if self.image and not getattr(self.image, '_committed', True):
            result = _shrink_image(self.image)
            if result:
                name, content = result
                self.image.save(name, content, save=False)
        super().save(*args, **kwargs)


class Order(models.Model):
    STATUS = [
        ('new', 'New'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('picked_up', 'Picked up'),
        ('out_of_stock', 'Out of stock'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT = [('unpaid', 'Unpaid'), ('paid', 'Paid'), ('refunded', 'Refunded')]

    MEALS = [('breakfast', 'Breakfast'), ('lunch', 'Lunch'), ('dinner', 'Dinner')]

    order_no = models.CharField(max_length=4, editable=False, unique=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    meal = models.CharField(max_length=10, choices=MEALS, default='lunch')
    status = models.CharField(max_length=12, choices=STATUS, default='new')
    note = models.CharField(max_length=200, blank=True)
    total = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)
    # Day the food is to be collected. Set at checkout: tomorrow when the meal's
    # window has already passed today (a pre-order for tomorrow). NULL on old orders.
    for_date = models.DateField(null=True, blank=True)

    # Payment: the customer pays an advance online (Razorpay), the rest at the counter.
    payment_status = models.CharField(max_length=10, choices=PAYMENT, default='unpaid')
    advance_percent = models.PositiveSmallIntegerField(default=0)
    advance_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    razorpay_order_id = models.CharField(max_length=40, blank=True, default='', db_index=True)
    razorpay_payment_id = models.CharField(max_length=40, blank=True, default='')
    razorpay_refund_id = models.CharField(max_length=40, blank=True, default='')
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    @property
    def balance(self):
        """What the customer still pays at the counter (never negative)."""
        return max(Decimal('0'), self.total - self.advance_amount)

    def save(self, *args, **kwargs):
        if not self.order_no:
            # Random 4-digit token, unique among today's orders and every order
            # that is still open (tokens do not expire).
            # select_for_update() locks matching rows so concurrent checkouts
            # cannot both pick the same code (unique=True on the field is the
            # last-resort guard; this loop avoids relying on the IntegrityError).
            today = timezone.localdate()
            from django.db import transaction
            with transaction.atomic():
                while True:
                    code = str(random.randint(1000, 9999))
                    clash = (Order.objects
                             .select_for_update()
                             .filter(order_no=code)
                             .filter(Q(created__date=today) | Q(status__in=OPEN_STATUSES))
                             .exists())
                    if not clash:
                        break
                self.order_no = code
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    dish = models.ForeignKey(Dish, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=7, decimal_places=2)  # price when ordered

    @property
    def line_total(self):
        return self.price * self.quantity


class SiteSetting(models.Model):
    accepting_orders = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        self.pk = 1  # there is only ever one row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
