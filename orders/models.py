from django.db import models

from accounts.models import Address, User
from products.models import Product


class DeliverySlot(models.Model):
    name = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Delivery Slot'
        verbose_name_plural = 'Delivery Slots'
        ordering = ['start_time']

    def __str__(self):
        return f"{self.name} ({self.start_time} - {self.end_time})"


class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )

    PAYMENT_METHOD_CHOICES = (
        ('razorpay', 'Razorpay'),
        ('cash', 'Cash on Delivery'),
        ('upi_at_delivery', 'UPI at Delivery'),
    )

    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('collected', 'Collected'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    address = models.ForeignKey(Address, on_delete=models.CASCADE, related_name='orders')
    delivery_slot = models.ForeignKey(DeliverySlot, on_delete=models.SET_NULL, null=True, related_name='orders')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='razorpay')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    delivery_boy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders')
    delivered_at = models.DateTimeField(null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=255, blank=True, default='')
    razorpay_payment_id = models.CharField(max_length=255, blank=True, default='')
    razorpay_signature = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} - {self.user.mobile_number} ({self.status})"


class OfflinePaymentCollection(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('collected', 'Collected'),
        ('failed', 'Failed'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    )

    METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('upi_at_delivery', 'UPI at Delivery'),
    )

    FAILURE_REASONS = (
        ('customer_unavailable', 'Customer Unavailable'),
        ('customer_refused', 'Customer Refused'),
        ('insufficient_cash', 'Insufficient Cash'),
        ('upi_failed', 'UPI Failed'),
        ('other', 'Other'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='offline_collections')
    delivery_partner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='offline_collections')
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='collected')
    transaction_reference = models.CharField(max_length=255, blank=True, default='')
    reason = models.CharField(max_length=50, blank=True, default='', choices=FAILURE_REASONS)
    collected_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_offline_collections'
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Offline Payment Collection'
        verbose_name_plural = 'Offline Payment Collections'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['delivery_partner', 'status']),
            models.Index(fields=['order', 'status']),
            models.Index(fields=['payment_method', 'status']),
        ]

    def __str__(self):
        return f"Collection #{self.id} for Order #{self.order_id} - ₹{self.amount} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price at purchase time")
    total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def save(self, *args, **kwargs):
        self.total = self.price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"
