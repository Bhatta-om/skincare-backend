# apps/products/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Product
from django.db import models


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'brand',
        'category',
        'price',
        'discounted_price',
        'stock',
        'stock_status_colored',   # ← NEW: Color coded stock
        'suitable_skin_type',
        'is_available',
        'is_featured',
        'views_count',
    ]

    list_filter = [
        'suitable_skin_type',
        'gender',
        'skin_concern',
        'is_available',
        'is_featured',
        'category',
        'created_at',
    ]

    search_fields = ['name', 'brand', 'description', 'ingredients']
    prepopulated_fields = {'slug': ('brand', 'name')}

    readonly_fields = [
        'views_count',
        'created_at',
        'updated_at',
        'discounted_price',
        'stock_status',
    ]

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'slug', 'brand', 'category', 'description', 'ingredients')
        }),
        ('Pricing', {
            'fields': ('price', 'discount_percent', 'discounted_price')
        }),
        ('AI Matching', {
            'fields': ('suitable_skin_type', 'skin_concern', 'min_age', 'max_age', 'gender')
        }),
        ('Images', {
            'fields': ('image', 'image_2', 'image_3')
        }),
        ('Inventory', {
            'fields': ('stock', 'is_available', 'low_stock_threshold', 'stock_status')
        }),
        ('Metadata', {
            'fields': ('is_featured', 'views_count', 'created_at', 'updated_at')
        }),
    )

    actions = [
        'mark_as_featured',
        'mark_as_not_featured',
        'mark_as_unavailable',
        'show_low_stock',         # ← NEW
    ]

    # ── Color coded stock status ───────────────────────────────────────────────
    def stock_status_colored(self, obj):
        if obj.stock == 0:
            return format_html(
                '<span style="color:white; background:#E74C3C; padding:2px 8px; border-radius:4px;">Out of Stock</span>'
            )
        elif obj.stock <= obj.low_stock_threshold:
            return format_html(
                '<span style="color:white; background:#F39C12; padding:2px 8px; border-radius:4px;">Low: {}</span>',
                obj.stock
            )
        else:
            return format_html(
                '<span style="color:white; background:#27AE60; padding:2px 8px; border-radius:4px;">In Stock: {}</span>',
                obj.stock
            )
    stock_status_colored.short_description = 'Stock'

    # ── Actions ────────────────────────────────────────────────────────────────
    def mark_as_featured(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, f'{queryset.count()} products marked as featured!')
    mark_as_featured.short_description = "Mark as Featured"

    def mark_as_not_featured(self, request, queryset):
        queryset.update(is_featured=False)
        self.message_user(request, f'{queryset.count()} products removed from featured!')
    mark_as_not_featured.short_description = "Remove from Featured"

    def mark_as_unavailable(self, request, queryset):
        queryset.update(is_available=False)
        self.message_user(request, f'{queryset.count()} products marked unavailable!')
    mark_as_unavailable.short_description = "Mark as Unavailable"

    # ── Low stock alert ────────────────────────────────────────────────────────
    def show_low_stock(self, request, queryset):
        low = queryset.filter(stock__lte=models.F('low_stock_threshold'))
        count = low.count()
        if count:
            names = ', '.join([p.name for p in low[:5]])
            self.message_user(
                request,
                f'{count} low stock products: {names}',
                level='WARNING'
            )
        else:
            self.message_user(request, 'No low stock products!')
    show_low_stock.short_description = "Check Low Stock Alert"