"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from accounts.views import RazorpayWebhookView
from core.admin_views import (
    AdminDashboardView,
    AdminStatsAPIView,
    AdminOfflineCollectionsAPIView,
    AdminVerifyOfflinePaymentActionView,
    AdminCashCollectionDetailAPIView,
    AdminCustomersAPIView,
    AdminCreateCustomerAPIView,
    AdminCustomerDetailAPIView,
    AdminSubscriptionPlansAPIView,
    AdminSubscriptionsAPIView,
    AdminSubscriptionDetailAPIView,
    AdminCreateSubscriptionAPIView,
    AdminOrdersAPIView,
    AdminOrderDetailAPIView,
    AdminAssignOrderActionAPIView,
    AdminDeliveryBoysAPIView,
    AdminCreateDeliveryBoyAPIView,
    AdminDeliveryBoyDetailAPIView,
    AdminProductsAPIView,
    AdminCategoriesAPIView,
    AdminCashHandoversAPIView,
    AdminConfirmCashHandoverActionView,
    AdminReferralsAPIView,
    AdminNotificationsAPIView,
    AdminSettingsAPIView,
    AdminReportsAPIView,
    AdminDeliverySlotsAPIView,
    AdminDeliverySlotDetailAPIView,
    AdminRecycleBinAPIView,
    AdminVacationsAPIView,
    AdminLoginView,
    AdminLogoutView,
    AdminForgotPasswordView,
    AdminResetPasswordConfirmView,
    AdminVerifyOtpView,
    AdminResetPasswordWithOtpView,
    AdminAccountSettingsAPIView,
    AdminInitiateContactChangeAPIView,
    AdminVerifyContactChangeAPIView,
    AdminChangePasswordAPIView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('dairypanel/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('dairypanel/login/', AdminLoginView.as_view(), name='admin-login'),
    path('dairypanel/logout/', AdminLogoutView.as_view(), name='admin-logout'),
    path('dairypanel/forgot-password/', AdminForgotPasswordView.as_view(), name='admin-forgot-password'),
    path('dairypanel/verify-otp/', AdminVerifyOtpView.as_view(), name='admin-verify-otp'),
    path('dairypanel/reset-password-otp/<str:token>/', AdminResetPasswordWithOtpView.as_view(), name='admin-reset-password-otp'),
    path('dairypanel/reset-password/<uidb64>/<token>/', AdminResetPasswordConfirmView.as_view(), name='admin-reset-password-confirm'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard-alias'),
    path('api/admin/logout/', AdminLogoutView.as_view(), name='api-admin-logout'),
    path('api/admin/stats/', AdminStatsAPIView.as_view(), name='admin-stats'),
    path('api/admin/vacations/', AdminVacationsAPIView.as_view(), name='admin-vacations-api'),
    path('api/admin/recycle-bin/', AdminRecycleBinAPIView.as_view(), name='admin-recycle-bin-api'),
    path('api/admin/reports/', AdminReportsAPIView.as_view(), name='admin-reports-api'),
    path('api/admin/cash-handovers/', AdminCashHandoversAPIView.as_view(), name='admin-cash-handovers-api'),
    path('api/admin/cash-handovers/<int:pk>/confirm/', AdminConfirmCashHandoverActionView.as_view(), name='admin-confirm-cash-handover-api'),
    path('api/admin/offline-collections/', AdminOfflineCollectionsAPIView.as_view(), name='admin-offline-collections-api'),
    path('api/admin/offline-collections/<int:pk>/action/', AdminVerifyOfflinePaymentActionView.as_view(), name='admin-offline-action-api'),
    path('api/admin/offline-collections/<int:pk>/', AdminCashCollectionDetailAPIView.as_view(), name='admin-offline-detail-api'),
    path('api/admin/customers/', AdminCustomersAPIView.as_view(), name='admin-customers-api'),
    path('api/admin/customers/create/', AdminCreateCustomerAPIView.as_view(), name='admin-customers-create-api'),
    path('api/admin/customers/<int:pk>/', AdminCustomerDetailAPIView.as_view(), name='admin-customer-detail-api'),
    path('api/admin/subscription-plans/', AdminSubscriptionPlansAPIView.as_view(), name='admin-subscription-plans-api'),
    path('api/admin/subscriptions/', AdminSubscriptionsAPIView.as_view(), name='admin-subscriptions-api'),
    path('api/admin/subscriptions/create/', AdminCreateSubscriptionAPIView.as_view(), name='admin-subscriptions-create-api'),
    path('api/admin/subscriptions/<int:pk>/', AdminSubscriptionDetailAPIView.as_view(), name='admin-subscription-detail-api'),
    path('api/admin/orders/', AdminOrdersAPIView.as_view(), name='admin-orders-api'),
    path('api/admin/orders/<int:pk>/', AdminOrderDetailAPIView.as_view(), name='admin-order-detail-api'),
    path('api/admin/orders/<int:pk>/assign/', AdminAssignOrderActionAPIView.as_view(), name='admin-assign-order-api'),
    path('api/admin/delivery-boys/', AdminDeliveryBoysAPIView.as_view(), name='admin-boys-api'),
    path('api/admin/delivery-boys/create/', AdminCreateDeliveryBoyAPIView.as_view(), name='admin-boys-create-api'),
    path('api/admin/delivery-boys/<int:pk>/', AdminDeliveryBoyDetailAPIView.as_view(), name='admin-boy-detail-api'),
    path('api/admin/products/', AdminProductsAPIView.as_view(), name='admin-products-api'),
    path('api/admin/categories/', AdminCategoriesAPIView.as_view(), name='admin-categories-api'),
    path('api/admin/referrals/', AdminReferralsAPIView.as_view(), name='admin-referrals-api'),
    path('api/admin/notifications/', AdminNotificationsAPIView.as_view(), name='admin-notifications-api'),
    path('api/admin/settings/', AdminSettingsAPIView.as_view(), name='admin-settings-api'),
    path('api/admin/delivery-slots/', AdminDeliverySlotsAPIView.as_view(), name='admin-delivery-slots-api'),
    path('api/admin/delivery-slots/<int:pk>/', AdminDeliverySlotDetailAPIView.as_view(), name='admin-delivery-slot-detail-api'),
    path('api/admin/account/settings/', AdminAccountSettingsAPIView.as_view(), name='admin-account-settings-api'),
    path('api/admin/account/initiate-contact-change/', AdminInitiateContactChangeAPIView.as_view(), name='admin-initiate-contact-change-api'),
    path('api/admin/account/verify-contact-change/', AdminVerifyContactChangeAPIView.as_view(), name='admin-verify-contact-change-api'),
    path('api/admin/account/change-password/', AdminChangePasswordAPIView.as_view(), name='admin-change-password-api'),

    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/wallet/', include('accounts.wallet_urls')),
    path('api/v1/payments/razorpay/webhook/', RazorpayWebhookView.as_view(), name='razorpay-webhook'),
    path('api/v1/subscriptions/', include('subscriptions.urls')),
    path('api/v1/products/', include('products.urls')),
    path('api/v1/orders/', include('orders.urls')),
    path('api/v1/delivery/', include('delivery.urls')),

    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
