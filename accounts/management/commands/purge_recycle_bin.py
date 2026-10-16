import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User, DeliveryBoyProfile, AdminAuditLog
from products.models import Product
from subscriptions.models import Subscription
from orders.models import OfflinePaymentCollection
from delivery.models import DailyDelivery, CashHandover
from core.soft_delete import get_retention_days

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Idempotent scheduled cleanup task that permanently deletes eligible soft-deleted "
        "records after their retention period, enforcing strict foreign-key and financial audit safety."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the cleanup and report which records would be deleted without making changes.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=None,
            help="Override the retention period (in days). Defaults to the value in SystemSetting or 30.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        override_days = options.get("retention_days")

        retention_days = override_days if (override_days and override_days > 0) else get_retention_days()
        cutoff_date = timezone.now() - timedelta(days=retention_days)

        mode_str = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.NOTICE(
                f"{mode_str}Starting Recycle Bin purge. Retention period: {retention_days} days. Cutoff: {cutoff_date}."
            )
        )
        logger.info(f"{mode_str}Recycle Bin purge job started. Retention: {retention_days} days. Cutoff: {cutoff_date}.")

        stats = {
            "customers_purged": 0,
            "customers_skipped": 0,
            "delivery_boys_purged": 0,
            "delivery_boys_skipped": 0,
            "products_purged": 0,
            "products_skipped": 0,
            "subscriptions_purged": 0,
            "subscriptions_skipped": 0,
            "errors": 0,
        }

        # -------------------------------------------------------------
        # 1. PURGE ELIGIBLE SUBSCRIPTIONS
        # -------------------------------------------------------------
        eligible_subs = Subscription.deleted_objects.filter(deleted_at__lte=cutoff_date)
        for sub in eligible_subs:
            try:
                # Check financial & delivery dependencies
                has_fulfilled_drops = sub.daily_deliveries.exclude(status="pending").exists()
                has_payments = sub.payments.exists()
                if has_fulfilled_drops or has_payments:
                    # Keep permanently archived to preserve financial/delivery history
                    stats["subscriptions_skipped"] += 1
                    logger.info(f"Skipping purge of Subscription #{sub.id}: fulfilled drops/payments exist.")
                    continue

                if not dry_run:
                    with transaction.atomic():
                        sub.daily_deliveries.all().delete()
                        sub_id = sub.id
                        sub.hard_delete()
                    logger.info(f"Purged Subscription #{sub_id}.")
                stats["subscriptions_purged"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error purging Subscription #{sub.id}: {e}", exc_info=True)

        # -------------------------------------------------------------
        # 2. PURGE ELIGIBLE PRODUCTS
        # -------------------------------------------------------------
        eligible_products = Product.deleted_objects.filter(deleted_at__lte=cutoff_date)
        for prod in eligible_products:
            try:
                # Check dependencies
                has_orders = prod.orderitem_set.exists()
                has_subs = prod.subscriptions.exists()
                if has_orders or has_subs:
                    stats["products_skipped"] += 1
                    logger.info(f"Skipping purge of Product '{prod.name}' (id={prod.id}): historical orders/subs exist.")
                    continue

                if not dry_run:
                    with transaction.atomic():
                        prod.images.all().delete()
                        prod_name = prod.name
                        prod.hard_delete()
                    logger.info(f"Purged Product '{prod_name}'.")
                stats["products_purged"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error purging Product #{prod.id}: {e}", exc_info=True)

        # -------------------------------------------------------------
        # 3. PURGE ELIGIBLE DELIVERY BOYS
        # -------------------------------------------------------------
        eligible_boys = User.deleted_objects.filter(role="delivery_boy", deleted_at__lte=cutoff_date)
        for boy in eligible_boys:
            try:
                has_collections = OfflinePaymentCollection.objects.filter(delivery_partner=boy).exists()
                has_handovers = CashHandover.objects.filter(delivery_boy=boy).exists()
                has_deliveries = DailyDelivery.objects.filter(delivery_boy=boy).exclude(status="pending").exists()
                if has_collections or has_handovers or has_deliveries:
                    stats["delivery_boys_skipped"] += 1
                    logger.info(f"Skipping purge of Partner {boy.mobile_number}: financial cash/delivery records exist.")
                    continue

                if not dry_run:
                    with transaction.atomic():
                        DeliveryBoyProfile.objects.filter(user=boy).delete()
                        mob = boy.mobile_number
                        boy.hard_delete()
                    logger.info(f"Purged Partner {mob}.")
                stats["delivery_boys_purged"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error purging Partner #{boy.id}: {e}", exc_info=True)

        # -------------------------------------------------------------
        # 4. PURGE ELIGIBLE CUSTOMERS
        # -------------------------------------------------------------
        eligible_customers = User.deleted_objects.filter(role="customer", deleted_at__lte=cutoff_date)
        for cust in eligible_customers:
            try:
                has_orders = cust.orders.exists()
                has_payments = cust.payments.exists()
                has_collections = OfflinePaymentCollection.objects.filter(order__user=cust).exists()
                if has_orders or has_payments or has_collections:
                    stats["customers_skipped"] += 1
                    logger.info(f"Skipping purge of Customer {cust.mobile_number}: orders/payments exist.")
                    continue

                if not dry_run:
                    with transaction.atomic():
                        cust.notifications.all().delete()
                        cust.addresses.all().delete()
                        cust.device_tokens.all().delete()
                        mob = cust.mobile_number
                        cust.hard_delete()
                    logger.info(f"Purged Customer {mob}.")
                stats["customers_purged"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error purging Customer #{cust.id}: {e}", exc_info=True)

        # Log completion in AdminAuditLog if not a dry-run
        summary_msg = (
            f"{mode_str}Recycle Bin purge completed. "
            f"Purged: {stats['customers_purged']} customers, {stats['delivery_boys_purged']} partners, "
            f"{stats['products_purged']} products, {stats['subscriptions_purged']} subscriptions. "
            f"Preserved for audit: {stats['customers_skipped']} customers, {stats['delivery_boys_skipped']} partners, "
            f"{stats['products_skipped']} products, {stats['subscriptions_skipped']} subscriptions. "
            f"Errors: {stats['errors']}."
        )

        if not dry_run:
            try:
                AdminAuditLog.objects.create(
                    user=None,
                    module="recycle_bin",
                    action="purge_cleanup_job",
                    target_id="cron",
                    details=summary_msg,
                )
            except Exception:
                pass

        logger.info(summary_msg)
        self.stdout.write(self.style.SUCCESS(summary_msg))
