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
        order = Order.objects.filter(pk=pk).first()
        if not order:
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
