from django.urls import path

from .views import (
    AdminCreateSubscriptionView,
    CancelSubscriptionPreviewView,
    CancelSubscriptionView,
    CreateSubscriptionView,
    MySubscriptionsView,
    PaymentDetailView,
    PaymentHistoryView,
    ReferralDiscountTierDetailView,
    ReferralDiscountTierListView,
    SubscriptionDetailView,
    VerifySubscriptionPaymentView,
    WalletAddMoneyView,
    WalletTransactionsView,
    WalletCreateOrderView,
    WalletVerifyPaymentView,
)

app_name = 'subscriptions'

urlpatterns = [
    path('discount-tiers/', ReferralDiscountTierListView.as_view(), name='discount-tier-list'),
    path('discount-tiers/create/', ReferralDiscountTierDetailView.as_view(), name='discount-tier-create'),
    path('discount-tiers/<int:pk>/', ReferralDiscountTierDetailView.as_view(), name='discount-tier-detail'),
    path('create/', CreateSubscriptionView.as_view(), name='create-subscription'),
    path('verify-payment/', VerifySubscriptionPaymentView.as_view(), name='verify-subscription-payment'),
    path('my/', MySubscriptionsView.as_view(), name='my-subscriptions'),
    path('admin-create/', AdminCreateSubscriptionView.as_view(), name='admin-create-subscription'),
    path('<int:pk>/', SubscriptionDetailView.as_view(), name='subscription-detail'),
    path('<int:pk>/cancel-preview/', CancelSubscriptionPreviewView.as_view(), name='cancel-preview'),
    path('<int:pk>/cancel/', CancelSubscriptionView.as_view(), name='cancel-subscription'),
    path('payments/', PaymentHistoryView.as_view(), name='payment-history'),
    path('payments/<int:pk>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('wallet/add/', WalletAddMoneyView.as_view(), name='wallet-add-money'),
    path('wallet/create-order/', WalletCreateOrderView.as_view(), name='wallet-create-order'),
    path('wallet/verify/', WalletVerifyPaymentView.as_view(), name='wallet-verify-payment'),
    path('wallet/transactions/', WalletTransactionsView.as_view(), name='wallet-transactions'),
]
