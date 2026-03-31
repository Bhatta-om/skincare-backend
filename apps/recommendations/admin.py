# apps/recommendations/admin.py

from django.contrib import admin
from .models import Recommendation, RecommendationSession, DermaProfile


@admin.register(DermaProfile)
class DermaProfileAdmin(admin.ModelAdmin):
    """
    Admin interface for the Dermatological Knowledge Base.
    Admins can update ingredient lists without a code deploy.
    """
    list_display  = ['skin_type', 'age_group', 'gender', 'source', 'updated_at']
    list_filter   = ['skin_type', 'age_group', 'gender']
    search_fields = ['primary_ingredients', 'secondary_ingredients', 'source']
    ordering      = ['skin_type', 'age_group', 'gender']

    fieldsets = (
        ('Profile Identity', {
            'fields': ('skin_type', 'age_group', 'gender'),
        }),
        ('Dermatologist-Validated Ingredients', {
            'description': (
                'Sources: AAD aad.org, JAAD Delphi Consensus, '
                'Baumann BSTI (PubMed 18555952), Northwestern Study'
            ),
            'fields': ('primary_ingredients', 'secondary_ingredients', 'avoid_ingredients'),
        }),
        ('Skin Concerns', {
            'fields': ('key_concerns',),
        }),
        ('Citation', {
            'fields': ('source',),
        }),
    )


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display  = ['product', 'analysis', 'rank', 'match_score', 'user_feedback', 'is_clicked']
    list_filter   = ['user_feedback', 'is_clicked']
    search_fields = ['product__name', 'reasoning']
    ordering      = ['analysis', 'rank']
    readonly_fields = ['match_score', 'skin_type_match', 'age_match', 'gender_match',
                       'reasoning', 'created_at', 'clicked_at']


@admin.register(RecommendationSession)
class RecommendationSessionAdmin(admin.ModelAdmin):
    list_display  = ['analysis', 'total_products_matched', 'algorithm_version',
                     'processing_time_ms', 'created_at']
    readonly_fields = ['analysis', 'total_products_matched', 'algorithm_version',
                       'filters_applied', 'processing_time_ms', 'created_at']