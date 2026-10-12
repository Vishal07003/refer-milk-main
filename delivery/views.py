from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.models import DeliveryBoyProfile, Notification, User
from orders.models import Order
from subscriptions.models import Subscription
from .models import DailyDelivery
from .serializers import (
    AssignOrderSerializer,
    AssignSubscriptionSerializer,
    CreateDeliveryBoySerializer,
    DailyDeliverySerializer,
    DeliveryBoyListSerializer,
    DeliveryBoyProfileSerializer,
    DeliveryOrderSerializer,
    UpdateDeliveryStatusSerializer,
)


def is_delivery_boy(user):
    return user.role in ["delivery_boy", "delivery"]


def is_admin(user):
    return user.is_staff


class DeliveryBoyProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get delivery boy profile")
    def get(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        profile = DeliveryBoyProfile.objects.filter(user=request.user).first()
        if not profile:
            profile = DeliveryBoyProfile.objects.create(user=request.user)
        serializer = DeliveryBoyProfileSerializer(profile)
        today = timezone.now().date()
        today_deliveries = DailyDelivery.objects.filter(
            delivery_boy=request.user, delivery_date=today
        )
        return Response(
            {
                "msg": "Profile fetched successfully.",
                "profile": serializer.data,
                "today_summary": {
                    "total": today_deliveries.count(),
                    "delivered": today_deliveries.filter(status="delivered").count(),
                    "pending": today_deliveries.filter(status="pending").count(),
                    "failed": today_deliveries.filter(status="failed").count(),
                },
            },
            status=200,
        )


class UpdateDeliveryBoyProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update delivery boy profile",
        examples=[
            OpenApiExample(
                "Example",
                value={"vehicle_number": "MH-12-AB-1234", "zone": "Pune Central"},
            )
        ],
    )
    def put(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        profile, _ = DeliveryBoyProfile.objects.get_or_create(user=request.user)
        serializer = DeliveryBoyProfileSerializer(
            profile, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Profile updated successfully.",
                "profile": serializer.data,
            },
            status=200,
        )


class ToggleAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Toggle delivery boy online/offline status")
    def post(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        profile, _ = DeliveryBoyProfile.objects.get_or_create(user=request.user)
        profile.is_available = not profile.is_available
        profile.save(update_fields=["is_available"])
        return Response(
            {
                "msg": f"You are now {'online' if profile.is_available else 'offline'}.",
                "is_available": profile.is_available,
            },
            status=200,
        )


class MyOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get today's assigned orders")
    def get(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        orders = (
            Order.objects.filter(
                delivery_boy=request.user,
                status__in=["confirmed", "processing", "out_for_delivery", "delivered"],
            )
            .select_related("user", "address", "delivery_slot")
            .prefetch_related("items", "items__product")
            .order_by("created_at")
        )

        serializer = DeliveryOrderSerializer(orders, many=True)
        return Response(
            {
                "msg": "Assigned orders fetched successfully.",
                "orders": serializer.data,
            },
            status=200,
        )


class DeliveryOrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get detail of an assigned order")
    def get(self, request, pk):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        order = (
            Order.objects.filter(pk=pk)
            .select_related("user", "address", "delivery_slot")
            .prefetch_related("items", "items__product")
            .first()
        )
        if not order:
            return Response({"msg": "Order not found."}, status=404)

        if order.delivery_boy != request.user:
            return Response(
                {"msg": "Forbidden: You are not assigned to this order."},
                status=403,
            )

        serializer = DeliveryOrderSerializer(order)
        return Response(
            {
                "msg": "Order detail fetched successfully.",
                "order": serializer.data,
            },
            status=200,
        )


class UpdateOrderDeliveryStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update order delivery status",
        examples=[
            OpenApiExample(
                "Example", value={"status": "delivered", "notes": "Left at door"}
            )
        ],
    )
    def post(self, request, pk):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        order = Order.objects.filter(pk=pk).first()
        if not order:
            return Response({"msg": "Order not found."}, status=404)

        if order.delivery_boy != request.user:
            return Response(
                {"msg": "Forbidden: You are not assigned to this order."},
                status=403,
            )

        serializer = UpdateDeliveryStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        allowed_transitions = {
            "confirmed": ["out_for_delivery"],
            "processing": ["out_for_delivery"],
            "out_for_delivery": ["delivered", "failed"],
        }
        current_allowed = allowed_transitions.get(order.status, [])
        if new_status not in current_allowed:
            return Response(
                {
                    "msg": f"Cannot change status from '{order.status}' to '{new_status}'."
                },
                status=400,
            )

        order.status = new_status
        if new_status in ("delivered", "failed"):
            order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_at", "updated_at"])

        from notifications.services import send_notification_to_user
        if new_status == "out_for_delivery":
            send_notification_to_user(
                user=order.user,
                title="Out for Delivery 🚚",
                body=f"Your order #{order.id} is out for delivery.",
                data={"type": "out_for_delivery", "order_id": str(order.id)},
                notification_type="order",
            )
        elif new_status == "delivered":
            send_notification_to_user(
                user=order.user,
                title="Order Delivered 🥛",
                body=f"Your order #{order.id} has been delivered successfully.",
                data={"type": "order_delivered", "order_id": str(order.id)},
                notification_type="order",
            )
        elif new_status == "failed":
            send_notification_to_user(
                user=order.user,
                title="Delivery Attempt Failed",
                body=f"Delivery attempt for order #{order.id} could not be completed.",
                data={"type": "order_failed", "order_id": str(order.id)},
                notification_type="order",
            )

        return Response(
            {
                "msg": f"Order status updated to '{new_status}'.",
                "order_id": order.id,
                "status": order.status,
            },
            status=200,
        )


class MySubscriptionDeliveriesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get today's subscription deliveries")
    def get(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        today = timezone.now().date()
        deliveries = DailyDelivery.objects.filter(
            delivery_boy=request.user,
            delivery_date=today,
        ).select_related(
            "subscription",
            "subscription__product",
            "subscription__address",
            "subscription__user",
            "subscription__delivery_slot",
        )
        serializer = DailyDeliverySerializer(deliveries, many=True)
        return Response(
            {
                "msg": "Today's subscription deliveries fetched successfully.",
                "deliveries": serializer.data,
            },
            status=200,
        )


class DeliveryDailyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get detail of an assigned daily delivery")
    def get(self, request, pk):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        delivery = (
            DailyDelivery.objects.filter(pk=pk)
            .select_related(
                "subscription",
                "subscription__product",
                "subscription__address",
                "subscription__user",
                "subscription__delivery_slot",
            )
            .first()
        )
        if not delivery:
            return Response({"msg": "Delivery not found."}, status=404)

        if delivery.delivery_boy != request.user:
            return Response(
                {"msg": "Forbidden: You are not assigned to this delivery."},
                status=403,
            )

        serializer = DailyDeliverySerializer(delivery)
        return Response(
            {
                "msg": "Daily delivery detail fetched successfully.",
                "delivery": serializer.data,
            },
            status=200,
        )


class UpdateDailyDeliveryStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update daily delivery status",
        examples=[
            OpenApiExample(
                "Example", value={"status": "delivered", "notes": "Handed to customer"}
            )
        ],
    )
    def post(self, request, pk):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        delivery = DailyDelivery.objects.filter(pk=pk).first()
        if not delivery:
            return Response({"msg": "Delivery not found."}, status=404)

        if delivery.delivery_boy != request.user:
            return Response(
                {"msg": "Forbidden: You are not assigned to this delivery."},
                status=403,
            )

        serializer = UpdateDeliveryStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        notes = serializer.validated_data.get("notes", "")

        allowed_transitions = {
            "pending": ["out_for_delivery"],
            "out_for_delivery": ["delivered", "failed"],
        }
        current_allowed = allowed_transitions.get(delivery.status, [])
        if new_status not in current_allowed:
            return Response(
                {
                    "msg": f"Cannot change status from '{delivery.status}' to '{new_status}'."
                },
                status=400,
            )

        delivery.status = new_status
        if new_status in ("delivered", "failed"):
            delivery.delivered_at = timezone.now()
        if notes:
            delivery.notes = notes
        delivery.save(update_fields=["status", "delivered_at", "notes", "updated_at"])

        if new_status == "out_for_delivery":
            from notifications.services import send_notification_to_user
            send_notification_to_user(
                user=delivery.subscription.user,
                title="Out for Delivery 🚚",
                body=f"Your {delivery.subscription.product.name} milk delivery is on the way.",
                data={"type": "out_for_delivery", "subscription_id": str(delivery.subscription.id)},
                notification_type="subscription",
            )
        elif new_status == "delivered":
            from notifications.services import send_notification_to_user
            send_notification_to_user(
                user=delivery.subscription.user,
                title="Delivery Completed 🥛",
                body=f"Your {delivery.subscription.product.name} has been delivered for today.",
                data={"type": "order_delivered", "subscription_id": str(delivery.subscription.id)},
                notification_type="subscription",
            )
        elif new_status == "failed":
            from notifications.services import send_notification_to_user
            send_notification_to_user(
                user=delivery.subscription.user,
                title="Delivery Attempt Failed",
                body=f"Today's delivery for {delivery.subscription.product.name} could not be completed.",
                data={"type": "order_failed", "subscription_id": str(delivery.subscription.id)},
                notification_type="subscription",
            )

        return Response(
            {
                "msg": f"Delivery status updated to '{new_status}'.",
                "delivery_id": delivery.id,
                "status": delivery.status,
            },
            status=200,
        )


class AdminCreateDeliveryBoyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Admin creates a delivery boy account",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "mobile_number": "9876543210",
                    "first_name": "Ramesh",
                    "last_name": "Kumar",
                    "vehicle_number": "MH-12-AB-1234",
                    "zone": "Pune Central",
                },
            )
        ],
    )
    def post(self, request):
        if not is_admin(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        serializer = CreateDeliveryBoySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, profile = serializer.create(serializer.validated_data)

        Notification.objects.create(
            user=user,
            title="Account Created",
            message="Your delivery boy account has been created. You can now log in with your mobile number.",
            notification_type="general",
        )

        return Response(
            {
                "msg": "Delivery boy account created successfully.",
                "delivery_boy": DeliveryBoyListSerializer(user).data,
            },
            status=201,
        )


class AdminDeliveryBoysListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List all delivery boys")
    def get(self, request):
        if not is_admin(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        boys = User.objects.filter(role="delivery_boy").select_related(
            "delivery_profile"
        )
        serializer = DeliveryBoyListSerializer(boys, many=True)
        return Response(
            {
                "msg": "Delivery boys fetched successfully.",
                "delivery_boys": serializer.data,
            },
            status=200,
        )


class AdminDeliveryBoyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get delivery boy details")
    def get(self, request, pk):
        if not is_admin(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        try:
            boy = User.objects.select_related("delivery_profile").get(
                id=pk, role="delivery_boy"
            )
        except User.DoesNotExist:
            return Response({"msg": "Delivery boy not found."}, status=404)

        profile = DeliveryBoyProfile.objects.filter(user=boy).first()
        today = timezone.now().date()
        today_deliveries = DailyDelivery.objects.filter(
            delivery_boy=boy, delivery_date=today
        )
        assigned_orders = Order.objects.filter(
            delivery_boy=boy, status__in=["confirmed", "processing", "out_for_delivery"]
        )

        return Response(
            {
                "msg": "Delivery boy details fetched successfully.",
                "delivery_boy": DeliveryBoyListSerializer(boy).data,
                "today_summary": {
                    "total_deliveries": today_deliveries.count(),
                    "delivered": today_deliveries.filter(status="delivered").count(),
                    "pending": today_deliveries.filter(status="pending").count(),
                    "failed": today_deliveries.filter(status="failed").count(),
                },
                "active_orders": assigned_orders.count(),
            },
            status=200,
        )


class AdminAssignOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Admin assigns delivery boy to order",
        examples=[
            OpenApiExample("Example", value={"delivery_boy_id": 5, "order_id": 12})
        ],
    )
    def post(self, request):
        if not is_admin(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        serializer = AssignOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        boy = User.objects.get(id=serializer.validated_data["delivery_boy_id"])
        order = Order.objects.get(id=serializer.validated_data["order_id"])

        order.delivery_boy = boy
        order.save(update_fields=["delivery_boy", "updated_at"])

        from notifications.services import send_notification_to_user
        send_notification_to_user(
            user=boy,
            title="New Delivery Assigned",
            body=f"Order #{order.id} has been assigned to you.",
            data={"type": "new_order", "order_id": str(order.id)},
            notification_type="order",
        )

        return Response(
            {
                "msg": f"Order #{order.id} assigned to {boy.mobile_number}.",
            },
            status=200,
        )


class AdminAssignSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Admin assigns delivery boy to subscription",
        description="Assigns delivery boy and creates DailyDelivery records for remaining days.",
        examples=[
            OpenApiExample(
                "Example", value={"delivery_boy_id": 5, "subscription_id": 8}
            )
        ],
    )
    def post(self, request):
        if not is_admin(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        serializer = AssignSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        boy = User.objects.get(id=serializer.validated_data["delivery_boy_id"])
        subscription = Subscription.objects.get(
            id=serializer.validated_data["subscription_id"]
        )

        subscription.delivery_boy = boy
        subscription.save(update_fields=["delivery_boy", "updated_at"])

        today = timezone.now().date()
        end_date = subscription.end_date
        created_count = 0
        current_date = max(today, subscription.start_date)
        while current_date <= end_date:
            _, created = DailyDelivery.objects.get_or_create(
                subscription=subscription,
                delivery_date=current_date,
                defaults={"delivery_boy": boy},
            )
            if created:
                created_count += 1
            from datetime import timedelta

            current_date += timedelta(days=1)

        from notifications.services import send_notification_to_user
        send_notification_to_user(
            user=boy,
            title="New Subscription Delivery",
            body=f"A new milk subscription has been assigned to you.",
            data={"type": "new_subscription", "subscription_id": str(subscription.id)},
            notification_type="subscription",
        )

        return Response(
            {
                "msg": f"Subscription #{subscription.id} assigned to {boy.mobile_number}. {created_count} daily deliveries created.",
            },
            status=200,
        )


class AvailableOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get all unassigned available orders for delivery partners")
    def get(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        orders = (
            Order.objects.filter(
                delivery_boy__isnull=True,
                status__in=["confirmed", "processing"],
            )
            .select_related("user", "address", "delivery_slot")
            .prefetch_related("items", "items__product")
            .order_by("-created_at")
        )
        serializer = DeliveryOrderSerializer(orders, many=True)
        return Response(
            {
                "msg": "Available unassigned orders fetched successfully.",
                "orders": serializer.data,
            },
            status=200,
        )


class AcceptOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Delivery boy accepts an unassigned order")
    def post(self, request, pk):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        from django.db import transaction

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=pk)
            except Order.DoesNotExist:
                return Response({"msg": "Order not found."}, status=404)

            if order.delivery_boy is not None:
                if order.delivery_boy == request.user:
                    return Response({"msg": "You have already accepted this order."}, status=200)
                return Response(
                    {"msg": "Order has already been accepted by another delivery partner."},
                    status=400,
                )

            order.delivery_boy = request.user
            order.save(update_fields=["delivery_boy", "updated_at"])

        from notifications.services import send_notification_to_user

        # 1. Notify Customer
        send_notification_to_user(
            user=order.user,
            title="Order Accepted 🛵",
            body=f"Delivery partner has accepted your order #{order.id}.",
            data={"type": "order_confirmed", "order_id": str(order.id)},
            notification_type="order",
        )

        # 2. Notify all other delivery partners
        other_delivery_boys = User.objects.filter(
            role__in=["delivery_boy", "delivery"]
        ).exclude(id=request.user.id)

        for boy in other_delivery_boys:
            send_notification_to_user(
                user=boy,
                title="Order Taken 📦",
                body=f"Order #{order.id} has been accepted by another delivery partner.",
                data={"type": "order_claimed", "order_id": str(order.id)},
                notification_type="order",
            )

        return Response(
            {
                "msg": "Order accepted successfully.",
                "order_id": order.id,
                "delivery_boy": request.user.mobile_number,
            },
            status=200,
        )


class CollectPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delivery partner collects payment for an assigned order",
        examples=[
            OpenApiExample(
                "Cash Example",
                value={"payment_method": "cash"}
            ),
            OpenApiExample(
                "UPI Example",
                value={"payment_method": "upi_at_delivery", "transaction_reference": "UTR12345678"}
            ),
        ],
    )
    def post(self, request, pk):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        order = Order.objects.filter(pk=pk).select_related("user").first()
        if not order:
            return Response({"msg": "Order not found."}, status=404)

        if order.delivery_boy != request.user:
            return Response(
                {"msg": "Forbidden: You are not assigned to this order."},
                status=403,
            )

        req_method = request.data.get("payment_method", "cash")
        payment_method = "cash" if req_method not in ("cash", "upi_at_delivery") else req_method
        transaction_ref = request.data.get("transaction_reference", "").strip()

        if order.payment_method not in ("cash", "upi_at_delivery"):
            return Response(
                {"msg": f"Order payment method is '{order.payment_method}', not offline cash."},
                status=400,
            )

        # Idempotency check: if already collected
        if order.payment_status in ("collected", "paid", "verified"):
            existing = order.offline_collections.filter(status__in=["collected", "verified"]).first()
            from orders.serializers import OfflinePaymentCollectionSerializer
            return Response(
                {
                    "msg": "Cash has already been collected for this order.",
                    "collection": OfflinePaymentCollectionSerializer(existing).data if existing else None,
                    "order_id": order.id,
                    "payment_status": order.payment_status,
                },
                status=200,
            )

        if order.payment_status != "pending":
            return Response(
                {"msg": f"Cannot collect payment with status '{order.payment_status}'."},
                status=400,
            )

        from django.db import transaction
        from orders.models import OfflinePaymentCollection
        from subscriptions.models import Payment

        with transaction.atomic():
            # Lock the order row to prevent concurrent race conditions
            locked_order = Order.objects.select_for_update().get(pk=order.pk)
            if locked_order.payment_status in ("collected", "paid", "verified"):
                existing = locked_order.offline_collections.filter(status__in=["collected", "verified"]).first()
                from orders.serializers import OfflinePaymentCollectionSerializer
                return Response(
                    {
                        "msg": "Cash has already been collected for this order.",
                        "collection": OfflinePaymentCollectionSerializer(existing).data if existing else None,
                        "order_id": locked_order.id,
                        "payment_status": locked_order.payment_status,
                    },
                    status=200,
                )

            # Prevent duplicate collection entries in OfflinePaymentCollection
            existing_col = OfflinePaymentCollection.objects.filter(order=locked_order).first()
            if existing_col and existing_col.status in ("collected", "verified"):
                from orders.serializers import OfflinePaymentCollectionSerializer
                return Response(
                    {
                        "msg": "Collection entry already exists for this order.",
                        "collection": OfflinePaymentCollectionSerializer(existing_col).data,
                        "order_id": locked_order.id,
                        "payment_status": locked_order.payment_status,
                    },
                    status=200,
                )

            now = timezone.now()
            # Validated exact final_amount from database - delivery boy cannot tamper with amount
            collected_amount = locked_order.final_amount

            collection = OfflinePaymentCollection.objects.create(
                order=locked_order,
                delivery_partner=request.user,
                payment_method=payment_method,
                transaction_reference=transaction_ref,
                amount=collected_amount,
                status="collected",
                collected_at=now,
            )

            locked_order.payment_method = payment_method
            locked_order.payment_status = "collected"
            # Update delivery status to delivered when payment is successfully collected
            if locked_order.status != "delivered":
                locked_order.status = "delivered"
                locked_order.delivered_at = now
            locked_order.save(update_fields=["payment_method", "payment_status", "status", "delivered_at", "updated_at"])

            # Also create audit Payment record
            Payment.objects.create(
                user=locked_order.user,
                order=locked_order,
                payment_for="order",
                amount=locked_order.final_amount,
                payment_method="cash",
                payment_status="completed",
                transaction_id=f"CASH-{locked_order.id}-{int(now.timestamp())}",
                notes=f"Collected by delivery partner {request.user.mobile_number}",
            )

        # Dispatch FCM push notification after successful database commit
        from notifications.services import send_notification_to_user
        try:
            send_notification_to_user(
                user=locked_order.user,
                title="Payment Collected 🥛",
                body=f"Payment of ₹{locked_order.final_amount} for order #{locked_order.id} has been collected.",
                data={
                    "type": "offline_payment_collected",
                    "order_id": str(locked_order.id),
                },
                notification_type="payment",
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to send collection notification: {e}")

        from orders.serializers import OfflinePaymentCollectionSerializer
        return Response(
            {
                "msg": f"Payment of ₹{locked_order.final_amount} collected successfully via {payment_method}.",
                "collection": OfflinePaymentCollectionSerializer(collection).data,
                "order_id": locked_order.id,
                "payment_status": locked_order.payment_status,
                "status": locked_order.status,
            },
            status=200,
        )


class PaymentFailedView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Report unable to collect payment for order",
        examples=[
            OpenApiExample(
                "Example",
                value={"reason": "customer_unavailable", "notes": "Customer did not answer doorbell"}
            )
        ],
    )
    def post(self, request, pk):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        order = Order.objects.filter(pk=pk).first()
        if not order:
            return Response({"msg": "Order not found."}, status=404)

        if order.delivery_boy != request.user:
            return Response(
                {"msg": "Forbidden: You are not assigned to this order."},
                status=403,
            )

        reason = request.data.get("reason", "other")
        notes = request.data.get("notes", "")

        from orders.models import OfflinePaymentCollection
        collection = OfflinePaymentCollection.objects.create(
            order=order,
            delivery_partner=request.user,
            payment_method=order.payment_method if order.payment_method in ('cash', 'upi_at_delivery') else 'cash',
            amount=order.final_amount,
            status="failed",
            reason=reason,
            notes=notes,
        )

        from orders.serializers import OfflinePaymentCollectionSerializer
        return Response(
            {
                "msg": "Recorded payment collection failure.",
                "collection": OfflinePaymentCollectionSerializer(collection).data,
            },
            status=200,
        )


class OfflineCollectionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get delivery partner's collections and totals")
    def get(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        from orders.models import OfflinePaymentCollection
        from django.db.models import Sum

        today = timezone.now().date()
        today_collections = OfflinePaymentCollection.objects.filter(
            delivery_partner=request.user,
            status="collected",
            collected_at__date=today,
        )

        today_cash = (
            today_collections.filter(payment_method="cash").aggregate(Sum("amount"))["amount__sum"]
            or 0
        )
        today_upi = (
            today_collections.filter(payment_method="upi_at_delivery").aggregate(Sum("amount"))["amount__sum"]
            or 0
        )
        today_total = today_cash + today_upi

        total_cash_collected = (
            OfflinePaymentCollection.objects.filter(
                delivery_partner=request.user,
                payment_method="cash",
                status="collected",
            ).aggregate(Sum("amount"))["amount__sum"]
            or 0
        )

        from .models import CashHandover
        from decimal import Decimal
        total_confirmed_handover = CashHandover.objects.filter(
            delivery_boy=request.user,
            status="confirmed",
        ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

        total_pending_handover = max(Decimal("0.00"), Decimal(str(total_cash_collected)) - total_confirmed_handover)
        prev_collected = max(Decimal("0.00"), Decimal(str(total_cash_collected)) - Decimal(str(today_cash)))
        prev_unhanded = max(Decimal("0.00"), prev_collected - total_confirmed_handover)

        all_collections = OfflinePaymentCollection.objects.filter(
            delivery_partner=request.user
        ).select_related("order", "order__user")[:50]

        from orders.serializers import OfflinePaymentCollectionSerializer
        return Response(
            {
                "msg": "Collections summary fetched successfully.",
                "today_summary": {
                    "cash": str(today_cash),
                    "upi": str(today_upi),
                    "total": str(today_total),
                    "count": today_collections.count(),
                    "today_cash": float(today_cash),
                    "today_order_count": today_collections.values("order_id").distinct().count(),
                    "previous_unhanded_cash": float(prev_unhanded),
                    "total_pending_handover": float(total_pending_handover),
                    "confirmed_handovers": float(total_confirmed_handover),
                },
                "collections": OfflinePaymentCollectionSerializer(all_collections, many=True).data,
            },
            status=200,
        )


class AdminOfflinePaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Admin: List all offline collections with filtering")
    def get(self, request):
        if not is_admin(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        from orders.models import OfflinePaymentCollection
        qs = OfflinePaymentCollection.objects.all().select_related("order", "order__user", "delivery_partner")

        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        method_param = request.query_params.get("payment_method")
        if method_param:
            qs = qs.filter(payment_method=method_param)

        from orders.serializers import OfflinePaymentCollectionSerializer
        return Response(
            {
                "msg": "Offline payments fetched successfully.",
                "collections": OfflinePaymentCollectionSerializer(qs[:100], many=True).data,
            },
            status=200,
        )


class AdminVerifyOfflinePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Admin: Verify/Reconcile an offline payment collection")
    def post(self, request, pk):
        if not is_admin(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        from orders.models import OfflinePaymentCollection
        collection = OfflinePaymentCollection.objects.filter(pk=pk).first()
        if not collection:
            return Response({"msg": "Collection not found."}, status=404)

        action = request.data.get("action", "verify")
        if action == "verify":
            collection.status = "verified"
            collection.verified_at = timezone.now()
            collection.verified_by = request.user
        elif action == "reject":
            collection.status = "rejected"
            collection.notes = (collection.notes + " " + request.data.get("notes", "Rejected by admin")).strip()
        else:
            return Response({"msg": "Action must be 'verify' or 'reject'."}, status=400)

        collection.save(update_fields=["status", "verified_at", "verified_by", "notes", "updated_at"])

        from orders.serializers import OfflinePaymentCollectionSerializer
        return Response(
            {
                "msg": f"Offline collection marked as {collection.status}.",
                "collection": OfflinePaymentCollectionSerializer(collection).data,
            },
            status=200,
        )


class SubmitCashHandoverView(APIView):
    """
    Delivery Boy submits cash handover to admin hub.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Delivery partner submits cash handover")
    def post(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        from .models import CashHandover
        from .serializers import SubmitCashHandoverSerializer, CashHandoverSerializer
        from orders.models import OfflinePaymentCollection
        from django.db.models import Sum
        from decimal import Decimal
        from datetime import timedelta

        serializer = SubmitCashHandoverSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        submitted_amount = serializer.validated_data["submitted_amount"]
        delivery_notes = serializer.validated_data.get("delivery_notes", "")

        # Compute current cash in hand
        total_collected = OfflinePaymentCollection.objects.filter(
            delivery_partner=request.user,
            payment_method="cash",
            status="collected"
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        total_confirmed_handover = CashHandover.objects.filter(
            delivery_boy=request.user,
            status="confirmed"
        ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

        pending_handovers_amt = CashHandover.objects.filter(
            delivery_boy=request.user,
            status="submitted"
        ).aggregate(s=Sum("submitted_amount"))["s"] or Decimal("0.00")

        available_cash_balance = max(Decimal("0.00"), total_collected - total_confirmed_handover)

        # Enforce validation: Handover cannot exceed unhanded cash balance
        if submitted_amount > available_cash_balance:
            return Response(
                {
                    "msg": f"Submitted amount (₹{submitted_amount}) cannot exceed current unhanded cash balance (₹{available_cash_balance}).",
                    "available_cash_balance": float(available_cash_balance),
                },
                status=400,
            )

        # Idempotency and duplicate prevention: Check if identical handover was already submitted recently
        recent_cutoff = timezone.now() - timedelta(minutes=2)
        duplicate_handover = CashHandover.objects.filter(
            delivery_boy=request.user,
            submitted_amount=submitted_amount,
            status="submitted",
            submitted_at__gte=recent_cutoff,
        ).first()

        if duplicate_handover:
            return Response(
                {
                    "msg": f"A cash handover of ₹{submitted_amount} is already submitted and awaiting Admin confirmation.",
                    "handover": CashHandoverSerializer(duplicate_handover).data,
                    "summary": {
                        "total_collected": float(total_collected),
                        "total_confirmed_handover": float(total_confirmed_handover),
                        "pending_cash_balance": float(available_cash_balance),
                        "awaiting_admin_confirmation": float(pending_handovers_amt),
                    }
                },
                status=200,
            )

        # Create cash handover record with status 'submitted'
        handover = CashHandover.objects.create(
            delivery_boy=request.user,
            submitted_amount=submitted_amount,
            status="submitted",
            delivery_notes=delivery_notes,
        )

        return Response(
            {
                "msg": f"Cash handover of ₹{submitted_amount} submitted successfully. Awaiting Admin confirmation.",
                "handover": CashHandoverSerializer(handover).data,
                "summary": {
                    "total_collected": float(total_collected),
                    "total_confirmed_handover": float(total_confirmed_handover),
                    "pending_cash_balance": float(available_cash_balance - submitted_amount),
                    "awaiting_admin_confirmation": float(pending_handovers_amt + submitted_amount),
                }
            },
            status=201,
        )


class MyCashHandoversView(APIView):
    """
    Delivery Boy views their cash handover history and current pending cash balance.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Delivery partner views handover history & unreconciled balance")
    def get(self, request):
        if not is_delivery_boy(request.user):
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )

        from .models import CashHandover
        from .serializers import CashHandoverSerializer
        from orders.models import OfflinePaymentCollection
        from django.db.models import Sum
        from decimal import Decimal

        handovers = CashHandover.objects.filter(
            delivery_boy=request.user
        ).order_by("-created_at")[:50]

        total_collected = OfflinePaymentCollection.objects.filter(
            delivery_partner=request.user,
            payment_method="cash",
            status="collected"
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        total_confirmed = CashHandover.objects.filter(
            delivery_boy=request.user,
            status="confirmed"
        ).aggregate(s=Sum("received_amount"))["s"] or Decimal("0.00")

        pending_handovers_amt = CashHandover.objects.filter(
            delivery_boy=request.user,
            status="submitted"
        ).aggregate(s=Sum("submitted_amount"))["s"] or Decimal("0.00")

        today = timezone.now().date()
        today_collections = OfflinePaymentCollection.objects.filter(
            delivery_partner=request.user,
            payment_method="cash",
            status="collected",
            collected_at__date=today,
        )
        today_cash = today_collections.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        today_order_count = today_collections.values("order_id").distinct().count()

        # Previous unhanded cash = collected before today that hasn't been confirmed yet
        # Since confirmed handovers reconcile the oldest debt first:
        # previous_collected = total_collected - today_cash
        # previous_unhanded_cash = max(0, previous_collected - total_confirmed)
        previous_collected = max(Decimal("0.00"), total_collected - today_cash)
        previous_unhanded_cash = max(Decimal("0.00"), previous_collected - total_confirmed)
        pending_balance = max(Decimal("0.00"), total_collected - total_confirmed)

        return Response(
            {
                "msg": "Handovers fetched successfully.",
                "summary": {
                    "today_cash": float(today_cash),
                    "today_order_count": today_order_count,
                    "previous_unhanded_cash": float(previous_unhanded_cash),
                    "total_pending_handover": float(pending_balance),
                    "confirmed_handovers": float(total_confirmed),
                    "awaiting_admin_confirmation": float(pending_handovers_amt),
                    "total_collected": float(total_collected),
                    "confirmed_handed_over": float(total_confirmed),
                    "pending_handover_balance": float(pending_balance),
                },
                "handovers": CashHandoverSerializer(handovers, many=True).data,
            },
            status=200,
        )
