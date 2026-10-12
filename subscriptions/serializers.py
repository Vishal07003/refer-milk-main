from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from accounts.models import Address
from accounts.serializers import AddressSerializer
from orders.models import DeliverySlot
from orders.serializers import DeliverySlotSerializer
from products.models import Product

from .models import Payment, ReferralDiscountTier, Subscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = (
            'id', 'name', 'product', 'product_name', 'product_price',
            'quantity', 'unit', 'frequency', 'price_per_unit',
            'schedule_description', 'is_active', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class ReferralDiscountTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralDiscountTier
        fields = ('id', 'min_referrals', 'discount_per_unit')
        read_only_fields = ('id',)


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True, default='')
    address_detail = AddressSerializer(source='address', read_only=True)
    delivery_slot_detail = DeliverySlotSerializer(source='delivery_slot', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)
    delivery_boy_name = serializers.SerializerMethodField()
    delivery_boy_mobile = serializers.CharField(source='delivery_boy.mobile_number', read_only=True, default='')
    customer_name = serializers.SerializerMethodField()
    customer_mobile = serializers.CharField(source='user.mobile_number', read_only=True, default='')
    days_used = serializers.IntegerField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    amount_used = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    refund_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Subscription
        fields = (
            'id', 'plan', 'plan_name', 'user', 'customer_name', 'customer_mobile',
            'product', 'product_name', 'product_unit',
            'address', 'address_detail', 'delivery_slot', 'delivery_slot_detail',
            'delivery_boy', 'delivery_boy_name', 'delivery_boy_mobile',
            'quantity', 'start_date', 'end_date',
            'price_per_unit', 'discount_per_unit', 'final_price_per_unit',
            'total_amount', 'status', 'cancelled_at',
            'days_used', 'days_remaining', 'amount_used', 'refund_amount',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'user', 'price_per_unit', 'discount_per_unit',
            'final_price_per_unit', 'total_amount', 'cancelled_at',
            'created_at', 'updated_at',
        )

    def get_delivery_boy_name(self, obj):
        if obj.delivery_boy:
            name = f"{obj.delivery_boy.first_name} {obj.delivery_boy.last_name}".strip()
            return name or obj.delivery_boy.username or obj.delivery_boy.mobile_number
        return ""

    def get_customer_name(self, obj):
        if obj.user:
            name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return name or obj.user.username or obj.user.mobile_number
        return ""


class RequestCustomerSubscriptionSerializer(serializers.Serializer):
    """
    Customer requests a subscription linked to an active predefined plan.
    Strictly creates status='pending' (pending approval). Customer cannot activate or set price.
    """
    plan_id = serializers.IntegerField()
    address_id = serializers.IntegerField()
    delivery_slot_id = serializers.IntegerField(required=False, allow_null=True)
    start_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_plan_id(self, value):
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Subscription plan not found or currently inactive.")
        return value

    def validate_address_id(self, value):
        user = self.context['request'].user
        try:
            address = Address.objects.get(id=value, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Delivery address not found.")
        return value

    def validate_delivery_slot_id(self, value):
        if value is None:
            return value
        try:
            DeliverySlot.objects.get(id=value)
        except DeliverySlot.DoesNotExist:
            raise serializers.ValidationError("Delivery slot not found.")
        return value


class UpdateCustomerSubscriptionSerializer(serializers.Serializer):
    """
    Customer updates their existing subscription delivery slot, quantity, or address.
    """
    delivery_slot_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.1'), required=False)
    address_id = serializers.IntegerField(required=False)

    def validate_delivery_slot_id(self, value):
        if value is None:
            return value
        try:
            DeliverySlot.objects.get(id=value, is_active=True)
        except DeliverySlot.DoesNotExist:
            raise serializers.ValidationError("Delivery slot not found or inactive.")
        return value

    def validate_address_id(self, value):
        user = self.context['request'].user
        try:
            Address.objects.get(id=value, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Delivery address not found.")
        return value


class CreateSubscriptionSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    address_id = serializers.IntegerField()
    delivery_slot_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.1'))
    start_date = serializers.DateField()
    payment_method = serializers.CharField(required=False, default='razorpay')

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive.")
        return value

    def validate_address_id(self, value):
        try:
            Address.objects.get(id=value)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Address not found.")
        return value

    def validate_delivery_slot_id(self, value):
        if value is None:
            return value
        try:
            DeliverySlot.objects.get(id=value)
        except DeliverySlot.DoesNotExist:
            raise serializers.ValidationError("Delivery slot not found.")
        return value

    def validate_start_date(self, value):
        # Allow today's date and future dates
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        product = Product.objects.get(id=attrs['product_id'])

        price = product.price
        discount_per_unit = Decimal('0')

        if product.has_referral_discount:
            referral_count = user.referrals.count()
            discount_tier = ReferralDiscountTier.objects.filter(
                min_referrals__lte=referral_count
            ).order_by('-min_referrals').first()
            if discount_tier:
                discount_per_unit = discount_tier.discount_per_unit

        final_price = price - discount_per_unit
        start_date = attrs['start_date']
        end_date = start_date + timedelta(days=30)
        quantity = attrs['quantity']
        total_amount = final_price * quantity * 30

        attrs['product'] = product
        attrs['address'] = Address.objects.get(id=attrs['address_id'])
        attrs['delivery_slot'] = (
            DeliverySlot.objects.get(id=attrs['delivery_slot_id'])
            if attrs.get('delivery_slot_id') else None
        )
        attrs['price_per_unit'] = price
        attrs['discount_per_unit'] = discount_per_unit
        attrs['final_price_per_unit'] = final_price
        attrs['end_date'] = end_date
        attrs['total_amount'] = total_amount

        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'id', 'user', 'subscription', 'order', 'payment_for',
            'amount', 'payment_method', 'payment_status', 'transaction_id',
            'razorpay_payment_id', 'notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'user', 'created_at', 'updated_at')


class CreatePaymentSerializer(serializers.Serializer):
    subscription_id = serializers.IntegerField(required=False, allow_null=True)
    order_id = serializers.IntegerField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(choices=Payment.METHOD_CHOICES)
    transaction_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        user = self.context['request'].user
        sub_id = attrs.get('subscription_id')
        order_id = attrs.get('order_id')

        if sub_id and order_id:
            raise serializers.ValidationError("Provide either subscription_id or order_id, not both.")
        if not sub_id and not order_id:
            raise serializers.ValidationError("Either subscription_id or order_id is required.")

        if sub_id:
            try:
                subscription = Subscription.objects.get(id=sub_id, user=user)
            except Subscription.DoesNotExist:
                raise serializers.ValidationError({"msg": "Subscription not found."})
            if subscription.status != 'active':
                raise serializers.ValidationError({"msg": "Can only make payments for active subscriptions."})
            attrs['subscription'] = subscription
            attrs['amount'] = subscription.total_amount
            attrs['payment_for'] = 'subscription'
        else:
            from orders.models import Order
            try:
                order = Order.objects.get(id=order_id, user=user)
            except Order.DoesNotExist:
                raise serializers.ValidationError({"msg": "Order not found."})
            attrs['order'] = order
            attrs['amount'] = order.final_amount
            attrs['payment_for'] = 'order'

        return attrs


class CancelSubscriptionSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=Payment.METHOD_CHOICES, required=False)
    transaction_id = serializers.CharField(max_length=255, required=False, allow_blank=True)


class CustomerDeliveryItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    delivery_date = serializers.DateField()
    status = serializers.CharField()
    status_display = serializers.CharField()
    delivered_at = serializers.DateTimeField(allow_null=True)
    notes = serializers.CharField(allow_blank=True)
    product_name = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    unit = serializers.CharField()
    delivery_boy_name = serializers.CharField(allow_blank=True)


class CustomerSubscriptionBillSerializer(serializers.Serializer):
    subscription_id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity_per_day = serializers.DecimalField(max_digits=10, decimal_places=2)
    unit = serializers.CharField()
    rate_per_unit = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_per_unit = serializers.DecimalField(max_digits=10, decimal_places=2)
    final_rate_per_unit = serializers.DecimalField(max_digits=10, decimal_places=2)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    subscription_status = serializers.CharField()
    total_scheduled_drops = serializers.IntegerField()
    delivered_drops_count = serializers.IntegerField()
    delivered_volume = serializers.DecimalField(max_digits=10, decimal_places=2)
    failed_drops_count = serializers.IntegerField()
    pending_future_drops_count = serializers.IntegerField()
    delivered_subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_payable = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_status = serializers.CharField()
    delivery_breakdown = serializers.ListField(child=CustomerDeliveryItemSerializer(), required=False)

