import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from subscriptions.models import CustomerVacation
from delivery.models import DailyDelivery
from notifications.services import send_notification_to_user

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Idempotent scheduled task that checks for active CustomerVacations whose end_date has passed, "
        "resumes only the subscriptions paused by Vacation Mode, safely recreates missing daily deliveries, "
        "marks the vacation as completed, and notifies customer and delivery partners."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the resume process without writing database changes.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        today = timezone.localdate()

        self.stdout.write(
            self.style.NOTICE(f"{'[DRY-RUN] ' if dry_run else ''}Checking for expired vacations on {today}...")
        )

        # Vacations where end_date < today and status is 'active'
        expired_vacations = CustomerVacation.objects.filter(
            status="active",
            end_date__lt=today,
        ).select_related("user")

        count = expired_vacations.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No expired active vacations found."))
            return

        self.stdout.write(f"Found {count} vacation(s) due for resumption.")

        resumed_count = 0
        error_count = 0

        for vacation in expired_vacations:
            customer = vacation.user
            try:
                if dry_run:
                    self.stdout.write(f"[DRY-RUN] Would resume vacation ID {vacation.id} for customer {customer.mobile_number}")
                    resumed_count += 1
                    continue

                with transaction.atomic():
                    # Re-lock record to prevent race conditions
                    vac = CustomerVacation.objects.select_for_update().get(id=vacation.id)
                    if vac.status != "active":
                        continue

                    affected_records = vac.affected_subscriptions.select_related("subscription").all()
                    resumed_sub_count = 0
                    affected_partner_ids = set()

                    for rec in affected_records:
                        sub = rec.subscription
                        # Only resume if subscription is still paused and was paused by this vacation
                        if sub.status == "paused" and rec.previous_status == "active":
                            sub.status = "active"
                            sub.save(update_fields=["status", "updated_at"])
                            resumed_sub_count += 1

                            if sub.delivery_boy_id:
                                affected_partner_ids.add(sub.delivery_boy)

                            # Re-create deliveries from max(today, sub.start_date) up to sub.end_date
                            # Or next 7 days if no end_date
                            sub_end = sub.end_date or (today + timedelta(days=7))
                            curr_date = today
                            while curr_date <= sub_end and (curr_date - today).days < 7:
                                DailyDelivery.objects.get_or_create(
                                    subscription=sub,
                                    delivery_date=curr_date,
                                    defaults={
                                        "delivery_boy": sub.delivery_boy,
                                        "status": "pending",
                                    },
                                )
                                curr_date += timedelta(days=1)

                    vac.status = "completed"
                    vac.save(update_fields=["status", "updated_at"])

                # Notifications outside transaction
                try:
                    send_notification_to_user(
                        user=customer,
                        title="Welcome Back from Vacation!",
                        body=f"Your vacation ended on {vacation.end_date.strftime('%d %b %Y')}. Your {resumed_sub_count} subscription(s) have resumed deliveries.",
                        notification_type="subscription",
                        data={
                            "action": "vacation_completed",
                            "vacation_id": vacation.id,
                        },
                    )

                    for partner in affected_partner_ids:
                        send_notification_to_user(
                            user=partner,
                            title="Vacation Completed - Deliveries Resumed",
                            body=f"Customer {customer.get_full_name() or customer.mobile_number}'s vacation ended. Deliveries have resumed.",
                            notification_type="delivery",
                            data={
                                "action": "customer_vacation_resumed",
                                "customer_id": customer.id,
                                "customer_phone": customer.mobile_number,
                                "vacation_id": vacation.id,
                            },
                        )
                except Exception as notif_err:
                    logger.warning(f"Error sending vacation completion notifications for vacation {vacation.id}: {notif_err}")

                resumed_count += 1
                self.stdout.write(self.style.SUCCESS(f"Successfully resumed vacation ID {vacation.id} for {customer.mobile_number}"))

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to auto-resume vacation ID {vacation.id}: {e}", exc_info=True)
                self.stdout.write(self.style.ERROR(f"Error resuming vacation ID {vacation.id}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(f"Done. Resumed {resumed_count} vacation(s). Errors: {error_count}.")
        )
