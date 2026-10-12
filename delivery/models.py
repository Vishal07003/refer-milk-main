from django.db import models

from accounts.models import User


class DailyDelivery(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    )

    subscription = models.ForeignKey(
        'subscriptions.Subscription', on_delete=models.CASCADE,
        related_name='daily_deliveries'
    )
    delivery_boy = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='daily_deliveries'
    )
    delivery_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    delivered_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Daily Delivery'
        verbose_name_plural = 'Daily Deliveries'
        ordering = ['-delivery_date']
        unique_together = ('subscription', 'delivery_date')

    def __str__(self):
        return f"{self.subscription.product.name} - {self.delivery_date} ({self.status})"


class CashHandover(models.Model):
    STATUS_CHOICES = (
        ('submitted', 'Submitted by Partner'),
        ('confirmed', 'Confirmed by Admin'),
        ('discrepancy', 'Discrepancy Noted'),
        ('rejected', 'Rejected'),
    )

    delivery_boy = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='cash_handovers'
    )
    submitted_amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Amount submitted by Delivery Boy"
    )
    received_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Actual cash amount verified and counted by Admin"
    )
    discrepancy_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Difference (received_amount - submitted_amount)"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='submitted'
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='confirmed_cash_handovers'
    )
    delivery_notes = models.TextField(
        blank=True, default='', help_text="Notes from delivery boy"
    )
    admin_notes = models.TextField(
        blank=True, default='', help_text="Notes or investigation remarks from admin"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cash Handover'
        verbose_name_plural = 'Cash Handovers'
        ordering = ['-created_at']

    def __str__(self):
        return f"Handover #{self.id} - {self.delivery_boy.mobile_number} (₹{self.submitted_amount}) - {self.status}"

