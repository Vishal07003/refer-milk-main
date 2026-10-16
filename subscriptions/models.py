from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from accounts.models import Address, User
from core.soft_delete import SoftDeleteModel


class ReferralDiscountTier(models.Model):
    min_referrals = models.PositiveIntegerField(unique=True)
    discount_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Referral Discount Tier'
        verbose_name_plural = 'Referral Discount Tiers'
        ordering = ['min_referrals']

    def __str__(self):
        return f"{self.min_referrals} referrals → ₹{self.discount_per_unit}/unit discount"


class SubscriptionPlan(models.Model):
    FREQUENCY_CHOICES = (
        ('daily', 'Daily'),
        ('alternate', 'Alternate Days'),
        ('weekly', 'Weekly'),
    )

    name = models.CharField(max_length=150)
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='subscription_plans')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), help_text="Quantity per delivery")
    unit = models.CharField(max_length=20, default='litre')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, help_text="Configured price per unit for plan")
    schedule_description = models.CharField(max_length=255, blank=True, default='Morning Delivery')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.product.name} ({self.quantity} {self.unit}, ₹{self.price_per_unit}/{self.unit})"


class Subscription(SoftDeleteModel):
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    )

    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='customer_subscriptions'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='subscriptions')
    address = models.ForeignKey(Address, on_delete=models.CASCADE, related_name='subscriptions')
    delivery_slot = models.ForeignKey('orders.DeliverySlot', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Units per delivery")
    start_date = models.DateField()
    end_date = models.DateField()
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price at time of purchase")
    discount_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Referral discount applied")
    final_price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price after discount")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="final_price × quantity × 30 days")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    delivery_boy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_subscriptions')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=255, blank=True, default='')
    razorpay_payment_id = models.CharField(max_length=255, blank=True, default='')
    razorpay_signature = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        ordering = ['-created_at']

    def __str__(self):
        plan_prefix = f"[{self.plan.name}] " if self.plan else ""
        return f"{plan_prefix}{self.user.mobile_number} - {self.product.name} x{self.quantity}/day ({self.status})"

    def delete(self, using=None, keep_parents=False, hard=False, deleted_by=None):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents, hard=True)
        # Soft delete: cancel subscription and clean future pending drops
        self.is_deleted = True
        self.status = "cancelled"
        if not self.cancelled_at:
            self.cancelled_at = timezone.now()
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=["is_deleted", "status", "cancelled_at", "deleted_at", "deleted_by", "updated_at"])

        # Stop future pending daily deliveries safely (preserve delivered/failed historical drops!)
        today = timezone.localdate()
        self.daily_deliveries.filter(delivery_date__gte=today, status="pending").delete()
        return 1, {self._meta.label: 1}

    def save(self, *args, **kwargs):
        self.final_price_per_unit = Decimal(str(self.price_per_unit)) - Decimal(str(self.discount_per_unit or 0))
        self.total_amount = self.final_price_per_unit * Decimal(str(self.quantity)) * 30
        super().save(*args, **kwargs)

    @property
    def total_days(self):
        return (self.end_date - self.start_date).days

    @property
    def days_used(self):
        today = timezone.now().date()
        if today >= self.end_date:
            return self.total_days
        if today <= self.start_date:
            return 0
        return (today - self.start_date).days

    @property
    def days_remaining(self):
        return max(0, self.total_days - self.days_used)

    @property
    def amount_used(self):
        return self.final_price_per_unit * Decimal(str(self.quantity)) * Decimal(str(self.days_used))

    @property
    def refund_amount(self):
        return self.total_amount - self.amount_used


class Payment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card'),
        ('net_banking', 'Net Banking'),
        ('wallet', 'Wallet'),
        ('razorpay', 'Razorpay'),
    )

    PAYMENT_FOR_CHOICES = (
        ('subscription', 'Subscription'),
        ('order', 'Order'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    payment_for = models.CharField(max_length=20, choices=PAYMENT_FOR_CHOICES, default='subscription')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash')
    payment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=255, blank=True, default='')
    razorpay_payment_id = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.mobile_number} - ₹{self.amount} ({self.payment_status})"
