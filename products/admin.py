from django.contrib import admin

from .models import Category, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'category', 'price', 'unit',
        'is_active', 'is_subscription_eligible', 'has_referral_discount', 'created_at',
    )
    list_filter = ('is_active', 'is_subscription_eligible', 'has_referral_discount', 'category', 'unit')
    search_fields = ('name', 'description')
    inlines = [ProductImageInline]
    ordering = ('-created_at',)
