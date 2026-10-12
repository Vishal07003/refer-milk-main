from decimal import Decimal

import razorpay
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Address
from products.models import Product

from .models import DeliverySlot, Order, OrderItem
from .serializers import (
    CreateOrderSerializer,
    DeliverySlotSerializer,
    OrderSerializer,
)


class OrderPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class DeliverySlotListView(APIView):
    serializer_class = DeliverySlotSerializer

    @extend_schema(
        summary="List active delivery slots",
        description="Get all active delivery time slots.",
    )
    def get(self, request):
        slots = DeliverySlot.objects.filter(is_active=True)
        serializer = DeliverySlotSerializer(slots, many=True)
        return Response(
            {
                "msg": "Delivery slots fetched successfully.",
                "slots": serializer.data,
            },
            status=200,
        )


class DeliverySlotDetailView(APIView):
    serializer_class = DeliverySlotSerializer

    def get_object(self, pk):
        try:
            return DeliverySlot.objects.get(pk=pk)
        except DeliverySlot.DoesNotExist:
            return None

    @extend_schema(
        summary="Create a delivery slot (Admin only)",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "name": "Morning 7AM-9AM",
                    "start_time": "07:00:00",
                    "end_time": "09:00:00",
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
        serializer = DeliverySlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Delivery slot created successfully.",
                "slot": serializer.data,
            },
            status=201,
        )

    @extend_schema(summary="Update a delivery slot (Admin only)")
    def put(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        slot = self.get_object(pk)
        if not slot:
            return Response({"msg": "Delivery slot not found."}, status=404)
        serializer = DeliverySlotSerializer(slot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Delivery slot updated successfully.",
                "slot": serializer.data,
            },
            status=200,
        )

    @extend_schema(summary="Delete a delivery slot (Admin only)")
    def delete(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        slot = self.get_object(pk)
        if not slot:
            return Response({"msg": "Delivery slot not found."}, status=404)
        slot.delete()
        return Response({"msg": "Delivery slot deleted successfully."}, status=200)


class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CreateOrderSerializer

    @extend_schema(
        summary="Create an order and Razorpay order",
        description="Create a one-time order. Returns Razorpay order_id for payment.",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "address_id": 1,
                    "delivery_slot_id": 1,
                    "items": [
                        {"product_id": 1, "quantity": 2},
                        {"product_id": 2, "quantity": 1},
                    ],
                },
            )
        ],
    )
    def post(self, request):
        serializer = CreateOrderSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        address = Address.objects.get(id=data["address_id"])
        delivery_slot = DeliverySlot.objects.get(id=data["delivery_slot_id"])
        payment_method = data.get("payment_method", "razorpay")

        is_offline = payment_method in ("cash", "upi_at_delivery")
        order_status = "confirmed" if is_offline else "pending"

        order = Order.objects.create(
            user=request.user,
            address=address,
            delivery_slot=delivery_slot,
            payment_method=payment_method,
            payment_status="pending",
            status=order_status,
        )

        total = Decimal("0")
        for item_data in data["items"]:
            product = Product.objects.get(id=item_data["product_id"])
            quantity = item_data["quantity"]
            price = product.price
            item_total = price * quantity
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=price,
                total=item_total,
            )
            total += item_total

        order.total_amount = total
        order.final_amount = total - order.discount_amount
        order.save(update_fields=["total_amount", "final_amount"])

        if is_offline:
            # Send notification for confirmed offline order
            from notifications.services import send_notification_to_user
            send_notification_to_user(
                user=order.user,
                title="Order Confirmed",
                body=f"Your order #{order.id} is confirmed. ₹{order.final_amount} will be collected at delivery.",
                data={"type": "order_confirmed", "order_id": str(order.id)},
                notification_type="order",
            )

            return Response(
                {
                    "msg": "Order placed successfully. Pay at delivery.",
                    "order": OrderSerializer(order).data,
                    "payment_method": payment_method,
                },
                status=201,
            )

        # Online Razorpay Payment flow
        try:
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
            razorpay_order = client.order.create(
                {
                    "amount": int(order.final_amount * 100),
                    "currency": "INR",
                    "receipt": f"order_{order.id}",
                }
            )
            order.razorpay_order_id = razorpay_order["id"]
            order.save(update_fields=["razorpay_order_id"])

            return Response(
                {
                    "msg": "Order created successfully.",
                    "order": OrderSerializer(order).data,
                    "razorpay_order": {
                        "order_id": razorpay_order["id"],
                        "amount": razorpay_order["amount"],
                        "currency": razorpay_order["currency"],
                        "key": settings.RAZORPAY_KEY_ID,
                    },
                },
                status=201,
            )
        except Exception:
            mock_id = f"order_mock_{order.id}"
            order.razorpay_order_id = mock_id
            order.save(update_fields=["razorpay_order_id"])
            return Response(
                {
                    "msg": "Order created successfully.",
                    "order": OrderSerializer(order).data,
                    "razorpay_order": {
                        "order_id": mock_id,
                        "amount": int(order.final_amount * 100),
                        "currency": "INR",
                        "key": settings.RAZORPAY_KEY_ID,
                    },
                },
                status=201,
            )


class VerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Verify Razorpay payment (Deprecated)",
        description="Disabled: Online payments are disabled. DudhDairy is strictly Cash Only.",
    )
    def post(self, request):
        return Response(
            {"msg": "Online payments are disabled. DudhDairy is strictly Cash Only."},
            status=410,
        )


class MyOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List my orders",
        description="Get all orders for the authenticated user.",
    )
    def get(self, request):
        orders = Order.objects.filter(user=request.user)
        paginator = OrderPagination()
        page = paginator.paginate_queryset(orders, request)
        serializer = OrderSerializer(page, many=True)
        return paginator.get_paginated_response(
            {
                "msg": "Orders fetched successfully.",
                "orders": serializer.data,
            }
        )


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get order details")
    def get(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({"msg": "Order not found."}, status=404)
        serializer = OrderSerializer(order)
        return Response(
            {
                "msg": "Order fetched successfully.",
                "order": serializer.data,
            },
            status=200,
        )

    @extend_schema(summary="Cancel an order")
    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({"msg": "Order not found."}, status=404)
        if order.status not in ("pending", "confirmed"):
            return Response(
                {"msg": "Only pending or confirmed orders can be cancelled."},
                status=400,
            )
        order.status = "cancelled"
        order.save(update_fields=["status"])

        from notifications.services import send_notification_to_user
        send_notification_to_user(
            user=order.user,
            title="Order Cancelled",
            body=f"Your order #{order.id} has been cancelled.",
            data={"type": "order_cancelled", "order_id": str(order.id)},
            notification_type="order",
        )
        if order.delivery_boy:
            send_notification_to_user(
                user=order.delivery_boy,
                title="Order Cancelled",
                body=f"Assigned order #{order.id} has been cancelled by customer.",
                data={"type": "order_cancelled", "order_id": str(order.id)},
                notification_type="order",
            )

        return Response(
            {
                "msg": "Order cancelled successfully.",
                "order": OrderSerializer(order).data,
            },
            status=200,
        )


class AdminCreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Admin creates order for a user",
        description="Super admin can create an order on behalf of any user.",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "user_id": 1,
                    "address_id": 1,
                    "delivery_slot_id": 1,
                    "items": [{"product_id": 1, "quantity": 2}],
                    "payment_method": "cash",
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

        from accounts.models import User

        user_id = request.data.get("user_id")
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"msg": "User not found."}, status=404)

        address_id = request.data.get("address_id")
        delivery_slot_id = request.data.get("delivery_slot_id")
        items_data = request.data.get("items", [])
        payment_method = request.data.get("payment_method", "cash")

        try:
            address = Address.objects.get(id=address_id, user=user)
        except Address.DoesNotExist:
            return Response({"msg": "Address not found for this user."}, status=404)

        try:
            delivery_slot = DeliverySlot.objects.get(
                id=delivery_slot_id, is_active=True
            )
        except DeliverySlot.DoesNotExist:
            return Response({"msg": "Delivery slot not found."}, status=404)

        if not items_data:
            return Response({"msg": "At least one item is required."}, status=400)

        order = Order.objects.create(
            user=user,
            address=address,
            delivery_slot=delivery_slot,
            status="confirmed",
        )

        total = Decimal("0")
        from products.models import Product

        for item_data in items_data:
            product = Product.objects.get(id=item_data["product_id"])
            quantity = Decimal(str(item_data["quantity"]))
            price = product.price
            item_total = price * quantity
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=price,
                total=item_total,
            )
            total += item_total

        order.total_amount = total
        order.final_amount = total
        order.save(update_fields=["total_amount", "final_amount"])

        from subscriptions.models import Payment

        if payment_method != "razorpay":
            Payment.objects.create(
                user=user,
                order=order,
                payment_for="order",
                amount=order.final_amount,
                payment_method=payment_method,
                payment_status="completed",
                notes="Payment recorded by admin",
            )

        return Response(
            {
                "msg": "Order created successfully by admin.",
                "order": OrderSerializer(order).data,
            },
            status=201,
        )


class AdminAllOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Admin: List all orders",
        description="Super admin can view all orders.",
    )
    def get(self, request):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        orders = Order.objects.all()
        paginator = OrderPagination()
        page = paginator.paginate_queryset(orders, request)
        serializer = OrderSerializer(page, many=True)
        return paginator.get_paginated_response(
            {
                "msg": "All orders fetched successfully.",
                "orders": serializer.data,
            }
        )
