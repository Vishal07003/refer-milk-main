from django.urls import path

from .views import (
    CategoryDetailView,
    CategoryListView,
    ProductCreateView,
    ProductDetailView,
    ProductImageUploadView,
    ProductListView,
)

app_name = 'products'

urlpatterns = [
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('categories/<int:pk>/', CategoryDetailView.as_view(), name='category-detail'),
    path('', ProductListView.as_view(), name='product-list'),
    path('create/', ProductCreateView.as_view(), name='product-create'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('<int:pk>/upload-image/', ProductImageUploadView.as_view(), name='product-upload-image'),
]
