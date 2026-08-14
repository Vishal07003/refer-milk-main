from django.contrib import admin

from .models import Payment, ReferralDiscountTier, Subscription


@admin.register(ReferralDiscountTier)
class ReferralDiscountTierAdmin(admin.ModelAdmin):
    list_display = ('id', 'min_referrals', 'discount_per_unit')
    ordering = ('min_referrals',)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'product', 'address', 'quantity', 'start_date', 'end_date',
        'price_per_unit', 'discount_per_unit', 'final_price_per_unit',
        'total_amount', 'status', 'cancelled_at', 'created_at',
    )
    list_filter = ('status',)
    search_fields = ('user__mobile_number', 'product__name')
    readonly_fields = ('cancelled_at', 'created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'payment_for', 'amount', 'payment_method',
        'payment_status', 'transaction_id', 'razorpay_payment_id', 'created_at',
    )
    list_filter = ('payment_status', 'payment_method', 'payment_for')
    search_fields = ('user__mobile_number', 'transaction_id', 'razorpay_payment_id')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
