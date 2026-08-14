from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, Wallet


@receiver(post_save, sender=User)
def ensure_customer_wallet(sender, instance, created, **kwargs):
    """
    Automatically creates a Wallet for every Customer user upon creation.
    Does NOT create wallets for delivery_boy or admin roles.
    """
    if instance.role == 'customer':
        Wallet.objects.get_or_create(user=instance)
