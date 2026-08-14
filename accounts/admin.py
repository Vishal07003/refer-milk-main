from django.contrib import admin

from .models import Address, DeliveryBoyProfile, Notification, OTP, Referral, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "mobile_number",
        "username",
        "role",
        "first_name",
        "last_name",
        "email",
        "referral_code",
        "is_active",
    )
    list_filter = ("role", "is_active", "gender")
    search_fields = (
        "mobile_number",
        "username",
        "referral_code",
        "first_name",
        "last_name",
        "email",
    )
    ordering = ("-date_joined",)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "referrer",
        "referred_user",
        "referral_code",
        "status",
        "reward_amount",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "referrer__mobile_number",
        "referred_user__mobile_number",
        "referral_code",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "label",
        "house_number",
        "street",
        "city",
        "state",
        "pincode",
        "is_default",
    )
    list_filter = ("label", "is_default", "city", "state")
    search_fields = ("user__mobile_number", "house_number", "street", "city", "pincode")
    ordering = ("-is_default", "-created_at")


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("id", "mobile_number", "otp", "created_at", "is_used")
    list_filter = ("is_used",)
    search_fields = ("mobile_number",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(DeliveryBoyProfile)
class DeliveryBoyProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "vehicle_number",
        "is_available",
        "zone",
        "created_at",
    )
    list_filter = ("is_available", "zone")
    search_fields = ("user__mobile_number", "vehicle_number", "zone")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read")
    search_fields = ("user__mobile_number", "title", "message")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
