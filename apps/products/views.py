# apps/products/views.py — 100% Professional

from rest_framework import viewsets, filters, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from decimal import Decimal
import csv
import io
import logging
import requests as req
import cloudinary.uploader

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

logger = logging.getLogger(__name__)


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

    # ── FIX: Reset file pointers before Cloudinary upload ──
    # Without this, the file content is empty b'' when Cloudinary
    # tries to read it, causing "Empty file" BadRequest error.
    def _reset_file_pointers(self):
        for field in ['image', 'image_2', 'image_3']:
            file = self.request.FILES.get(field)
            if file and hasattr(file, 'seek'):
                file.seek(0)

    def perform_create(self, serializer):
        self._reset_file_pointers()
        serializer.save()

    def perform_update(self, serializer):
        self._reset_file_pointers()
        serializer.save()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page     = self.paginate_queryset(queryset)
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
                         'message': f'{product.name} added to wishlist!'}, status=201)

    @action(detail=False, methods=['get'])
    def ids(self, request):
        ids = Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
        return Response({'success': True, 'ids': list(ids)})

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        count, _ = Wishlist.objects.filter(user=request.user).delete()
        return Response({'success': True, 'message': f'Wishlist cleared. {count} item(s) removed.'})


# ════════════════════════════════════════════════════════════
# SEARCH SUGGESTIONS
# ════════════════════════════════════════════════════════════

def _build_multi_word_query(q, fields):
    words = q.split()
    query = Q()
    for word in words:
        word_q = Q()
        for field in fields:
            word_q |= Q(**{f'{field}__icontains': word})
        query &= word_q
    return query


class SearchSuggestionsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        q = request.query_params.get('q', '').strip()

        if len(q) < 3:
            return Response({'products': [], 'brands': [], 'categories': []})

        product_query = _build_multi_word_query(q, ['name', 'brand', 'description'])
        products_qs   = (
            Product.objects
            .filter(product_query, is_available=True)
            .values('name', 'slug', 'brand', 'price', 'discount_percent', 'image')
            .order_by('name')[:5]
        )

        brand_query = _build_multi_word_query(q, ['brand'])
        brands = list(
            Product.objects
            .filter(brand_query, is_available=True)
            .values_list('brand', flat=True)
            .distinct()
            .order_by('brand')[:4]
        )

        cat_query  = _build_multi_word_query(q, ['name'])
        categories = list(
            Category.objects
            .filter(cat_query)
            .values('id', 'name')
            .order_by('name')[:3]
        )

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


# ════════════════════════════════════════════════════════════
# BULK IMPORT — CSV Upload with Image URL Support
# ════════════════════════════════════════════════════════════

class BulkImportView(APIView):
    permission_classes = [permissions.IsAdminUser]
    parser_classes     = [MultiPartParser]

    def post(self, request):
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'success': False, 'error': 'No file uploaded.'}, status=400)

        if not csv_file.name.endswith('.csv'):
            return Response({'success': False, 'error': 'File must be a CSV.'}, status=400)

        try:
            decoded = csv_file.read().decode('utf-8')
            reader  = csv.DictReader(io.StringIO(decoded))
        except Exception as e:
            return Response({'success': False, 'error': f'Failed to read CSV: {str(e)}'}, status=400)

        results = []
        created = 0
        failed  = 0
        skipped = 0

        for row_num, row in enumerate(reader, start=2):
            row_result = {'row': row_num, 'name': row.get('name', '').strip()}

            try:
                name = row.get('name', '').strip()
                if not name:
                    row_result.update({'status': 'skipped', 'reason': 'Name is empty'})
                    skipped += 1
                    results.append(row_result)
                    continue

                if Product.objects.filter(name=name).exists():
                    row_result.update({'status': 'skipped', 'reason': f'Product "{name}" already exists'})
                    skipped += 1
                    results.append(row_result)
                    continue

                category_name = row.get('category', '').strip()
                category = None
                if category_name:
                    try:
                        category = Category.objects.get(name__iexact=category_name)
                    except Category.DoesNotExist:
                        row_result.update({'status': 'failed', 'reason': f'Category "{category_name}" not found'})
                        failed += 1
                        results.append(row_result)
                        continue

                def safe_decimal(val, default='0'):
                    try:
                        return Decimal(str(val).strip() or default)
                    except Exception:
                        return Decimal(default)

                def safe_int(val, default=0):
                    try:
                        return int(str(val).strip() or default)
                    except Exception:
                        return default

                valid_skin_types = ['normal', 'dry', 'oily', 'combination', 'sensitive', 'all']
                valid_concerns   = ['acne', 'aging', 'brightening', 'hydration', 'pigmentation', 'sensitivity', 'general']
                valid_genders    = ['male', 'female', 'unisex']

                skin_type = row.get('suitable_skin_type', 'all').strip().lower()
                concern   = row.get('skin_concern', 'general').strip().lower()
                gender    = row.get('gender', 'unisex').strip().lower()

                if skin_type not in valid_skin_types: skin_type = 'all'
                if concern   not in valid_concerns:   concern   = 'general'
                if gender    not in valid_genders:    gender    = 'unisex'

                price    = safe_decimal(row.get('price', '0'))
                discount = safe_decimal(row.get('discount_percent', '0'))
                stock    = safe_int(row.get('stock', 0))
                min_age  = safe_int(row.get('min_age', 13), 13)
                max_age  = safe_int(row.get('max_age', 65), 65)

                if price <= 0:
                    row_result.update({'status': 'failed', 'reason': 'Price must be greater than 0'})
                    failed += 1
                    results.append(row_result)
                    continue

                from django.utils.text import slugify
                base_slug = slugify(f"{row.get('brand', '').strip()}-{name}")
                slug      = base_slug
                counter   = 1
                while Product.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1

                product = Product.objects.create(
                    name                = name,
                    slug                = slug,
                    brand               = row.get('brand', '').strip() or 'Unknown',
                    category            = category,
                    description         = row.get('description', '').strip(),
                    ingredients         = row.get('ingredients', '').strip(),
                    price               = price,
                    discount_percent    = discount,
                    suitable_skin_type  = skin_type,
                    skin_concern        = concern,
                    min_age             = min_age,
                    max_age             = max_age,
                    gender              = gender,
                    stock               = stock,
                    is_available        = stock > 0,
                    is_featured         = str(row.get('is_featured', 'false')).strip().lower() == 'true',
                    low_stock_threshold = safe_int(row.get('low_stock_threshold', 10), 10),
                )

                image_url = row.get('image_url', '').strip()
                if image_url:
                    try:
                        img_response = req.get(image_url, timeout=15)
                        if img_response.status_code == 200:
                            upload_result = cloudinary.uploader.upload(
                                img_response.content,
                                folder    = 'products',
                                public_id = slug,
                                overwrite = True,
                            )
                            product.image = upload_result['public_id']
                            product.save(update_fields=['image'])
                            logger.info("Image uploaded for %s", name)
                        else:
                            logger.warning("Image URL returned %s for %s", img_response.status_code, name)
                    except Exception as img_err:
                        logger.warning("Image upload failed for %s: %s", name, str(img_err))

                created += 1
                row_result.update({
                    'status': 'success',
                    'id':     product.id,
                    'image':  'uploaded' if image_url else 'no image',
                })

            except Exception as e:
                row_result.update({'status': 'failed', 'reason': str(e)})
                failed += 1

            results.append(row_result)

        return Response({
            'success': True,
            'summary': {
                'total':   created + failed + skipped,
                'created': created,
                'failed':  failed,
                'skipped': skipped,
            },
            'results': results,
        })