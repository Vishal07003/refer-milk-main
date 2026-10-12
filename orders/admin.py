from django.contrib import admin

from .models import DeliverySlot, Order, OrderItem, OfflinePaymentCollection


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price', 'total')


@admin.register(DeliverySlot)
class DeliverySlotAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'start_time', 'end_time', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'delivery_slot', 'total_amount', 'discount_amount',
        'final_amount', 'status', 'payment_method', 'payment_status', 'created_at',
    )
    list_filter = ('status', 'payment_method', 'payment_status')
    search_fields = ('user__mobile_number', 'razorpay_order_id')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [OrderItemInline]
    ordering = ('-created_at',)


@admin.register(OfflinePaymentCollection)
class OfflinePaymentCollectionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'order', 'delivery_partner', 'payment_method', 'amount',
        'status', 'transaction_reference', 'reason', 'collected_at', 'verified_at', 'verified_by',
    )
    list_filter = ('status', 'payment_method', 'reason')
    search_fields = (
        'order__id', 'delivery_partner__mobile_number',
        'order__user__mobile_number', 'transaction_reference',
    )
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
