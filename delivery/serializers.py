from decimal import Decimal
from rest_framework import serializers

from accounts.models import Address, DeliveryBoyProfile, User
from orders.models import Order, OrderItem, DeliverySlot
from subscriptions.models import Subscription
from .models import DailyDelivery


class DeliveryBoyProfileSerializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = DeliveryBoyProfile
        fields = (
            'id', 'mobile_number', 'first_name', 'last_name',
            'vehicle_number', 'is_available', 'zone',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class CreateDeliveryBoySerializer(serializers.Serializer):
    mobile_number = serializers.CharField(max_length=15)
    first_name = serializers.CharField(max_length=150, required=False, default='')
    last_name = serializers.CharField(max_length=150, required=False, default='')
    vehicle_number = serializers.CharField(max_length=20, required=False, default='')
    zone = serializers.CharField(max_length=100, required=False, default='')

    def validate_mobile_number(self, value):
        if User.objects.filter(mobile_number=value).exists():
            raise serializers.ValidationError("A user with this mobile number already exists.")
        return value

    def create(self, validated_data):
        mobile_number = validated_data['mobile_number']
        user = User.objects.create_user(
            username=mobile_number,
            mobile_number=mobile_number,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role='delivery_boy',
        )
        profile = DeliveryBoyProfile.objects.create(
            user=user,
            vehicle_number=validated_data.get('vehicle_number', ''),
            zone=validated_data.get('zone', ''),
        )
        return user, profile


class DeliveryBoyListSerializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(source='user.mobile_number', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    is_available = serializers.BooleanField(source='delivery_profile.is_available', read_only=True)
    zone = serializers.CharField(source='delivery_profile.zone', read_only=True)
    vehicle_number = serializers.CharField(source='delivery_profile.vehicle_number', read_only=True)
    total_deliveries = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'mobile_number', 'first_name', 'last_name',
            'is_available', 'zone', 'vehicle_number', 'total_deliveries',
            'is_active', 'date_joined',
        )

    def get_total_deliveries(self, obj):
        return DailyDelivery.objects.filter(
            delivery_boy=obj, status='delivered'
        ).count()


class AssignOrderSerializer(serializers.Serializer):
    delivery_boy_id = serializers.IntegerField()
    order_id = serializers.IntegerField()

    def validate_delivery_boy_id(self, value):
        try:
            user = User.objects.get(id=value, role__in=['delivery_boy', 'delivery'])
        except User.DoesNotExist:
            raise serializers.ValidationError("Delivery boy not found.")
        return value

    def validate_order_id(self, value):
        try:
            order = Order.objects.get(id=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found.")
        return value


class AssignSubscriptionSerializer(serializers.Serializer):
    delivery_boy_id = serializers.IntegerField()
    subscription_id = serializers.IntegerField()

    def validate_delivery_boy_id(self, value):
        try:
            user = User.objects.get(id=value, role__in=['delivery_boy', 'delivery'])
        except User.DoesNotExist:
            raise serializers.ValidationError("Delivery boy not found.")
        return value

    def validate_subscription_id(self, value):
        try:
            subscription = Subscription.objects.get(id=value, status='active')
        except Subscription.DoesNotExist:
            raise serializers.ValidationError("Active subscription not found.")
        return value


class UpdateDeliveryStatusSerializer(serializers.Serializer):
    STATUS_CHOICES = (
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    )
    status = serializers.ChoiceField(choices=STATUS_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class DeliveryCustomerMinimalSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'name', 'mobile_number')

    def get_name(self, obj):
        name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return name or obj.mobile_number


class DeliveryAddressMinimalSerializer(serializers.ModelSerializer):
    instructions = serializers.SerializerMethodField()

    class Meta:
        model = Address
        fields = (
            'id', 'house_number', 'street', 'area', 'city',
            'state', 'pincode', 'latitude', 'longitude', 'instructions',
        )

    def get_instructions(self, obj):
        return getattr(obj, 'instructions', '') or getattr(obj, 'label', '')


class DeliveryOrderItemMinimalSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = OrderItem
        fields = ('id', 'product_name', 'product_unit', 'quantity', 'price')


class DeliveryOrderSerializer(serializers.ModelSerializer):
    customer = DeliveryCustomerMinimalSerializer(source='user', read_only=True)
    delivery_address = DeliveryAddressMinimalSerializer(source='address', read_only=True)
    items = DeliveryOrderItemMinimalSerializer(many=True, read_only=True)
    delivery_slot = serializers.CharField(source='delivery_slot.name', read_only=True)
    total_items = serializers.SerializerMethodField()
    payment_method = serializers.CharField(read_only=True)
    payment_status = serializers.CharField(read_only=True)
    amount_to_collect = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id', 'customer', 'delivery_address', 'items',
            'delivery_slot', 'total_items', 'final_amount',
            'payment_method', 'payment_status', 'amount_to_collect',
            'status', 'created_at', 'delivered_at',
        )

    def get_total_items(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_amount_to_collect(self, obj):
        if obj.payment_method in ('cash', 'upi_at_delivery') and obj.payment_status == 'pending':
            return str(obj.final_amount)
        return '0.00'


class DailyDeliverySerializer(serializers.ModelSerializer):
    customer = DeliveryCustomerMinimalSerializer(source='subscription.user', read_only=True)
    delivery_address = DeliveryAddressMinimalSerializer(source='subscription.address', read_only=True)
    subscription_id = serializers.IntegerField(source='subscription.id', read_only=True)
    product_name = serializers.CharField(source='subscription.product.name', read_only=True)
    product_unit = serializers.CharField(source='subscription.product.get_unit_display', read_only=True)
    plan_unit = serializers.CharField(source='subscription.plan.unit', read_only=True, default='')
    quantity = serializers.DecimalField(source='subscription.quantity', max_digits=10, decimal_places=2, read_only=True)
    delivery_slot = serializers.CharField(source='subscription.delivery_slot.name', read_only=True)

    class Meta:
        model = DailyDelivery
        fields = (
            'id', 'subscription_id', 'customer', 'delivery_address',
            'product_name', 'product_unit', 'plan_unit', 'quantity',
            'delivery_date', 'delivery_slot',
            'status', 'delivered_at', 'notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'delivered_at', 'created_at', 'updated_at')


class CashHandoverSerializer(serializers.ModelSerializer):
    delivery_boy_name = serializers.SerializerMethodField()
    delivery_boy_mobile = serializers.CharField(source='delivery_boy.mobile_number', read_only=True)
    confirmed_by_name = serializers.SerializerMethodField()

    class Meta:
        from .models import CashHandover
        model = CashHandover
        fields = (
            'id', 'delivery_boy', 'delivery_boy_name', 'delivery_boy_mobile',
            'submitted_amount', 'received_amount', 'discrepancy_amount',
            'status', 'submitted_at', 'confirmed_at', 'confirmed_by',
            'confirmed_by_name', 'delivery_notes', 'admin_notes',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'delivery_boy', 'discrepancy_amount', 'status',
            'submitted_at', 'confirmed_at', 'confirmed_by', 'created_at', 'updated_at',
        )

    def get_delivery_boy_name(self, obj):
        name = f"{obj.delivery_boy.first_name} {obj.delivery_boy.last_name}".strip()
        return name or obj.delivery_boy.mobile_number

    def get_confirmed_by_name(self, obj):
        if obj.confirmed_by:
            name = f"{obj.confirmed_by.first_name} {obj.confirmed_by.last_name}".strip()
            return name or obj.confirmed_by.username or obj.confirmed_by.mobile_number
        return None


class SubmitCashHandoverSerializer(serializers.Serializer):
    submitted_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    delivery_notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')

