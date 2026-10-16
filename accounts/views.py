from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .models import Address, DeviceToken, Notification, Referral, User
from .serializers import (
    AddressSerializer,
    ApplyReferralSerializer,
    DeviceTokenSerializer,
    NotificationSerializer,
    ProfileCompletionSerializer,
    ProfileSerializer,
    ReferralItemSerializer,
    SendOTPSerializer,
    VerifyOTPSerializer,
)


class SendOTPView(APIView):
    serializer_class = SendOTPSerializer

    @extend_schema(
        summary="Send OTP to mobile number",
        description="Generates a 6-digit OTP and sends it to the provided mobile number. For now, the OTP is printed to the console (mock).",
        examples=[
            OpenApiExample("Example", value={"mobile_number": "9876543210"}),
        ],
        responses={200: {"msg": "OTP sent successfully."}},
    )
    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile_number = serializer.validated_data["mobile_number"]
        otp_code, success, message = serializer.create_otp(mobile_number)

        if not success:
            return Response(
                {"error": message or "Failed to deliver OTP SMS via provider."},
                status=400,
            )

        return Response({"msg": message or "OTP sent successfully."}, status=200)


class VerifyOTPView(APIView):
    serializer_class = VerifyOTPSerializer

    @extend_schema(
        summary="Verify OTP and login",
        description='Verifies the OTP sent to the mobile number. If the user does not exist, a new account is automatically created with role "customer".',
        examples=[
            OpenApiExample(
                "Example", value={"mobile_number": "9876543210", "otp": "123456"}
            ),
        ],
    )
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, created = serializer.get_or_create_user(serializer.validated_data)

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "msg": (
                    "Login successful."
                    if not created
                    else "Account created and login successful."
                ),
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "mobile_number": user.mobile_number,
                    "role": user.role,
                    "referral_code": user.referral_code,
                    "username": user.username,
                },
            },
            status=200,
        )


class ApplyReferralView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ApplyReferralSerializer

    @extend_schema(
        summary="Apply a referral code",
        description="Apply another customer's referral code. Can only be done once per account.",
        examples=[
            OpenApiExample("Example", value={"referral_code": "DD8K2P91A"}),
        ],
    )
    def post(self, request):
        serializer = ApplyReferralSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        referral = serializer.apply(request.user)
        return Response(
            {
                "message": "Referral applied successfully.",
                "referral_code": referral.referral_code,
                "discount": int(referral.reward_amount),
            },
            status=200,
        )


class MyReferralsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="View my referrals",
        description="Get statistics and list of referrals for the authenticated customer.",
    )
    def get(self, request):
        user = request.user
        referral_code = user.referral_code or ""

        qs = Referral.objects.filter(referrer=user).order_by("-created_at")
        total_referrals = qs.count()
        successful_referrals = qs.filter(status="successful").count()
        pending_referrals = qs.filter(status="pending").count()

        total_rewards = sum(r.reward_amount for r in qs.filter(status="successful"))

        serializer = ReferralItemSerializer(qs, many=True)
        return Response(
            {
                "referral_code": referral_code,
                "total_referrals": total_referrals,
                "successful_referrals": successful_referrals,
                "pending_referrals": pending_referrals,
                "total_rewards": float(total_rewards),
                "referrals": serializer.data,
            },
            status=200,
        )


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    @extend_schema(
        summary="Get my profile",
        description="Retrieve the authenticated user's profile information including profile completion percentage.",
    )
    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return Response(
            {
                "msg": "Profile fetched successfully.",
                "profile": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Update my profile",
        description="Update the authenticated user's profile information. Only provided fields will be updated.",
    )
    def put(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Profile updated successfully.",
                "profile": serializer.data,
            },
            status=200,
        )


class ProfileCompletionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Check profile completion",
        description="Returns the profile completion percentage along with filled and missing fields.",
    )
    def get(self, request):
        user = request.user
        all_fields = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "profile_picture": user.profile_picture,
            "date_of_birth": user.date_of_birth,
            "has_address": user.addresses.exists(),
        }
        filled = [field for field, value in all_fields.items() if value]
        missing = [field for field, value in all_fields.items() if not value]
        return Response(
            {
                "msg": "Profile completion fetched successfully.",
                "profile_completion": user.profile_completion,
                "filled_fields": filled,
                "missing_fields": missing,
            },
            status=200,
        )


class AddressListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AddressSerializer

    @extend_schema(
        summary="List all addresses",
        description="Get all addresses for the authenticated user.",
    )
    def get(self, request):
        addresses = Address.objects.filter(user=request.user)
        serializer = AddressSerializer(addresses, many=True)
        return Response(
            {
                "msg": "Addresses fetched successfully.",
                "addresses": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Add a new address",
        description="Create a new address for the authenticated user.",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "label": "home",
                    "house_number": "Flat 101, Sunshine Apartments",
                    "street": "MG Road",
                    "area": "Near City Mall",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "pincode": "400001",
                    "country": "India",
                    "latitude": 19.0760,
                    "longitude": 72.8777,
                    "is_default": True,
                },
            ),
        ],
    )
    def post(self, request):
        serializer = AddressSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Address added successfully.",
                "address": serializer.data,
            },
            status=201,
        )


class AddressDetailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AddressSerializer

    def get_object(self):
        address_id = self.kwargs.get("pk")
        try:
            return Address.objects.get(id=address_id, user=self.request.user)
        except Address.DoesNotExist:
            return None

    @extend_schema(
        summary="Get a single address",
        description="Retrieve a specific address by ID.",
    )
    def get(self, request, pk):
        address = self.get_object()
        if not address:
            return Response({"msg": "Address not found."}, status=404)
        serializer = AddressSerializer(address)
        return Response(
            {
                "msg": "Address fetched successfully.",
                "address": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Update an address",
        description="Update a specific address by ID.",
    )
    def put(self, request, pk):
        address = self.get_object()
        if not address:
            return Response({"msg": "Address not found."}, status=404)
        serializer = AddressSerializer(
            address, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Address updated successfully.",
                "address": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Delete an address",
        description="Delete a specific address by ID.",
    )
    def delete(self, request, pk):
        address = self.get_object()
        if not address:
            return Response({"msg": "Address not found."}, status=404)
        address.delete()
        return Response({"msg": "Address deleted successfully."}, status=200)


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List my notifications",
        description="Get all notifications for the authenticated user.",
    )
    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        serializer = NotificationSerializer(notifications, many=True)
        return Response(
            {
                "msg": "Notifications fetched successfully.",
                "total": notifications.count(),
                "unread_count": notifications.filter(is_read=False).count(),
                "notifications": serializer.data,
            },
            status=200,
        )


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mark a notification as read",
        description="Mark a specific notification as read.",
    )
    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response({"msg": "Notification not found."}, status=404)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response({"msg": "Notification marked as read."}, status=200)


class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mark all notifications as read",
        description="Mark all unread notifications as read.",
    )
    def post(self, request):
        updated = Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True
        )
        return Response(
            {
                "msg": f"{updated} notification(s) marked as read.",
            },
            status=200,
        )


class ClearAllNotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Clear all notifications",
        description="Delete all notifications for the authenticated user.",
    )
    def delete(self, request):
        deleted_count, _ = Notification.objects.filter(user=request.user).delete()
        return Response(
            {
                "msg": f"{deleted_count} notification(s) cleared successfully.",
                "deleted_count": deleted_count,
            },
            status=200,
        )


import razorpay
from decimal import Decimal
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone
from .models import Wallet, WalletTransaction


class GetWalletView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get Customer Wallet Balance")
    def get(self, request):
        if request.user.role != "customer":
            return Response(
                {"msg": "Wallet feature is available for customers only."}, status=403
            )
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        return Response(
            {
                "balance": str(wallet.balance),
                "currency": "INR",
            },
            status=200,
        )


class CreateWalletTopupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Create Razorpay order for wallet top-up")
    def post(self, request):
        if request.user.role != "customer":
            return Response(
                {"msg": "Wallet top-up is available for customers only."}, status=403
            )

        amount_raw = request.data.get("amount")
        if not amount_raw:
            return Response({"msg": "Amount is required."}, status=400)

        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {"msg": "Please enter a valid positive amount."}, status=400
            )

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        amount_in_paise = int(amount * 100)
        timestamp = int(timezone.now().timestamp())
        order_id = f"order_topup_{user_id if (user_id := getattr(request.user, 'id', None)) else '0'}_{timestamp}"

        key_id = getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_mockkey12345")
        key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "mock_secret")

        try:
            client = razorpay.Client(auth=(key_id, key_secret))
            razorpay_order = client.order.create(
                {
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": f"topup_{request.user.id}_{timestamp}",
                }
            )
            order_id = razorpay_order["id"]
        except Exception:
            pass

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="credit",
            amount=amount,
            status="pending",
            razorpay_order_id=order_id,
            description="Wallet Top-up",
        )

        return Response(
            {
                "order_id": order_id,
                "amount": amount_in_paise,
                "currency": "INR",
                "key_id": key_id,
            },
            status=200,
        )


class VerifyWalletTopupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Verify Razorpay payment and credit customer wallet")
    def post(self, request):
        if request.user.role != "customer":
            return Response(
                {"msg": "Wallet top-up is available for customers only."}, status=403
            )

        razorpay_order_id = request.data.get("razorpay_order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")

        if not razorpay_order_id or not razorpay_payment_id:
            return Response(
                {"msg": "razorpay_order_id and razorpay_payment_id are required."},
                status=400,
            )

        with db_transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            tx = WalletTransaction.objects.filter(
                wallet=wallet, razorpay_order_id=razorpay_order_id
            ).first()

            if not tx:
                return Response(
                    {"msg": "Transaction for this order ID was not found."}, status=404
                )

            # Idempotency check: prevent duplicate credit
            if tx.status == "success":
                return Response(
                    {
                        "message": "Payment already processed.",
                        "balance": str(wallet.balance),
                    },
                    status=200,
                )

            key_id = getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_mockkey12345")
            key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "mock_secret")

            if razorpay_signature and not razorpay_order_id.startswith("order_topup_"):
                try:
                    client = razorpay.Client(auth=(key_id, key_secret))
                    client.utility.verify_payment_signature(
                        {
                            "razorpay_order_id": razorpay_order_id,
                            "razorpay_payment_id": razorpay_payment_id,
                            "razorpay_signature": razorpay_signature,
                        }
                    )
                except Exception:
                    tx.status = "failed"
                    tx.save(update_fields=["status"])
                    return Response(
                        {"msg": "Invalid payment signature verification failed."},
                        status=400,
                    )

            tx.status = "success"
            tx.razorpay_payment_id = razorpay_payment_id
            tx.save(update_fields=["status", "razorpay_payment_id"])

            wallet.balance += tx.amount
            wallet.save(update_fields=["balance", "updated_at"])

            request.user.wallet_balance = wallet.balance
            request.user.save(update_fields=["wallet_balance"])

            Notification.objects.create(
                user=request.user,
                title="Wallet Recharged",
                message=f"₹{tx.amount} credited to your DudhDairy wallet.",
                notification_type="payment",
            )

            return Response(
                {
                    "message": "Wallet recharge successful.",
                    "balance": str(wallet.balance),
                    "transaction": {
                        "id": tx.id,
                        "amount": str(tx.amount),
                        "status": "success",
                    },
                },
                status=200,
            )


class WalletTransactionHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get Wallet Transaction History")
    def get(self, request):
        if request.user.role != "customer":
            return Response(
                {"msg": "Wallet transactions are available for customers only."},
                status=403,
            )
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        txs = WalletTransaction.objects.filter(wallet=wallet).order_by("-created_at")

        data = [
            {
                "id": tx.id,
                "type": tx.transaction_type,
                "amount": str(tx.amount),
                "status": tx.status,
                "description": tx.description
                or ("Wallet Top-up" if tx.transaction_type == "credit" else "Payment"),
                "created_at": tx.created_at.isoformat(),
            }
            for tx in txs
        ]

        return Response({"transactions": data}, status=200)


class RazorpayWebhookView(APIView):
    permission_classes = []

    @extend_schema(summary="Razorpay Payment Webhook (Disabled - Cash Only)")
    def post(self, request):
        return Response(
            {"msg": "Online payments and webhooks are disabled. DudhDairy is strictly Cash Only."},
            status=410,
        )


class DeviceTokenView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DeviceTokenSerializer

    @extend_schema(
        summary="Register or update device FCM token",
        description="Registers or updates FCM device token for authenticated user.",
    )
    def post(self, request):
        user = request.user
        token = request.data.get("token")
        platform = request.data.get("platform", "android")

        if not token:
            return Response({"msg": "Token is required."}, status=400)

        device_token, created = DeviceToken.objects.update_or_create(
            token=token,
            defaults={
                "user": user,
                "platform": platform,
                "is_active": True,
            },
        )

        serializer = DeviceTokenSerializer(device_token)
        return Response(
            {
                "msg": "Device token registered successfully." if created else "Device token updated successfully.",
                "device_token": serializer.data,
            },
            status=201 if created else 200,
        )

    @extend_schema(
        summary="Deactivate device FCM token on logout",
        description="Deactivates FCM token for authenticated user on logout.",
    )
    def delete(self, request):
        user = request.user
        token = request.data.get("token") or request.query_params.get("token")

        if token:
            DeviceToken.objects.filter(user=user, token=token).update(is_active=False)
        else:
            DeviceToken.objects.filter(user=user).update(is_active=False)

        return Response({"msg": "Device token deactivated successfully."}, status=200)
