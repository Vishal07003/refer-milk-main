from django.urls import path

from .views import (
    AcceptOrderView,
    AdminAssignOrderView,
    AdminAssignSubscriptionView,
    AdminCreateDeliveryBoyView,
    AdminDeliveryBoyDetailView,
    AdminDeliveryBoysListView,
    AvailableOrdersView,
    DeliveryBoyProfileView,
    DeliveryDailyDetailView,
    DeliveryOrderDetailView,
    MyOrdersView,
    MySubscriptionDeliveriesView,
    ToggleAvailabilityView,
    UpdateDailyDeliveryStatusView,
    UpdateDeliveryBoyProfileView,
    UpdateOrderDeliveryStatusView,
)

app_name = 'delivery'

urlpatterns = [
    path('profile/', DeliveryBoyProfileView.as_view(), name='profile'),
    path('profile/update/', UpdateDeliveryBoyProfileView.as_view(), name='profile-update'),
    path('toggle-availability/', ToggleAvailabilityView.as_view(), name='toggle-availability'),
    path('available-orders/', AvailableOrdersView.as_view(), name='available-orders'),
    path('my-orders/', MyOrdersView.as_view(), name='my-orders'),
    path('orders/<int:pk>/', DeliveryOrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/accept/', AcceptOrderView.as_view(), name='accept-order'),
    path('orders/<int:pk>/update-status/', UpdateOrderDeliveryStatusView.as_view(), name='update-order-status'),
    path('my-subscriptions/', MySubscriptionDeliveriesView.as_view(), name='my-subscriptions'),
    path('daily-deliveries/<int:pk>/', DeliveryDailyDetailView.as_view(), name='daily-delivery-detail'),
    path('daily-deliveries/<int:pk>/update-status/', UpdateDailyDeliveryStatusView.as_view(), name='update-daily-delivery-status'),
    path('admin/create-boy/', AdminCreateDeliveryBoyView.as_view(), name='admin-create-boy'),
    path('admin/boys/', AdminDeliveryBoysListView.as_view(), name='admin-boys-list'),
    path('admin/boys/<int:pk>/', AdminDeliveryBoyDetailView.as_view(), name='admin-boy-detail'),
    path('admin/assign-order/', AdminAssignOrderView.as_view(), name='admin-assign-order'),
    path('admin/assign-subscription/', AdminAssignSubscriptionView.as_view(), name='admin-assign-subscription'),
]
