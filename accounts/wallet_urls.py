from django.urls import path
from .views import (
    GetWalletView,
    CreateWalletTopupView,
    VerifyWalletTopupView,
    WalletTransactionHistoryView,
)

urlpatterns = [
    path('', GetWalletView.as_view(), name='wallet-detail'),
    path('create-topup/', CreateWalletTopupView.as_view(), name='wallet-create-topup'),
    path('verify-topup/', VerifyWalletTopupView.as_view(), name='wallet-verify-topup'),
    path('transactions/', WalletTransactionHistoryView.as_view(), name='wallet-transactions'),
]
