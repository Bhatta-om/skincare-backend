# apps/products/serializers.py — 100% Professional

from rest_framework import serializers
from django.db.models import Avg, Count
from .models import Category, Product, Review
from core.utils import validate_image_file


# ════════════════════════════════════════════════════════════
# CATEGORY
# ════════════════════════════════════════════════════════════

class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model  = Category
        fields = ['id','name','slug','description','image','is_active','product_count','created_at']
        read_only_fields = ['id','slug','created_at']

    def get_product_count(self, obj):
        return obj.products.filter(is_available=True).count()


# ════════════════════════════════════════════════════════════
# PRODUCT LIST — Card मा stars + count देखाउन
# ════════════════════════════════════════════════════════════

class ProductListSerializer(serializers.ModelSerializer):
    category_name    = serializers.CharField(source='category.name', read_only=True)
    discounted_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    stock_status     = serializers.CharField(read_only=True)

    # ✅ NEW — Ratings summary for product card
    avg_rating       = serializers.SerializerMethodField()
    review_count     = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            'id','slug','name','brand','category_name',
            'image','price','discount_percent','discounted_price',
            'suitable_skin_type','gender','stock_status','is_featured',
            'avg_rating','review_count',   # ✅ NEW
        ]

    def get_avg_rating(self, obj):
        result = obj.reviews.aggregate(avg=Avg('rating'))
        avg    = result['avg']
        return round(float(avg), 1) if avg else 0.0

    def get_review_count(self, obj):
        return obj.reviews.count()


# ════════════════════════════════════════════════════════════
# PRODUCT DETAIL — Full rating breakdown
# ════════════════════════════════════════════════════════════

class ProductDetailSerializer(serializers.ModelSerializer):
    category         = CategorySerializer(read_only=True)
    discounted_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    stock_status     = serializers.CharField(read_only=True)
    is_low_stock     = serializers.BooleanField(read_only=True)

    # ✅ NEW — Full ratings summary
    avg_rating          = serializers.SerializerMethodField()
    review_count        = serializers.SerializerMethodField()
    rating_distribution = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            'id','slug','name','brand','category',
            'description','ingredients',
            'price','discount_percent','discounted_price',
            'suitable_skin_type','skin_concern','min_age','max_age','gender',
            'image','image_2','image_3',
            'stock','stock_status','is_low_stock','is_available','is_featured',
            'views_count','created_at','updated_at',
            'avg_rating','review_count','rating_distribution',  # ✅ NEW
        ]
        read_only_fields = ['id','slug','views_count','created_at','updated_at']

    def get_avg_rating(self, obj):
        result = obj.reviews.aggregate(avg=Avg('rating'))
        avg    = result['avg']
        return round(float(avg), 1) if avg else 0.0

    def get_review_count(self, obj):
        return obj.reviews.count()

    def get_rating_distribution(self, obj):
        """5★→1★ breakdown with count + percentage"""
        total = obj.reviews.count()
        dist  = {}
        for entry in obj.reviews.values('rating').annotate(count=Count('rating')):
            dist[entry['rating']] = entry['count']

        return [
            {
                'star':    star,
                'count':   dist.get(star, 0),
                'percent': round(dist.get(star, 0) / total * 100) if total else 0,
            }
            for star in [5, 4, 3, 2, 1]
        ]


# ════════════════════════════════════════════════════════════
# PRODUCT CREATE/UPDATE
# ════════════════════════════════════════════════════════════

class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Product
        fields = [
            'name','brand','category','description','ingredients',
            'price','discount_percent',
            'suitable_skin_type','skin_concern','min_age','max_age','gender',
            'image','image_2','image_3',
            'stock','is_available','is_featured','low_stock_threshold',
        ]

    def validate_image(self, value):
        if value:
            validate_image_file(value)
        return value

    def validate(self, attrs):
        min_age = attrs.get('min_age')
        max_age = attrs.get('max_age')
        if min_age and max_age and min_age > max_age:
            raise serializers.ValidationError({'min_age': 'Minimum age cannot be greater than maximum age!'})
        return attrs


# ════════════════════════════════════════════════════════════
# RECOMMENDATION
# ════════════════════════════════════════════════════════════

class RecommendedProductSerializer(serializers.ModelSerializer):
    discounted_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    match_score      = serializers.FloatField(read_only=True, default=0.0)
    match_reason     = serializers.CharField(read_only=True, default='')
    avg_rating       = serializers.SerializerMethodField()
    review_count     = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            'id','slug','name','brand','image',
            'price','discounted_price',
            'suitable_skin_type','skin_concern',
            'match_score','match_reason',
            'avg_rating','review_count',
        ]

    def get_avg_rating(self, obj):
        result = obj.reviews.aggregate(avg=Avg('rating'))
        avg    = result['avg']
        return round(float(avg), 1) if avg else 0.0

    def get_review_count(self, obj):
        return obj.reviews.count()


# ════════════════════════════════════════════════════════════
# REVIEW — Verified Purchase badge थपियो
# ════════════════════════════════════════════════════════════

class ReviewSerializer(serializers.ModelSerializer):
    user_name          = serializers.SerializerMethodField()
    is_verified_purchase = serializers.SerializerMethodField()

    class Meta:
        model  = Review
        fields = ['id','user_name','rating','comment','created_at','is_verified_purchase']
        read_only_fields = ['id','user_name','created_at','is_verified_purchase']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email.split('@')[0]

    def get_is_verified_purchase(self, obj):
        """Check if user has actually ordered this product"""
        from apps.orders.models import OrderItem
        return OrderItem.objects.filter(
            order__user    = obj.user,
            product        = obj.product,
            order__status__in = ['confirmed', 'shipped', 'delivered'],
        ).exists()