from decimal import Decimal

from rest_framework import serializers

from accounts.models import Address
from products.models import Product

from .models import DeliverySlot, Order, OrderItem


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


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    address_detail = serializers.SerializerMethodField()
    delivery_slot_detail = DeliverySlotSerializer(source='delivery_slot', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'user', 'address', 'address_detail', 'delivery_slot', 'delivery_slot_detail',
            'items', 'total_amount', 'discount_amount', 'final_amount',
            'status', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'user', 'total_amount', 'discount_amount', 'final_amount',
            'created_at', 'updated_at',
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
