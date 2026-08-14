from django.urls import path

from .views import (
    AdminAllOrdersView,
    AdminCreateOrderView,
    CreateOrderView,
    DeliverySlotDetailView,
    DeliverySlotListView,
    MyOrdersView,
    OrderDetailView,
    VerifyPaymentView,
)

app_name = 'orders'

urlpatterns = [
    path('slots/', DeliverySlotListView.as_view(), name='slot-list'),
    path('slots/create/', DeliverySlotDetailView.as_view(), name='slot-create'),
    path('slots/<int:pk>/', DeliverySlotDetailView.as_view(), name='slot-detail'),
    path('create-order/', CreateOrderView.as_view(), name='create-order'),
    path('verify-payment/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('my/', MyOrdersView.as_view(), name='my-orders'),
    path('<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('<int:pk>/cancel/', OrderDetailView.as_view(), name='order-cancel'),
    path('admin-create/', AdminCreateOrderView.as_view(), name='admin-create-order'),
    path('admin-all/', AdminAllOrdersView.as_view(), name='admin-all-orders'),
]
