# apps/recommendations/admin.py

from django.contrib import admin
from .models import Recommendation, RecommendationSession

@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'analysis_id',
        'product_name',
        'rank',
        'match_percentage',
        'user_feedback',
        'is_clicked',
        'created_at',
    ]
    
    list_filter = [
        'user_feedback',
        'is_clicked',
        'rank',
        'created_at',
    ]
    
    search_fields = [
        'product__name',
        'product__brand',
        'analysis__user__email',
    ]
    
    readonly_fields = [
        'analysis',
        'product',
        'match_score',
        'rank',
        'reasoning',
        'skin_type_match',
        'age_match',
        'gender_match',
        'created_at',
    ]
    
    fieldsets = (
        ('Recommendation', {
            'fields': ('analysis', 'product', 'rank')
        }),
        ('Match Scores', {
            'fields': (
                'match_score',
                'skin_type_match',
                'age_match',
                'gender_match',
                'reasoning',
            )
        }),
        ('User Feedback', {
            'fields': (
                'user_feedback',
                'feedback_comment',
                'is_clicked',
                'clicked_at',
            )
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def analysis_id(self, obj):
        return f"#{obj.analysis.id}"
    
    def product_name(self, obj):
        return obj.product.name
    product_name.short_description = 'Product'
    
    def has_add_permission(self, request):
        return False


@admin.register(RecommendationSession)
class RecommendationSessionAdmin(admin.ModelAdmin):
    list_display = [
        'analysis_id',
        'total_products_matched',
        'algorithm_version',
        'processing_time_ms',
        'created_at',
    ]
    
    readonly_fields = [
        'analysis',
        'total_products_matched',
        'algorithm_version',
        'filters_applied',
        'processing_time_ms',
        'created_at',
    ]
    
    def analysis_id(self, obj):
        return f"Analysis #{obj.analysis.id}"
    
    def has_add_permission(self, request):
        return False