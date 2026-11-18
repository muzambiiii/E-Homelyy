from django.contrib import admin
from .models import Dish, Order, OrderItem, SiteSetting


@admin.register(Dish)
class DishAdmin(admin.ModelAdmin):
    list_display = ('name', 'meal', 'category', 'price', 'is_available', 'daily_limit')
    list_editable = ('meal', 'price', 'is_available', 'daily_limit')
    list_filter = ('meal', 'category')
    help_texts = {'daily_limit': '0 = no limit. Set to e.g. 75 for Biriyani/Meals.'}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_no', 'name', 'phone', 'status', 'payment_status',
                    'advance_amount', 'total', 'created')
    list_filter = ('status', 'payment_status')
    search_fields = ('order_no', 'name', 'phone', 'razorpay_payment_id', 'razorpay_refund_id')
    readonly_fields = ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_refund_id',
                       'paid_at', 'refunded_at')
    inlines = [OrderItemInline]


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ('accepting_orders',)
