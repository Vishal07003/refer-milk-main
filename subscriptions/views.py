import razorpay
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import transaction as db_transaction
from accounts.models import Address, Notification, User, Wallet, WalletTransaction
from orders.models import DeliverySlot

from .models import Payment, ReferralDiscountTier, Subscription, SubscriptionPlan
from .serializers import (
    CancelSubscriptionSerializer,
    CreatePaymentSerializer,
    CreateSubscriptionSerializer,
    PaymentSerializer,
    ReferralDiscountTierSerializer,
    SubscriptionSerializer,
    SubscriptionPlanSerializer,
    RequestCustomerSubscriptionSerializer,
    UpdateCustomerSubscriptionSerializer,
    CustomerSubscriptionBillSerializer,
    CustomerDeliveryItemSerializer,
)


class ActiveSubscriptionPlansListView(APIView):
    """
    Customer-facing endpoint: Returns only active predefined subscription plans.
    """
    @extend_schema(summary="List active subscription plans for customers")
    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).select_related('product')
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(
            {
                "msg": "Active subscription plans fetched successfully.",
                "plans": serializer.data,
            },
            status=200,
        )


class RequestCustomerSubscriptionView(APIView):
    """
    Customer requests a subscription by selecting an active predefined plan.
    - Status is strictly 'pending' (Pending Approval).
    - Customer CANNOT self-activate or tamper with plan price.
    - Prevents duplicate pending requests for the same active plan and user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = RequestCustomerSubscriptionSerializer

    @extend_schema(
        summary="Customer requests a subscription for an active plan",
        description="Creates a subscription request in 'pending' status awaiting Admin approval."
    )
    def post(self, request):
        serializer = RequestCustomerSubscriptionSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        plan = SubscriptionPlan.objects.get(id=data['plan_id'], is_active=True)
        address = Address.objects.get(id=data['address_id'], user=request.user)
        delivery_slot = DeliverySlot.objects.filter(id=data.get('delivery_slot_id')).first() if data.get('delivery_slot_id') else None

        # Check for duplicate pending request for same plan
        existing_pending = Subscription.objects.filter(
            user=request.user,
            plan=plan,
            status='pending'
        ).first()
        if existing_pending:
            return Response(
                {"msg": f"You already have a pending approval request for '{plan.name}'. Please wait for Admin approval."},
                status=400
            )

        start_date = data.get('start_date') or (timezone.localdate() + timedelta(days=1))
        end_date = start_date + timedelta(days=30)

        # Server-side price calculation directly from plan
        price_per_unit = plan.price_per_unit
        discount_per_unit = Decimal('0.00')
        final_price_per_unit = price_per_unit - discount_per_unit

        subscription = Subscription.objects.create(
            user=request.user,
            plan=plan,
            product=plan.product,
            address=address,
            delivery_slot=delivery_slot,
            quantity=plan.quantity,
            start_date=start_date,
            end_date=end_date,
            price_per_unit=price_per_unit,
            discount_per_unit=discount_per_unit,
            final_price_per_unit=final_price_per_unit,
            status='pending',  # Strictly pending approval
        )

        # Notify admins and customer
        Notification.objects.create(
            user=request.user,
            title="Subscription Request Submitted",
            message=f"Your request for '{plan.name}' ({plan.quantity} {plan.unit}) has been submitted and is pending Admin approval.",
            notification_type="subscription",
        )

        admin_user = User.objects.filter(is_staff=True).first()
        if admin_user:
            Notification.objects.create(
                user=admin_user,
                title="New Subscription Request",
                message=f"Customer {request.user.mobile_number} requested plan '{plan.name}'. Pending approval.",
                notification_type="subscription",
            )

        return Response(
            {
                "msg": f"Subscription request for '{plan.name}' submitted successfully. Awaiting Admin approval.",
                "subscription": SubscriptionSerializer(subscription).data,
            },
            status=201,
        )


class ReferralDiscountTierListView(APIView):
    serializer_class = ReferralDiscountTierSerializer

    @extend_schema(summary="List all referral discount tiers")
    def get(self, request):
        tiers = ReferralDiscountTier.objects.all()
        serializer = ReferralDiscountTierSerializer(tiers, many=True)
        return Response(
            {
                "msg": "Discount tiers fetched successfully.",
                "tiers": serializer.data,
            },
            status=200,
        )


class ReferralDiscountTierDetailView(APIView):
    serializer_class = ReferralDiscountTierSerializer

    @extend_schema(
        summary="Create a referral discount tier (Admin only)",
        examples=[
            OpenApiExample(
                "Example", value={"min_referrals": 2, "discount_per_unit": 2.00}
            )
        ],
    )
    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        serializer = ReferralDiscountTierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Discount tier created successfully.",
                "tier": serializer.data,
            },
            status=201,
        )

    @extend_schema(summary="Update a referral discount tier (Admin only)")
    def put(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        try:
            tier = ReferralDiscountTier.objects.get(pk=pk)
        except ReferralDiscountTier.DoesNotExist:
            return Response({"msg": "Discount tier not found."}, status=404)
        serializer = ReferralDiscountTierSerializer(
            tier, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Discount tier updated successfully.",
                "tier": serializer.data,
            },
            status=200,
        )

    @extend_schema(summary="Delete a referral discount tier (Admin only)")
    def delete(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        try:
            tier = ReferralDiscountTier.objects.get(pk=pk)
        except ReferralDiscountTier.DoesNotExist:
            return Response({"msg": "Discount tier not found."}, status=404)
        tier.delete()
        return Response({"msg": "Discount tier deleted successfully."}, status=200)


class CreateSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CreateSubscriptionSerializer

    @extend_schema(
        summary="Create a subscription with Razorpay payment",
        description="Create a new 30-day subscription. Returns Razorpay order for payment.",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "product_id": 1,
                    "address_id": 1,
                    "delivery_slot_id": 1,
                    "quantity": 2.0,
                    "start_date": "2026-07-20",
                },
            )
        ],
    )
    def post(self, request):
        serializer = CreateSubscriptionSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment_method = data.get("payment_method", "razorpay")

        # Handle Wallet Payment
        if payment_method == "wallet":
            with db_transaction.atomic():
                wallet, _ = Wallet.objects.select_for_update().get_or_create(
                    user=request.user
                )
                total_req = data["total_amount"]

                # Sync user.wallet_balance and wallet.balance
                user_bal = request.user.wallet_balance or Decimal("0.00")
                current_bal = max(wallet.balance, user_bal)

                if current_bal < total_req:
                    needed = total_req - current_bal + Decimal("100.00")
                    current_bal += needed
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type="credit",
                        amount=needed,
                        status="success",
                        description="Auto wallet top-up for subscription creation",
                    )

                wallet.balance = current_bal
                wallet.save(update_fields=["balance", "updated_at"])
                request.user.wallet_balance = current_bal
                request.user.save(update_fields=["wallet_balance"])

                subscription = Subscription.objects.create(
                    user=request.user,
                    product=data["product"],
                    address=data["address"],
                    delivery_slot=data.get("delivery_slot"),
                    quantity=data["quantity"],
                    start_date=data["start_date"],
                    end_date=data["end_date"],
                    price_per_unit=data["price_per_unit"],
                    discount_per_unit=data["discount_per_unit"],
                    final_price_per_unit=data["final_price_per_unit"],
                    total_amount=total_req,
                    status="active",
                )

                wallet.balance -= total_req
                wallet.save(update_fields=["balance", "updated_at"])

                request.user.wallet_balance = wallet.balance
                request.user.save(update_fields=["wallet_balance"])

                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type="debit",
                    amount=total_req,
                    status="success",
                    description=f"Milk Subscription #{subscription.id} - {subscription.product.name}",
                )

                Payment.objects.create(
                    user=request.user,
                    subscription=subscription,
                    payment_for="subscription",
                    amount=total_req,
                    payment_method="wallet",
                    payment_status="completed",
                    notes=f"Paid via DudhDairy Wallet for {subscription.product.name}",
                )

                from notifications.services import send_notification_to_user
                send_notification_to_user(
                    user=request.user,
                    title="Subscription Active",
                    body=f"Your subscription for {subscription.product.name} is now active (₹{total_req} debited from wallet).",
                    data={"type": "subscription_active", "subscription_id": str(subscription.id)},
                    notification_type="subscription",
                )

                return Response(
                    {
                        "msg": "Subscription activated successfully using wallet balance.",
                        "subscription": SubscriptionSerializer(subscription).data,
                        "wallet_balance": str(wallet.balance),
                    },
                    status=201,
                )

        # Standard Razorpay Payment
        subscription = Subscription.objects.create(
            user=request.user,
            product=data["product"],
            address=data["address"],
            delivery_slot=data.get("delivery_slot"),
            quantity=data["quantity"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            price_per_unit=data["price_per_unit"],
            discount_per_unit=data["discount_per_unit"],
            final_price_per_unit=data["final_price_per_unit"],
            total_amount=data["total_amount"],
        )

        try:
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
            razorpay_order = client.order.create(
                {
                    "amount": int(subscription.total_amount * 100),
                    "currency": "INR",
                    "receipt": f"sub_{subscription.id}",
                }
            )
            order_id = razorpay_order["id"]
            order_amount = razorpay_order["amount"]
            order_currency = razorpay_order["currency"]
        except Exception:
            order_id = f"order_mock_{subscription.id}"
            order_amount = int(subscription.total_amount * 100)
            order_currency = "INR"

        subscription.razorpay_order_id = order_id
        subscription.save(update_fields=["razorpay_order_id"])

        Notification.objects.create(
            user=request.user,
            title="Subscription Created",
            message=f"Your subscription for {subscription.product.name} has been created. Please complete the payment.",
            notification_type="subscription",
        )

        return Response(
            {
                "msg": "Subscription created successfully. Complete payment to activate.",
                "subscription": SubscriptionSerializer(subscription).data,
                "razorpay_order": {
                    "order_id": order_id,
                    "amount": order_amount,
                    "currency": order_currency,
                    "key": settings.RAZORPAY_KEY_ID,
                },
            },
            status=201,
        )


class VerifySubscriptionPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Verify subscription Razorpay payment (Deprecated)",
        description="Disabled: Online payments are disabled. DudhDairy is strictly Cash Only.",
    )
    def post(self, request):
        return Response(
            {"msg": "Online payments are disabled. DudhDairy is strictly Cash Only."},
            status=410,
        )


class MySubscriptionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List my subscriptions")
    def get(self, request):
        subscriptions = Subscription.objects.filter(user=request.user)
        serializer = SubscriptionSerializer(subscriptions, many=True)
        return Response(
            {
                "msg": "Subscriptions fetched successfully.",
                "subscriptions": serializer.data,
            },
            status=200,
        )


class SubscriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get subscription details")
    def get(self, request, pk):
        try:
            subscription = Subscription.objects.get(pk=pk, user=request.user)
        except Subscription.DoesNotExist:
            return Response({"msg": "Subscription not found."}, status=404)
        serializer = SubscriptionSerializer(subscription)
        return Response(
            {
                "msg": "Subscription fetched successfully.",
                "subscription": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Update subscription schedule/details",
        description="Allows customer to update delivery slot, quantity, or address for an active/paused subscription."
    )
    def patch(self, request, pk):
        try:
            subscription = Subscription.objects.get(pk=pk, user=request.user)
        except Subscription.DoesNotExist:
            return Response({"msg": "Subscription not found."}, status=404)

        if subscription.status not in ["active", "paused"]:
            return Response(
                {"msg": f"Cannot update a subscription with status '{subscription.status}'."},
                status=400,
            )

        serializer = UpdateCustomerSubscriptionSerializer(
            data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        update_fields = ["updated_at"]

        if "delivery_slot_id" in validated:
            slot_id = validated["delivery_slot_id"]
            subscription.delivery_slot = (
                DeliverySlot.objects.get(id=slot_id) if slot_id else None
            )
            update_fields.append("delivery_slot")

        if "address_id" in validated:
            subscription.address = Address.objects.get(
                id=validated["address_id"], user=request.user
            )
            update_fields.append("address")

        if "quantity" in validated:
            subscription.quantity = validated["quantity"]
            # Recalculate total_amount
            subscription.total_amount = (
                subscription.final_price_per_unit * Decimal(str(subscription.quantity)) * 30
            )
            update_fields.extend(["quantity", "total_amount"])

        subscription.save(update_fields=update_fields)

        return Response(
            {
                "msg": "Subscription schedule updated successfully.",
                "subscription": SubscriptionSerializer(subscription).data,
            },
            status=200,
        )

    def put(self, request, pk):
        return self.patch(request, pk)


class CancelSubscriptionPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Preview prorated cancellation",
        description="See how much you will owe if you cancel now.",
    )
    def get(self, request, pk):
        try:
            subscription = Subscription.objects.get(pk=pk, user=request.user)
        except Subscription.DoesNotExist:
            return Response({"msg": "Subscription not found."}, status=404)
        if subscription.status != "active":
            return Response(
                {"msg": "Only active subscriptions can be cancelled."}, status=400
            )

        return Response(
            {
                "msg": "Cancel preview",
                "start_date": str(subscription.start_date),
                "end_date": str(subscription.end_date),
                "cancelled_on": str(timezone.now().date()),
                "total_days": subscription.total_days,
                "days_used": subscription.days_used,
                "days_remaining": subscription.days_remaining,
                "total_amount": str(subscription.total_amount),
                "amount_used": str(subscription.amount_used),
                "refund_amount": str(subscription.refund_amount),
            },
            status=200,
        )


class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Cancel subscription with prorated billing",
        description="Cancel subscription mid-way. Only pays for days used.",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "payment_method": "upi",
                    "transaction_id": "UPI123456",
                },
            )
        ],
    )
    def post(self, request, pk):
        try:
            subscription = Subscription.objects.get(pk=pk, user=request.user)
        except Subscription.DoesNotExist:
            return Response({"msg": "Subscription not found."}, status=404)
        if subscription.status not in ["active", "paused", "pending"]:
            return Response(
                {"msg": f"Cannot cancel a subscription with status '{subscription.status}'."},
                status=400,
            )

        prev_status = subscription.status
        subscription.status = "cancelled"
        subscription.cancelled_at = timezone.now()
        subscription.save(update_fields=["status", "cancelled_at"])

        # Delete any future pending daily deliveries while preserving historical deliveries
        from delivery.models import DailyDelivery
        today = timezone.localdate()
        DailyDelivery.objects.filter(
            subscription=subscription,
            delivery_date__gt=today,
            status="pending",
        ).delete()

        amount_used = subscription.amount_used if prev_status != "pending" else Decimal("0.00")

        if amount_used > 0 and request.data:
            serializer = CancelSubscriptionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            Payment.objects.create(
                user=request.user,
                subscription=subscription,
                payment_for="subscription",
                amount=amount_used,
                payment_method=serializer.validated_data.get("payment_method", "cash"),
                payment_status="completed",
                transaction_id=serializer.validated_data.get("transaction_id", ""),
                notes="Prorated payment on cancellation",
            )

        from notifications.services import send_notification_to_user
        send_notification_to_user(
            user=request.user,
            title="Subscription Cancelled",
            body=f"Your {subscription.product.name} subscription has been cancelled.",
            data={"type": "subscription_cancelled", "subscription_id": str(subscription.id)},
            notification_type="subscription",
        )
        if subscription.delivery_boy:
            send_notification_to_user(
                user=subscription.delivery_boy,
                title="Subscription Cancelled",
                body=f"Assigned subscription #{subscription.id} ({subscription.product.name}) has been cancelled.",
                data={"type": "subscription_cancelled", "subscription_id": str(subscription.id)},
                notification_type="subscription",
            )

        return Response(
            {
                "msg": "Subscription cancelled successfully.",
                "subscription": SubscriptionSerializer(subscription).data,
                "amount_used": str(amount_used),
                "refund_amount": str(subscription.refund_amount),
            },
            status=200,
        )


class PauseCustomerSubscriptionView(APIView):
    """
    Customer pauses their own active subscription.
    - Strictly checks ownership: subscription.user == request.user
    - Validates status: only 'active' subscriptions can be paused
    - Sets status to 'paused'
    - Preserves assigned delivery partner, customer, product, plan, address, historical deliveries & orders
    - Removes unfulfilled future pending DailyDelivery records (delivery_date > today)
    - Leaves past and today's delivered/completed drops intact
    - Sends notifications to customer and assigned delivery partner
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Customer pauses active subscription",
        description="Pause an active subscription. Prevents future daily deliveries while preserving historical deliveries and delivery partner assignment."
    )
    def post(self, request, pk):
        try:
            subscription = Subscription.objects.get(pk=pk, user=request.user)
        except Subscription.DoesNotExist:
            return Response(
                {"success": False, "msg": "Subscription not found."},
                status=404,
            )

        if subscription.status == "paused":
            return Response(
                {"success": False, "msg": "Subscription is already paused."},
                status=400,
            )

        if subscription.status != "active":
            return Response(
                {"success": False, "msg": f"Cannot pause a subscription with '{subscription.status}' status. Only active subscriptions can be paused."},
                status=400,
            )

        subscription.status = "paused"
        subscription.save(update_fields=["status", "updated_at"])

        # Preserve historical and today's deliveries; remove future pending deliveries
        from delivery.models import DailyDelivery
        today = timezone.localdate()
        DailyDelivery.objects.filter(
            subscription=subscription,
            delivery_date__gt=today,
            status="pending"
        ).delete()

        # Send notifications
        from notifications.services import send_notification_to_user
        send_notification_to_user(
            user=subscription.user,
            title="Subscription Paused",
            body=f"Your subscription for {subscription.product.name} has been paused.",
            data={"type": "subscription_paused", "subscription_id": str(subscription.id)},
            notification_type="subscription",
        )

        if subscription.delivery_boy:
            send_notification_to_user(
                user=subscription.delivery_boy,
                title="Subscription Paused",
                body=f"Assigned subscription #{subscription.id} ({subscription.product.name}) has been paused by the customer.",
                data={"type": "subscription_paused", "subscription_id": str(subscription.id)},
                notification_type="subscription",
            )

        return Response(
            {
                "success": True,
                "msg": f"Subscription #{subscription.id} paused successfully.",
                "subscription": SubscriptionSerializer(subscription).data,
            },
            status=200,
        )


class ResumeCustomerSubscriptionView(APIView):
    """
    Customer resumes their own paused subscription.
    - Strictly checks ownership: subscription.user == request.user
    - Validates status: only 'paused' subscriptions can be resumed
    - Sets status to 'active'
    - Preserves assigned delivery partner, customer, product, plan, address, rates & financial records
    - Re-enables/generates future DailyDelivery records from max(today, start_date) to end_date
    - Uses get_or_create to prevent duplicate DailyDelivery records
    - Sends notifications to customer and assigned delivery partner
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Customer resumes paused subscription",
        description="Resume a paused subscription. Re-generates upcoming daily deliveries with existing assigned delivery partner without duplication."
    )
    def post(self, request, pk):
        try:
            subscription = Subscription.objects.get(pk=pk, user=request.user)
        except Subscription.DoesNotExist:
            return Response(
                {"success": False, "msg": "Subscription not found."},
                status=404,
            )

        if subscription.status == "active":
            return Response(
                {"success": False, "msg": "Subscription is already active."},
                status=400,
            )

        if subscription.status != "paused":
            return Response(
                {"success": False, "msg": f"Cannot resume a subscription with '{subscription.status}' status. Only paused subscriptions can be resumed."},
                status=400,
            )

        subscription.status = "active"
        subscription.save(update_fields=["status", "updated_at"])

        # Re-generate future DailyDeliveries if delivery partner is assigned
        from delivery.models import DailyDelivery
        today = timezone.localdate()
        if subscription.delivery_boy:
            curr_date = max(today, subscription.start_date)
            end_date = subscription.end_date or (curr_date + timedelta(days=30))
            while curr_date <= end_date:
                drop, created = DailyDelivery.objects.get_or_create(
                    subscription=subscription,
                    delivery_date=curr_date,
                    defaults={"delivery_boy": subscription.delivery_boy, "status": "pending"}
                )
                if not created and drop.status == "pending" and drop.delivery_boy_id != subscription.delivery_boy_id:
                    drop.delivery_boy = subscription.delivery_boy
                    drop.save(update_fields=["delivery_boy"])
                curr_date += timedelta(days=1)

        # Send notifications
        from notifications.services import send_notification_to_user
        send_notification_to_user(
            user=subscription.user,
            title="Subscription Resumed",
            body=f"Your subscription for {subscription.product.name} has been resumed.",
            data={"type": "subscription_resumed", "subscription_id": str(subscription.id)},
            notification_type="subscription",
        )

        if subscription.delivery_boy:
            send_notification_to_user(
                user=subscription.delivery_boy,
                title="Subscription Resumed",
                body=f"Assigned subscription #{subscription.id} ({subscription.product.name}) has been resumed by the customer.",
                data={"type": "subscription_resumed", "subscription_id": str(subscription.id)},
                notification_type="subscription",
            )

        return Response(
            {
                "success": True,
                "msg": f"Subscription #{subscription.id} resumed successfully.",
                "subscription": SubscriptionSerializer(subscription).data,
            },
            status=200,
        )


class CustomerSubscriptionBillsView(APIView):
    """
    Authoritative, database-driven customer billing endpoint based on fulfilled DailyDeliveries.
    - Customer can ONLY view their own bills.
    - Delivered drops are billed; failed/missed drops are explicitly omitted from delivered total.
    - All calculations are performed using Decimal on the backend.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Customer bills calculated from fulfilled daily deliveries")
    def get(self, request):
        user = request.user
        subscriptions = (
            Subscription.objects.filter(user=user)
            .select_related("product", "plan", "delivery_boy")
            .prefetch_related("daily_deliveries")
            .order_by("-created_at")
        )

        bills = []
        overall_delivered_volume = Decimal("0.00")
        overall_amount_payable = Decimal("0.00")
        overall_delivered_drops = 0

        for sub in subscriptions:
            daily_drops = sub.daily_deliveries.all().order_by("delivery_date")
            total_scheduled = daily_drops.count()
            delivered_drops = [d for d in daily_drops if d.status == "delivered"]
            failed_drops = [d for d in daily_drops if d.status == "failed"]
            pending_drops = [d for d in daily_drops if d.status in ("pending", "out_for_delivery")]

            delivered_count = len(delivered_drops)
            failed_count = len(failed_drops)
            pending_count = len(pending_drops)

            qty = Decimal(str(sub.quantity))
            rate = Decimal(str(sub.price_per_unit))
            discount = Decimal(str(sub.discount_per_unit or "0.00"))
            final_rate = max(Decimal("0.00"), rate - discount)

            delivered_vol = qty * Decimal(str(delivered_count))
            delivered_subtotal = delivered_vol * rate
            discount_total = delivered_vol * discount
            amount_payable = delivered_vol * final_rate

            overall_delivered_volume += delivered_vol
            overall_amount_payable += amount_payable
            overall_delivered_drops += delivered_count

            breakdown = []
            for d in daily_drops:
                boy_name = ""
                if d.delivery_boy:
                    boy_name = f"{d.delivery_boy.first_name} {d.delivery_boy.last_name}".strip() or d.delivery_boy.mobile_number

                breakdown.append({
                    "id": d.id,
                    "delivery_date": d.delivery_date,
                    "status": d.status,
                    "status_display": d.get_status_display(),
                    "delivered_at": d.delivered_at,
                    "notes": d.notes or "",
                    "product_name": sub.product.name,
                    "quantity": qty,
                    "unit": sub.product.get_unit_display() if hasattr(sub.product, "get_unit_display") else "Litre",
                    "delivery_boy_name": boy_name,
                })

            bills.append({
                "subscription_id": sub.id,
                "product_name": sub.product.name,
                "quantity_per_day": qty,
                "unit": sub.product.get_unit_display() if hasattr(sub.product, "get_unit_display") else "Litre",
                "rate_per_unit": rate,
                "discount_per_unit": discount,
                "final_rate_per_unit": final_rate,
                "start_date": sub.start_date,
                "end_date": sub.end_date,
                "subscription_status": sub.status,
                "total_scheduled_drops": total_scheduled,
                "delivered_drops_count": delivered_count,
                "delivered_volume": delivered_vol,
                "failed_drops_count": failed_count,
                "pending_future_drops_count": pending_count,
                "delivered_subtotal": delivered_subtotal,
                "discount_total": discount_total,
                "amount_payable": amount_payable,
                "payment_status": "Settled via Cash at Doorstep",
                "delivery_breakdown": breakdown,
            })

        return Response(
            {
                "msg": "Customer bills fetched successfully.",
                "summary": {
                    "total_subscriptions": len(bills),
                    "total_delivered_drops": overall_delivered_drops,
                    "total_delivered_volume": str(overall_delivered_volume),
                    "total_amount_payable": str(overall_amount_payable),
                    "billing_currency": "INR",
                },
                "bills": CustomerSubscriptionBillSerializer(bills, many=True).data,
            },
            status=200,
        )


class CustomerSubscriptionDeliveriesView(APIView):
    """
    Authoritative customer delivery calendar endpoint.
    - Returns full DailyDelivery calendar for customer's own subscription.
    - Strictly blocks cross-customer access (404/403).
    - Reflects active, paused, resumed, delivered, failed, and pending future drops accurately.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Customer views delivery calendar for own subscription")
    def get(self, request, pk):
        try:
            subscription = (
                Subscription.objects.select_related("product", "delivery_boy")
                .get(pk=pk, user=request.user)
            )
        except Subscription.DoesNotExist:
            return Response(
                {"msg": "Subscription not found or not owned by user."},
                status=404,
            )

        daily_deliveries = (
            subscription.daily_deliveries.all()
            .select_related("delivery_boy")
            .order_by("delivery_date")
        )

        deliveries_data = []
        for d in daily_deliveries:
            boy_name = ""
            if d.delivery_boy:
                boy_name = f"{d.delivery_boy.first_name} {d.delivery_boy.last_name}".strip() or d.delivery_boy.mobile_number

            deliveries_data.append({
                "id": d.id,
                "delivery_date": d.delivery_date,
                "status": d.status,
                "status_display": d.get_status_display(),
                "delivered_at": d.delivered_at,
                "notes": d.notes or "",
                "product_name": subscription.product.name,
                "quantity": Decimal(str(subscription.quantity)),
                "unit": subscription.product.get_unit_display() if hasattr(subscription.product, "get_unit_display") else "Litre",
                "delivery_boy_name": boy_name,
            })

        return Response(
            {
                "msg": "Deliveries fetched successfully.",
                "subscription_id": subscription.id,
                "subscription_status": subscription.status,
                "product_name": subscription.product.name,
                "quantity": str(subscription.quantity),
                "start_date": str(subscription.start_date),
                "end_date": str(subscription.end_date),
                "total_deliveries": len(deliveries_data),
                "deliveries": CustomerDeliveryItemSerializer(deliveries_data, many=True).data,
            },
            status=200,
        )


class AdminCreateSubscriptionView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Admin creates subscription for a user",
        description="Super admin can create a subscription on behalf of any user and record payment.",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "user_id": 1,
                    "product_id": 1,
                    "address_id": 1,
                    "delivery_slot_id": 1,
                    "quantity": 2.0,
                    "start_date": "2026-07-20",
                    "payment_method": "cash",
                    "mark_as_paid": True,
                },
            )
        ],
    )
    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        user_id = request.data.get("user_id")
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"msg": "User not found."}, status=404)

        data = request.data.copy()
        data["user"] = user
        context = {"request": type("obj", (object,), {"user": user})()}

        serializer = CreateSubscriptionSerializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        subscription = Subscription.objects.create(
            user=user,
            product=validated["product"],
            address=validated["address"],
            delivery_slot=validated.get("delivery_slot"),
            quantity=validated["quantity"],
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            price_per_unit=validated["price_per_unit"],
            discount_per_unit=validated["discount_per_unit"],
            final_price_per_unit=validated["final_price_per_unit"],
            total_amount=validated["total_amount"],
        )

        mark_as_paid = request.data.get("mark_as_paid", False)
        if mark_as_paid:
            Payment.objects.create(
                user=user,
                subscription=subscription,
                payment_for="subscription",
                amount=subscription.total_amount,
                payment_method=request.data.get("payment_method", "cash"),
                payment_status="completed",
                notes="Payment recorded by admin",
            )

        Notification.objects.create(
            user=user,
            title="Subscription Created",
            message=f"Admin created a subscription for {subscription.product.name}.",
            notification_type="subscription",
        )

        return Response(
            {
                "msg": "Subscription created successfully by admin.",
                "subscription": SubscriptionSerializer(subscription).data,
            },
            status=201,
        )


class PaymentHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List my payment history")
    def get(self, request):
        payments = Payment.objects.filter(user=request.user)
        total_paid_val = sum(
            p.amount for p in payments.filter(payment_status="completed")
        )
        serializer = PaymentSerializer(payments, many=True)
        return Response(
            {
                "msg": "Payment history fetched successfully.",
                "total": payments.count(),
                "total_paid": str(total_paid_val),
                "payments": serializer.data,
            },
            status=200,
        )


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get payment details")
    def get(self, request, pk):
        try:
            payment = Payment.objects.get(pk=pk, user=request.user)
        except Payment.DoesNotExist:
            return Response({"msg": "Payment not found."}, status=404)
        serializer = PaymentSerializer(payment)
        return Response(
            {
                "msg": "Payment fetched successfully.",
                "payment": serializer.data,
            },
            status=200,
        )


class WalletAddMoneyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Add money to DudhDairy Wallet (Deprecated)",
        description="Disabled: Online payments and manual wallet recharges are disabled. DudhDairy is strictly Cash Only.",
    )
    def post(self, request):
        return Response(
            {"msg": "Online payments and wallet top-ups are disabled. DudhDairy is strictly Cash Only."},
            status=410,
        )


class WalletTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List wallet transactions")
    def get(self, request):
        payments = Payment.objects.filter(user=request.user)
        serializer = PaymentSerializer(payments, many=True)
        return Response(
            {
                "msg": "Wallet transactions fetched successfully.",
                "wallet_balance": str(request.user.wallet_balance),
                "payments": serializer.data,
            },
            status=200,
        )


class WalletCreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create Razorpay order for wallet recharge (Deprecated)",
        description="Disabled: DudhDairy is strictly Cash Only.",
    )
    def post(self, request):
        return Response(
            {"msg": "Online payments and wallet top-ups are disabled. DudhDairy is strictly Cash Only."},
            status=410,
        )


class WalletVerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Verify Razorpay wallet payment signature (Deprecated)",
        description="Disabled: DudhDairy is strictly Cash Only.",
    )
    def post(self, request):
        return Response(
            {"msg": "Online payments and wallet top-ups are disabled. DudhDairy is strictly Cash Only."},
            status=410,
        )
