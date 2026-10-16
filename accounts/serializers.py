import random

from django.utils import timezone
from rest_framework import serializers

from .models import Address, DeviceToken, Notification, OTP, Referral, User


class SendOTPSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(max_length=15)

    def validate_mobile_number(self, value):
        digits_only = "".join(filter(str.isdigit, value))
        if len(digits_only) < 10:
            raise serializers.ValidationError("Invalid mobile number.")
        if User.all_objects.filter(mobile_number=value, is_deleted=True).exists():
            raise serializers.ValidationError("This account has been deleted or deactivated. Please contact support.")
        return value

    def create_otp(self, mobile_number):
        from .sms_service import send_sms_otp_via_2factor

        OTP.objects.filter(mobile_number=mobile_number, is_used=False).update(
            is_used=True
        )
        otp_code = f"{random.randint(100000, 999999)}"
        otp = OTP.objects.create(mobile_number=mobile_number, otp=otp_code)

        # Dispatch via 2Factor SMS gateway
        success, message, session_id = send_sms_otp_via_2factor(mobile_number, otp_code)
        return otp_code, success, message


class VerifyOTPSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(max_length=15)
    otp = serializers.CharField(max_length=6)

    def validate(self, attrs):
        mobile_number = attrs["mobile_number"]
        otp_code = attrs["otp"]

        otp = OTP.objects.filter(
            mobile_number=mobile_number, otp=otp_code, is_used=False
        ).first()

        if not otp:
            raise serializers.ValidationError({"msg": "Invalid or expired OTP."})

        if otp.created_at < timezone.now() - timezone.timedelta(minutes=5):
            raise serializers.ValidationError(
                {"msg": "OTP has expired. Please request a new one."}
            )

        # Check if an account with this mobile number is soft-deleted
        deleted_user = User.all_objects.filter(mobile_number=mobile_number, is_deleted=True).first()
        if deleted_user:
            raise serializers.ValidationError(
                {"msg": "This account has been deleted or deactivated. Please contact support."}
            )

        attrs["otp_obj"] = otp
        return attrs

    def get_or_create_user(self, validated_data):
        mobile_number = validated_data["mobile_number"]
        otp_obj = validated_data["otp_obj"]

        # Ensure we check all_objects for soft-deleted users
        if User.all_objects.filter(mobile_number=mobile_number, is_deleted=True).exists():
            raise serializers.ValidationError(
                {"msg": "This account has been deleted or deactivated. Please contact support."}
            )

        user, created = User.objects.get_or_create(
            mobile_number=mobile_number,
            defaults={"username": mobile_number, "role": "customer"},
        )
        otp_obj.is_used = True
        otp_obj.save()

        return user, created


class ApplyReferralSerializer(serializers.Serializer):
    referral_code = serializers.CharField(max_length=20)

    def validate_referral_code(self, value):
        code = value.strip()
        referrer = User.objects.filter(referral_code=code, role="customer").first()
        if not referrer:
            raise serializers.ValidationError("Invalid referral code.")
        return code

    def validate(self, attrs):
        user = self.context["request"].user
        if user.role != "customer":
            raise serializers.ValidationError(
                {"msg": "Only customers can participate in the referral program."}
            )

        code = attrs["referral_code"]
        referrer = User.objects.filter(referral_code=code, role="customer").first()
        if not referrer:
            raise serializers.ValidationError({"msg": "Invalid referral code."})

        if user.id == referrer.id or user.referral_code == code:
            raise serializers.ValidationError({"msg": "You cannot refer yourself."})

        if (
            Referral.objects.filter(referred_user=user).exists()
            or user.referred_by is not None
        ):
            raise serializers.ValidationError(
                {"msg": "You have already applied a referral code."}
            )

        attrs["referrer"] = referrer
        return attrs

    def apply(self, user):
        referrer = self.validated_data["referrer"]
        code = self.validated_data["referral_code"]

        referral, _ = Referral.objects.get_or_create(
            referred_user=user,
            defaults={
                "referrer": referrer,
                "referral_code": code,
                "status": "successful",
                "reward_amount": 50.00,
            },
        )
        if user.referred_by != referrer:
            user.referred_by = referrer
            user.save(update_fields=["referred_by"])

        return referral


class ReferralItemSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d", read_only=True)

    class Meta:
        model = Referral
        fields = ("id", "status", "reward_amount", "created_at")


class ProfileSerializer(serializers.ModelSerializer):
    profile_completion = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "mobile_number",
            "role",
            "referral_code",
            "first_name",
            "last_name",
            "email",
            "profile_picture",
            "date_of_birth",
            "gender",
            "wallet_balance",
            "profile_completion",
        )
        read_only_fields = (
            "id",
            "username",
            "mobile_number",
            "role",
            "referral_code",
            "wallet_balance",
            "profile_completion",
        )

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ProfileCompletionSerializer(serializers.Serializer):
    profile_completion = serializers.IntegerField()
    filled_fields = serializers.ListField(child=serializers.CharField())
    missing_fields = serializers.ListField(child=serializers.CharField())


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id",
            "label",
            "house_number",
            "street",
            "area",
            "city",
            "state",
            "pincode",
            "country",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            for coord in ("latitude", "longitude"):
                if data.get(coord) is not None:
                    try:
                        data[coord] = round(float(data[coord]), 6)
                    except (ValueError, TypeError):
                        pass
        return super().to_internal_value(data)

    def validate(self, attrs):
        user = self.context["request"].user
        if (
            attrs.get("is_default")
            and not Address.objects.filter(user=user, is_default=True).exists()
        ):
            pass
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["user"] = user
        if validated_data.get("is_default", True):
            Address.objects.filter(user=user).update(is_default=False)
        return super().create(validated_data)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "message",
            "notification_type",
            "is_read",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ("id", "token", "platform", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "is_active", "created_at", "updated_at")
