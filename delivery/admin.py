from django.contrib import admin

from .models import DailyDelivery


@admin.register(DailyDelivery)
class DailyDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'subscription', 'delivery_boy', 'delivery_date',
        'status', 'delivered_at', 'notes', 'created_at',
    )
    list_filter = ('status', 'delivery_date')
    search_fields = (
        'subscription__user__mobile_number',
        'delivery_boy__mobile_number',
        'subscription__product__name',
    )
    readonly_fields = ('delivered_at', 'created_at', 'updated_at')
    ordering = ('-delivery_date',)
