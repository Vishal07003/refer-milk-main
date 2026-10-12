from decimal import Decimal

from rest_framework import serializers

from accounts.models import Address
from products.models import Product

from .models import DeliverySlot, Order, OrderItem, OfflinePaymentCollection


class DeliverySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliverySlot
        fields = ('id', 'name', 'start_time', 'end_time', 'is_active', 'created_at')
        read_only_fields = ('id', 'created_at')


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ('id', 'product', 'product_name', 'quantity', 'price', 'total')
        read_only_fields = ('id', 'total')


class OfflinePaymentCollectionSerializer(serializers.ModelSerializer):
    delivery_partner_name = serializers.SerializerMethodField()
    delivery_partner_mobile = serializers.CharField(source='delivery_partner.mobile_number', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer_mobile = serializers.CharField(source='order.user.mobile_number', read_only=True)

    class Meta:
        model = OfflinePaymentCollection
        fields = (
            'id', 'order_id', 'customer_name', 'customer_mobile',
            'delivery_partner', 'delivery_partner_name', 'delivery_partner_mobile',
            'payment_method', 'amount', 'status', 'transaction_reference',
            'reason', 'collected_at', 'verified_at', 'verified_by',
            'notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_delivery_partner_name(self, obj):
        name = f"{obj.delivery_partner.first_name or ''} {obj.delivery_partner.last_name or ''}".strip()
        return name or obj.delivery_partner.mobile_number

    def get_customer_name(self, obj):
        name = f"{obj.order.user.first_name or ''} {obj.order.user.last_name or ''}".strip()
        return name or obj.order.user.mobile_number


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    address_detail = serializers.SerializerMethodField()
    delivery_slot_detail = DeliverySlotSerializer(source='delivery_slot', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'user', 'address', 'address_detail', 'delivery_slot', 'delivery_slot_detail',
            'items', 'total_amount', 'discount_amount', 'final_amount',
            'status', 'payment_method', 'payment_status', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'user', 'total_amount', 'discount_amount', 'final_amount',
            'payment_status', 'created_at', 'updated_at',
        )

    def get_address_detail(self, obj):
        from accounts.serializers import AddressSerializer
        return AddressSerializer(obj.address).data


class CreateOrderItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.1'))

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive.")
        return value


class CreateOrderSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    delivery_slot_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(
        choices=['cash', 'upi_at_delivery', 'razorpay'],
        default='cash',
        required=False,
    )
    items = CreateOrderItemSerializer(many=True)

    def validate_address_id(self, value):
        user = self.context['request'].user
        try:
            Address.objects.get(id=value, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Address not found.")
        return value

    def validate_delivery_slot_id(self, value):
        try:
            slot = DeliverySlot.objects.get(id=value, is_active=True)
        except DeliverySlot.DoesNotExist:
            raise serializers.ValidationError("Delivery slot not found or inactive.")
        return value

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value
