# apps/skin_analysis/admin.py

from django.contrib import admin
from .models import SkinAnalysis, SkinFeature

class SkinFeatureInline(admin.StackedInline):
    """Show features inside analysis admin"""
    model = SkinFeature
    can_delete = False
    readonly_fields = [
        'oiliness_score',
        'dryness_score',
        'texture_density',
        'pore_visibility',
        'redness_score',
    ]


@admin.register(SkinAnalysis)
class SkinAnalysisAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'user_email',
        'skin_type',
        'confidence_percentage',
        'age',
        'gender',
        'status',
        'created_at',
    ]
    
    list_filter = [
        'skin_type',
        'gender',
        'status',
        'created_at',
    ]
    
    search_fields = [
        'user__email',
        'skin_type',
    ]
    
    readonly_fields = [
        'user',
        'image',
        'age',
        'gender',
        'skin_type',
        'confidence_score',
        'confidence_percentage',
        'status',
        'error_message',
        'created_at',
        'completed_at',
    ]
    
    inlines = [SkinFeatureInline]
    
    def user_email(self, obj):
        return obj.user.email if obj.user else 'Guest'
    user_email.short_description = 'User'
    
    def has_add_permission(self, request):
        # Disable manual add (analysis API bata matra)
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Admin le delete garna sakcha
        return request.user.is_superuser


@admin.register(SkinFeature)
class SkinFeatureAdmin(admin.ModelAdmin):
    list_display = [
        'analysis_id',
        'oiliness_score',
        'dryness_score',
        'texture_density',
    ]
    
    readonly_fields = [
        'analysis',
        'oiliness_score',
        'dryness_score',
        'texture_density',
        'pore_visibility',
        'redness_score',
    ]
    
    def analysis_id(self, obj):
        return f"Analysis #{obj.analysis.id}"
    
    def has_add_permission(self, request):
        return False