# apps/products/views.py — 100% Professional

from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from decimal import Decimal

from .models import Category, Product, Review, Wishlist
from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ReviewSerializer,
)
from .filters import ProductFilter
from core.permissions import IsAdminOrReadOnly
from core.pagination import StandardPagination


# ════════════════════════════════════════════════════════════
# CATEGORY VIEWSET
# ════════════════════════════════════════════════════════════

class CategoryViewSet(viewsets.ModelViewSet):
    queryset           = Category.objects.filter(is_active=True)
    serializer_class   = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field       = 'slug'

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        category   = self.get_object()
        products   = Product.objects.filter(category=category, is_available=True)
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({
            'success':  True,
            'category': category.name,
            'count':    products.count(),
            'products': serializer.data,
        })


# ════════════════════════════════════════════════════════════
# PRODUCT VIEWSET
# ════════════════════════════════════════════════════════════

class ProductViewSet(viewsets.ModelViewSet):
    queryset           = Product.objects.filter(is_available=True)
    permission_classes = [IsAdminOrReadOnly]
    pagination_class   = StandardPagination
    lookup_field       = 'slug'

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ProductFilter
    ordering_fields = ['price', 'created_at', 'views_count']
    ordering        = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page    = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.increment_views()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def featured(self, request):
        products   = Product.objects.filter(is_featured=True, is_available=True)[:12]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({'success': True, 'count': len(products), 'products': serializer.data})

    @action(detail=False, methods=['get'])
    def trending(self, request):
        products   = Product.objects.filter(is_available=True).order_by('-views_count')[:12]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({'success': True, 'count': len(products), 'products': serializer.data})

    @action(detail=False, methods=['get'], url_path='on-sale')
    def on_sale(self, request):
        products   = Product.objects.filter(is_available=True, discount_percent__gt=0).order_by('-discount_percent')[:12]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({'success': True, 'count': len(products), 'products': serializer.data})

    @action(detail=False, methods=['get'], url_path='by-skin-type')
    def by_skin_type(self, request):
        skin_type = request.query_params.get('skin_type')
        if not skin_type:
            return Response({'success': False, 'error': 'skin_type parameter is required.'}, status=400)
        products   = Product.objects.filter(is_available=True, suitable_skin_type__in=[skin_type, 'all'])
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({'success': True, 'skin_type': skin_type, 'count': products.count(), 'products': serializer.data})

    @action(detail=True, methods=['get', 'post'], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def reviews(self, request, slug=None):
        product = self.get_object()

        if request.method == 'GET':
            reviews    = Review.objects.filter(product=product).select_related('user')
            serializer = ReviewSerializer(reviews, many=True)
            return Response({'count': reviews.count(), 'results': serializer.data})

        if Review.objects.filter(product=product, user=request.user).exists():
            return Response({'success': False, 'error': 'You have already reviewed this product.'}, status=400)

        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(product=product, user=request.user)
            return Response({'success': True, 'message': 'Review submitted!', 'review': serializer.data}, status=201)

        return Response({'success': False, 'error': serializer.errors}, status=400)


# ════════════════════════════════════════════════════════════
# WISHLIST VIEWSET
# ════════════════════════════════════════════════════════════

class WishlistViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        items      = Wishlist.objects.filter(user=request.user).select_related('product')
        products   = [item.product for item in items]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({'success': True, 'count': len(products), 'results': serializer.data})

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'success': False, 'error': 'product_id is required.'}, status=400)
        try:
            product = Product.objects.get(id=product_id, is_available=True)
        except Product.DoesNotExist:
            return Response({'success': False, 'error': 'Product not found.'}, status=404)

        item, created = Wishlist.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.delete()
            return Response({'success': True, 'action': 'removed', 'wishlisted': False,
                             'message': f'{product.name} removed from wishlist.'})
        return Response({'success': True, 'action': 'added', 'wishlisted': True,
                         'message': f'{product.name} added to wishlist! ❤️'}, status=201)

    @action(detail=False, methods=['get'])
    def ids(self, request):
        ids = Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
        return Response({'success': True, 'ids': list(ids)})

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        count, _ = Wishlist.objects.filter(user=request.user).delete()
        return Response({'success': True, 'message': f'Wishlist cleared. {count} item(s) removed.'})


# ════════════════════════════════════════════════════════════
# SEARCH SUGGESTIONS — 100% Professional
# ════════════════════════════════════════════════════════════

def _build_multi_word_query(q, fields):
    """
    Multi-word search: 'wow skin' → matches products containing 'wow' AND 'skin'
    Each word must appear in at least one of the given fields.
    """
    words = q.split()
    query = Q()
    for word in words:
        word_q = Q()
        for field in fields:
            word_q |= Q(**{f'{field}__icontains': word})
        query &= word_q
    return query


class SearchSuggestionsView(APIView):
    """
    GET /api/products/search/suggestions/?q=wow skin
    Returns: { products, brands, categories }
    Minimum 3 characters required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        q = request.query_params.get('q', '').strip()

        # ✅ Industry standard: minimum 3 characters
        if len(q) < 3:
            return Response({'products': [], 'brands': [], 'categories': []})

        # ✅ Multi-word search across name + brand + description
        product_query = _build_multi_word_query(q, ['name', 'brand', 'description'])

        products_qs = (
            Product.objects
            .filter(product_query, is_available=True)
            .values('name', 'slug', 'brand', 'price', 'discount_percent', 'image')
            .order_by('name')[:5]
        )

        # ✅ Multi-word brand search
        brand_query = _build_multi_word_query(q, ['brand'])
        brands = list(
            Product.objects
            .filter(brand_query, is_available=True)
            .values_list('brand', flat=True)
            .distinct()
            .order_by('brand')[:4]
        )

        # ✅ Category search
        cat_query = _build_multi_word_query(q, ['name'])
        categories = list(
            Category.objects
            .filter(cat_query)
            .values('id', 'name')
            .order_by('name')[:3]
        )

        # ✅ Compute discounted_price safely with Decimal
        product_list = []
        for p in products_qs:
            price      = Decimal(str(p['price']))
            discount   = Decimal(str(p['discount_percent'] or 0))
            discounted = round(price * (1 - discount / 100), 2)
            product_list.append({
                'name':             p['name'],
                'slug':             p['slug'],
                'brand':            p['brand'],
                'discounted_price': str(discounted),
                'image': f"http://127.0.0.1:8000{p['image']}" if p['image'] else None,
            })

        return Response({
            'products':   product_list,
            'brands':     brands,
            'categories': categories,
        })