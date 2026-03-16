# apps/products/filters.py

import django_filters
from django.db import models
from .models import Product


class ProductFilter(django_filters.FilterSet):
    """
    Product filtering for frontend queries.

    Usage:
    ?min_price=500&max_price=2000
    ?skin_type=oily
    ?brand=himalaya
    ?category=moisturizer
    ?gender=female
    ?concern=acne
    ?search=vitamin c serum
    """

    min_price  = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price  = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    skin_type  = django_filters.CharFilter(field_name='suitable_skin_type')
    brand      = django_filters.CharFilter(field_name='brand',    lookup_expr='iexact')
    category   = django_filters.CharFilter(field_name='category__slug')
    gender     = django_filters.CharFilter(field_name='gender')
    concern    = django_filters.CharFilter(field_name='skin_concern')

    # ── Custom search across name, brand, description ─────────────────────────
    search = django_filters.CharFilter(method='search_products')

    class Meta:
        model = Product
        fields = [
            'suitable_skin_type',
            'gender',
            'skin_concern',
            'is_featured',
            'is_available',
        ]

    def search_products(self, queryset, name, value):
        """Search across name, brand and description."""
        return queryset.filter(
            models.Q(name__icontains=value)        |
            models.Q(brand__icontains=value)       |
            models.Q(description__icontains=value)
        )