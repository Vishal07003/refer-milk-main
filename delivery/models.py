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
