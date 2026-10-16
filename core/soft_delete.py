from datetime import timedelta
import logging
from django.conf import settings
from django.contrib.auth.models import UserManager
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_retention_days():
    """
    Returns the configured Recycle Bin retention days from SystemSetting,
    defaulting to 30 days if not set or invalid.
    """
    try:
        from accounts.models import SystemSetting
        setting = SystemSetting.objects.filter(key="recycle_bin_retention_days").first()
        if setting and setting.value:
            val = int(str(setting.value).strip())
            if val > 0:
                return val
    except Exception:
        pass
    return 30


class SoftDeleteQuerySet(models.QuerySet):
    """
    Custom QuerySet supporting soft deletion and restore operations.
    """
    def delete(self, hard=False, deleted_by=None):
        if hard:
            return super().delete()
        now = timezone.now()
        return self.update(is_deleted=True, deleted_at=now, deleted_by=deleted_by)

    def hard_delete(self):
        return super().delete()

    def restore(self):
        return self.update(is_deleted=False, deleted_at=None, deleted_by=None)

    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """
    Default manager returning only active (non-deleted) records.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class RecycleBinManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """
    Manager returning only soft-deleted records for the Recycle Bin.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=True)


class SoftDeleteUserManager(UserManager.from_queryset(SoftDeleteQuerySet)):
    """
    Custom User Manager combining Django's auth UserManager with soft-delete filtering.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleteModel(models.Model):
    """
    Abstract base model providing soft delete functionality and audit fields.
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Admin user who soft-deleted this record",
    )

    # Standard managers
    objects = SoftDeleteManager()
    all_objects = models.Manager.from_queryset(SoftDeleteQuerySet)()
    deleted_objects = RecycleBinManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False, deleted_by=None):
        """
        Soft-delete by default. Call with hard=True for physical DB removal.
        """
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        update_fields = ["is_deleted", "deleted_at", "deleted_by"]
        if hasattr(self, "is_active"):
            self.is_active = False
            update_fields.append("is_active")
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=update_fields)
        return 1, {self._meta.label: 1}

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """
        Restores a soft-deleted record back to active status.
        """
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        update_fields = ["is_deleted", "deleted_at", "deleted_by"]
        if hasattr(self, "is_active"):
            self.is_active = True
            update_fields.append("is_active")
        self.save(update_fields=update_fields)
        return self

    @property
    def scheduled_permanent_deletion_date(self):
        """
        Calculates the timestamp when retention expires based on current settings.
        """
        if not self.deleted_at:
            return None
        days = get_retention_days()
        return self.deleted_at + timedelta(days=days)

    @property
    def remaining_retention_days(self):
        """
        Calculates whole days remaining until permanent deletion eligibility.
        """
        scheduled = self.scheduled_permanent_deletion_date
        if not scheduled:
            return None
        now = timezone.now()
        diff = scheduled - now
        return max(0, diff.days if diff.total_seconds() > 0 else 0)

    @property
    def is_eligible_for_purge(self):
        """
        True if retention period has fully expired.
        """
        scheduled = self.scheduled_permanent_deletion_date
        if not scheduled:
            return False
        return timezone.now() >= scheduled
