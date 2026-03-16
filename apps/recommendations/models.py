# apps/recommendations/models.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.skin_analysis.models import SkinAnalysis
from apps.products.models import Product

class Recommendation(models.Model):
    """
    Product Recommendations
    
    Workflow:
    1. SkinAnalysis completes
    2. Matching engine finds suitable products
    3. Recommendations saved here
    4. User can rate/feedback
    """
    
    # ════════════════════════════════════════════════════════════
    # RELATIONS
    # ════════════════════════════════════════════════════════════
    
    analysis = models.ForeignKey(
        SkinAnalysis,
        on_delete=models.CASCADE,
        related_name='recommendations',
        help_text='Source skin analysis'
    )
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='recommendations',
        help_text='Recommended product'
    )
    
    # ════════════════════════════════════════════════════════════
    # MATCHING SCORES
    # ════════════════════════════════════════════════════════════
    
    match_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Overall match score (0.0 - 1.0)'
    )
    
    rank = models.PositiveIntegerField(
        default=0,
        help_text='Recommendation ranking (1st, 2nd, 3rd...)'
    )
    
    # Score breakdown
    skin_type_match = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    
    age_match = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    
    gender_match = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    
    # ════════════════════════════════════════════════════════════
    # MATCH REASON (Human readable)
    # ════════════════════════════════════════════════════════════
    
    reasoning = models.TextField(
        blank=True,
        help_text='Why this product was recommended'
    )
    
    # ════════════════════════════════════════════════════════════
    # USER FEEDBACK
    # ════════════════════════════════════════════════════════════
    
    FEEDBACK_CHOICES = (
        ('none', 'No Feedback'),
        ('liked', 'Liked'),
        ('disliked', 'Disliked'),
        ('purchased', 'Purchased'),
    )
    
    user_feedback = models.CharField(
        max_length=20,
        choices=FEEDBACK_CHOICES,
        default='none',
        db_index=True
    )
    
    feedback_comment = models.TextField(
        blank=True,
        help_text='Optional user comment'
    )
    
    # ════════════════════════════════════════════════════════════
    # METADATA
    # ════════════════════════════════════════════════════════════
    
    is_clicked = models.BooleanField(
        default=False,
        help_text='User le product click garyo ki nai'
    )
    
    clicked_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    # ════════════════════════════════════════════════════════════
    # META
    # ════════════════════════════════════════════════════════════
    
    class Meta:
        verbose_name = 'Recommendation'
        verbose_name_plural = 'Recommendations'
        ordering = ['analysis', 'rank']
        
        # Prevent duplicate recommendations
        unique_together = [['analysis', 'product']]
        
        indexes = [
            models.Index(fields=['analysis', 'rank']),
            models.Index(fields=['product']),
            models.Index(fields=['user_feedback']),
            models.Index(fields=['match_score']),
        ]
    
    def __str__(self):
        return f"{self.product.name} for Analysis #{self.analysis.id} (Rank {self.rank})"
    
    @property
    def match_percentage(self):
        """Match score ko percentage"""
        return round(self.match_score * 100, 2)


class RecommendationSession(models.Model):
    """
    Recommendation session tracking
    
    Groups multiple recommendations together
    Useful for analytics
    """
    
    analysis = models.OneToOneField(
        SkinAnalysis,
        on_delete=models.CASCADE,
        related_name='recommendation_session',
        primary_key=True
    )
    
    total_products_matched = models.PositiveIntegerField(default=0)
    
    algorithm_version = models.CharField(
        max_length=50,
        default='v1.0',
        help_text='Matching algorithm version used'
    )
    
    # Filters applied
    filters_applied = models.JSONField(
        default=dict,
        help_text='Filters used in matching'
    )
    
    # Performance metrics
    processing_time_ms = models.PositiveIntegerField(
        default=0,
        help_text='Time taken to generate recommendations (milliseconds)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Recommendation Session'
        verbose_name_plural = 'Recommendation Sessions'
    
    def __str__(self):
        return f"Session for Analysis #{self.analysis.id}"