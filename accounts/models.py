from datetime import timedelta
import secrets
import string

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from core.soft_delete import (
    SoftDeleteUserManager,
    SoftDeleteQuerySet,
    RecycleBinManager,
    get_retention_days,
)


class User(AbstractUser):
    ROLE_CHOICES = (
        ("customer", "Customer"),
        ("delivery_boy", "Delivery Boy"),
        ("admin", "Admin"),
    )

    GENDER_CHOICES = (
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    )

    mobile_number = models.CharField(max_length=15, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer")
    referral_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
    )

    email = models.EmailField(max_length=255, blank=True, default="")
    is_mobile_verified = models.BooleanField(default=False, help_text="Designates whether the user's mobile number is verified.")
    is_email_verified = models.BooleanField(default=False, help_text="Designates whether the user's recovery email is verified.")
    profile_picture = models.ImageField(
        upload_to="profile_pictures/", blank=True, null=True
    )
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(
        max_length=10, choices=GENDER_CHOICES, blank=True, default=""
    )
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Soft Delete Fields
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Admin who soft-deleted this user",
    )

    # Custom managers
    objects = SoftDeleteUserManager()
    all_objects = models.Manager.from_queryset(SoftDeleteQuerySet)()
    deleted_objects = RecycleBinManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def delete(self, using=None, keep_parents=False, hard=False, deleted_by=None):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.is_active = False  # Deactivate credentials/tokens immediately
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=["is_deleted", "is_active", "deleted_at", "deleted_by"])
        return 1, {self._meta.label: 1}

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.is_active = True
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "is_active", "deleted_at", "deleted_by"])
        return self

    def save(self, *args, **kwargs):
        if self.role == "customer" and (
            self.referral_code is None or not str(self.referral_code).strip()
        ):
            self.referral_code = self.generate_referral_code()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_referral_code():
        while True:
            code = "DD" + "".join(
                secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
            )
            if not User.objects.filter(referral_code=code).exists():
                return code

    @property
    def profile_completion(self):
        fields = {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "profile_picture": self.profile_picture,
            "date_of_birth": self.date_of_birth,
            "has_address": self.addresses.exists(),
        }
        filled = sum(1 for value in fields.values() if value)
        total = len(fields)
        return round((filled / total) * 100)

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

    def __str__(self):
        return f"{self.mobile_number} ({self.get_role_display()})"


class DeliveryBoyProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="delivery_profile"
    )
    vehicle_number = models.CharField(max_length=20, blank=True, default="")
    is_available = models.BooleanField(default=True)
    zone = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Delivery Boy Profile"
        verbose_name_plural = "Delivery Boy Profiles"

    def __str__(self):
        return f"{self.user.mobile_number} - {self.zone or 'No Zone'}"


class Address(models.Model):
    LABEL_CHOICES = (
        ("home", "Home"),
        ("work", "Work"),
        ("other", "Other"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=20, choices=LABEL_CHOICES, default="home")
    house_number = models.CharField(max_length=50)
    street = models.CharField(max_length=255)
    area = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    country = models.CharField(max_length=50, default="India")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Address"
        verbose_name_plural = "Addresses"
        ordering = ["-is_default", "-created_at"]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label}: {self.house_number}, {self.street}, {self.city}"


class Notification(models.Model):
    TYPE_CHOICES = (
        ("subscription", "Subscription"),
        ("payment", "Payment"),
        ("referral", "Referral"),
        ("general", "General"),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="general"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.mobile_number} - {self.title}"


class OTP(models.Model):
    mobile_number = models.CharField(max_length=15, db_index=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.mobile_number} - {self.otp}"


class Referral(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("successful", "Successful"),
        ("failed", "Failed"),
    )

    referrer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="referrals_given"
    )
    referred_user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="referral_received"
    )
    referral_code = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="successful"
    )
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=50.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Referral"
        verbose_name_plural = "Referrals"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.referrer.mobile_number} referred {self.referred_user.mobile_number} ({self.status})"


class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"

    def __str__(self):
        return f"Wallet for {self.user.mobile_number} - Balance: ₹{self.balance}"


class WalletTransaction(models.Model):
    TYPE_CHOICES = (
        ("credit", "Credit"),
        ("debit", "Debit"),
    )

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    )

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    razorpay_order_id = models.CharField(max_length=255, blank=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Wallet Transaction"
        verbose_name_plural = "Wallet Transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transaction_type.upper()} ₹{self.amount} ({self.status}) - {self.wallet.user.mobile_number}"


class DeviceToken(models.Model):
    PLATFORM_CHOICES = (
        ("android", "Android"),
        ("ios", "iOS"),
        ("web", "Web"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="device_tokens")
    token = models.CharField(max_length=255, unique=True, db_index=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default="android")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Device Token"
        verbose_name_plural = "Device Tokens"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.mobile_number} - {self.platform} - {'Active' if self.is_active else 'Inactive'}"


class SystemSetting(models.Model):
    """
    Key-Value system settings for DudhDairy platform (cash discount, delivery slot windows, etc.)
    """
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.CharField(max_length=255, blank=True, default='')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_settings')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}: {self.value}"


class AdminAuditLog(models.Model):
    """
    Immutable audit log recording admin actions, status transitions, and data changes.
    """
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    module = models.CharField(max_length=50)  # customers, products, orders, cash_collection, etc.
    action = models.CharField(max_length=50)  # create, update, delete, status_change, verify, reconcile
    target_id = models.CharField(max_length=50, blank=True, default='')
    details = models.TextField(blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Admin Audit Log"
        verbose_name_plural = "Admin Audit Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.user} - {self.module}:{self.action}"


class AdminPasswordResetSession(models.Model):
    """
    Dedicated, secure OTP and verification session model for Admin Password Recovery.
    Features:
    - User foreign key linked directly to eligible administrator account.
    - Cryptographic SHA-256 hash storage of OTP (never stored plaintext).
    - Expiry timestamp (5 minutes).
    - Failed attempt counter (max 5 attempts before invalidation).
    - Verification flag and temporary reset authorization token.
    - Reset authorization token expires in 15 minutes.
    - One-time atomic consumption flag (is_consumed).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_reset_sessions")
    mobile_number = models.CharField(max_length=15, db_index=True)
    otp_hash = models.CharField(max_length=128)
    attempts_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    is_verified = models.BooleanField(default=False)
    reset_token = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    is_consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    reset_token_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Admin Password Reset Session"
        verbose_name_plural = "Admin Password Reset Sessions"
        ordering = ["-created_at"]

    @classmethod
    def hash_otp(cls, otp_code: str) -> str:
        import hashlib
        return hashlib.sha256(str(otp_code).encode("utf-8")).hexdigest()

    def check_otp(self, input_otp: str) -> bool:
        import hmac
        expected = self.otp_hash
        candidate = self.hash_otp(input_otp)
        return hmac.compare_digest(expected, candidate)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_reset_token_expired(self) -> bool:
        if not self.reset_token_expires_at:
            return True
        return timezone.now() > self.reset_token_expires_at

    def __str__(self):
        return f"AdminResetSession({self.user.username}, verified={self.is_verified}, consumed={self.is_consumed})"


class AdminContactVerificationChallenge(models.Model):
    """
    Challenge session for verifying new mobile number or recovery email during
    admin contact setup or contact change.
    Features:
    - Dedicated challenge type: 'mobile' or 'email'.
    - Stores candidate contact value (target_value) without mutating the user record prematurely.
    - Cryptographically hashed OTP (never plaintext).
    - Failed attempt tracking (max 5).
    - Expiry timestamp (5 minutes for OTP, 15 minutes for email token).
    - Single-use consumption flag (is_consumed).
    """
    CHALLENGE_TYPES = (
        ("mobile", "Mobile Number Verification"),
        ("email", "Email Verification"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contact_verification_challenges")
    challenge_type = models.CharField(max_length=20, choices=CHALLENGE_TYPES)
    target_value = models.CharField(max_length=255, help_text="New mobile number or recovery email being verified")
    otp_hash = models.CharField(max_length=128)
    token = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    attempts_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    is_verified = models.BooleanField(default=False)
    is_consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "Admin Contact Verification Challenge"
        verbose_name_plural = "Admin Contact Verification Challenges"
        ordering = ["-created_at"]

    @classmethod
    def hash_otp(cls, otp_code: str) -> str:
        import hashlib
        return hashlib.sha256(str(otp_code).encode("utf-8")).hexdigest()

    def check_otp(self, input_otp: str) -> bool:
        import hmac
        expected = self.otp_hash
        candidate = self.hash_otp(input_otp)
        return hmac.compare_digest(expected, candidate)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"ContactChallenge({self.user.username}, type={self.challenge_type}, verified={self.is_verified})"

