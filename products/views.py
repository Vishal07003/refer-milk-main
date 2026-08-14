from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Product, ProductImage
from .serializers import (
    CategorySerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductSerializer,
)


class ProductPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class CategoryListView(APIView):
    serializer_class = CategorySerializer

    @extend_schema(
        summary="List all categories",
        description="Get all active product categories.",
    )
    def get(self, request):
        categories = Category.objects.filter(is_active=True)
        serializer = CategorySerializer(categories, many=True)
        return Response(
            {
                "msg": "Categories fetched successfully.",
                "categories": serializer.data,
            },
            status=200,
        )


class CategoryDetailView(APIView):
    serializer_class = CategorySerializer

    def get_object(self, pk):
        try:
            return Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            return None

    @extend_schema(
        summary="Get category detail",
        description="Get a single category by ID.",
    )
    def get(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"msg": "Category not found."}, status=404)
        serializer = CategorySerializer(category)
        return Response(
            {
                "msg": "Category fetched successfully.",
                "category": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Create a category (Admin only)",
        description="Create a new product category.",
        examples=[
            OpenApiExample(
                "Example", value={"name": "Dairy", "description": "All dairy products"}
            )
        ],
    )
    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Category created successfully.",
                "category": serializer.data,
            },
            status=201,
        )

    @extend_schema(
        summary="Update a category (Admin only)",
        description="Update an existing category.",
    )
    def put(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        category = self.get_object(pk)
        if not category:
            return Response({"msg": "Category not found."}, status=404)
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Category updated successfully.",
                "category": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Delete a category (Admin only)",
        description="Delete a category.",
    )
    def delete(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        category = self.get_object(pk)
        if not category:
            return Response({"msg": "Category not found."}, status=404)
        category.delete()
        return Response({"msg": "Category deleted successfully."}, status=200)


class ProductListView(APIView):
    pagination_class = ProductPagination

    @extend_schema(
        summary="List products",
        description="List products with search, filter, sort, and pagination.",
        parameters=[
            {"name": "search", "type": "str", "description": "Search by name"},
            {"name": "category", "type": "int", "description": "Filter by category ID"},
            {
                "name": "is_subscription_eligible",
                "type": "str",
                "description": "true/false",
            },
            {
                "name": "has_referral_discount",
                "type": "str",
                "description": "true/false",
            },
            {"name": "min_price", "type": "number", "description": "Minimum price"},
            {"name": "max_price", "type": "number", "description": "Maximum price"},
            {
                "name": "sort",
                "type": "str",
                "description": "price, -price, name, -name, -created_at",
            },
            {"name": "page", "type": "int", "description": "Page number"},
            {
                "name": "page_size",
                "type": "int",
                "description": "Items per page (max 50)",
            },
        ],
    )
    def get(self, request):
        products = Product.objects.filter(is_active=True)

        search = request.query_params.get("search")
        if search:
            products = products.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        category = request.query_params.get("category")
        if category:
            products = products.filter(category_id=category)

        is_sub = request.query_params.get("is_subscription_eligible")
        if is_sub is not None:
            products = products.filter(
                is_subscription_eligible=is_sub.lower() == "true"
            )

        has_ref = request.query_params.get("has_referral_discount")
        if has_ref is not None:
            products = products.filter(has_referral_discount=has_ref.lower() == "true")

        min_price = request.query_params.get("min_price")
        if min_price:
            products = products.filter(price__gte=min_price)

        max_price = request.query_params.get("max_price")
        if max_price:
            products = products.filter(price__lte=max_price)

        sort = request.query_params.get("sort", "-created_at")
        allowed_sorts = [
            "price",
            "-price",
            "name",
            "-name",
            "created_at",
            "-created_at",
        ]
        if sort in allowed_sorts:
            products = products.order_by(sort)

        paginator = ProductPagination()
        page = paginator.paginate_queryset(products, request)
        serializer = ProductListSerializer(page, many=True)
        return paginator.get_paginated_response(
            {
                "msg": "Products fetched successfully.",
                "products": serializer.data,
            }
        )


class ProductDetailView(APIView):
    def get_object(self, pk):
        try:
            return Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return None

    @extend_schema(
        summary="Get product detail",
        description="Get a single product by ID with all images.",
    )
    def get(self, request, pk):
        product = self.get_object(pk)
        if not product:
            return Response({"msg": "Product not found."}, status=404)
        serializer = ProductSerializer(product)
        return Response(
            {
                "msg": "Product fetched successfully.",
                "product": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Update a product (Admin only)",
        description="Update an existing product.",
    )
    def put(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        product = self.get_object(pk)
        if not product:
            return Response({"msg": "Product not found."}, status=404)
        serializer = ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Product updated successfully.",
                "product": serializer.data,
            },
            status=200,
        )

    @extend_schema(
        summary="Delete a product (Admin only)",
        description="Delete a product.",
    )
    def delete(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        product = self.get_object(pk)
        if not product:
            return Response({"msg": "Product not found."}, status=404)
        product.delete()
        return Response({"msg": "Product deleted successfully."}, status=200)


class ProductCreateView(APIView):
    serializer_class = ProductSerializer

    @extend_schema(
        summary="Create a product (Admin only)",
        description="Create a new product.",
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "category": 1,
                    "name": "Toned Milk",
                    "description": "Fresh toned milk",
                    "price": 60.00,
                    "unit": "litre",
                    "is_subscription_eligible": True,
                    "has_referral_discount": True,
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
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "msg": "Product created successfully.",
                "product": serializer.data,
            },
            status=201,
        )


class ProductImageUploadView(APIView):
    @extend_schema(
        summary="Upload product image (Admin only)",
        description="Add an additional image to a product.",
    )
    def post(self, request, pk):
        if not request.user.is_staff:
            return Response(
                {"msg": "You do not have permission to perform this action."},
                status=403,
            )
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({"msg": "Product not found."}, status=404)
        image_file = request.FILES.get("image")
        if not image_file:
            return Response({"msg": "No image file provided."}, status=400)
        product_image = ProductImage.objects.create(product=product, image=image_file)
        return Response(
            {
                "msg": "Image uploaded successfully.",
                "image": ProductImageSerializer(product_image).data,
            },
            status=201,
        )
