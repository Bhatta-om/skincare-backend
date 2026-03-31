# apps/recommendations/models.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.skin_analysis.models import SkinAnalysis
from apps.products.models import Product


# ═══════════════════════════════════════════════════════════════════════════════
# DERMA PROFILE MODEL
#
# Admin-editable version of DERMA_KNOWLEDGE_BASE in services.py.
# Stored in DB so admins can update ingredient lists without a code deploy.
#
# IMPORTANT: skin_type choices are strictly limited to what the CNN can detect:
#   dry, oily, normal — ONLY. Do NOT add combination or sensitive.
# ═══════════════════════════════════════════════════════════════════════════════

class DermaProfile(models.Model):
    """
    Dermatologically validated ingredient profiles.
    One row per (skin_type × age_group × gender) = 24 total rows.

    skin_type is limited to ML model outputs: dry, oily, normal.
    age and gender come from user manual input, not the ML model.
    """

    # Only the 3 skin types the CNN model can output
    SKIN_TYPE_CHOICES = (
        ('dry',    'Dry'),
        ('oily',   'Oily'),
        ('normal', 'Normal'),
    )

    AGE_GROUP_CHOICES = (
        ('teen',        'Teen (13–17)'),
        ('young_adult', 'Young Adult (18–29)'),
        ('adult',       'Adult (30–49)'),
        ('mature',      'Mature (50+)'),
    )

    # Gender is user-entered. 'other' resolves to 'female' in the service layer.
    # The DB only stores 'male' / 'female' profiles.
    GENDER_CHOICES = (
        ('male',   'Male'),
        ('female', 'Female'),
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    skin_type = models.CharField(max_length=10, choices=SKIN_TYPE_CHOICES, db_index=True)
    age_group = models.CharField(max_length=20, choices=AGE_GROUP_CHOICES, db_index=True)
    gender    = models.CharField(max_length=10, choices=GENDER_CHOICES,    db_index=True)

    # ── Ingredients (comma-separated) ─────────────────────────────────────────
    primary_ingredients = models.TextField(
        help_text=(
            'Comma-separated. JAAD/AAD validated primary ingredients. '
            'e.g. salicylic acid, niacinamide, benzoyl peroxide'
        )
    )
    secondary_ingredients = models.TextField(
        blank=True,
        help_text='Comma-separated. Beneficial but lower priority than primary.'
    )
    avoid_ingredients = models.TextField(
        blank=True,
        help_text=(
            'Comma-separated. Products containing these get a score penalty. '
            'e.g. mineral oil for oily skin, alcohol denat for dry skin'
        )
    )

    # ── Key concerns ──────────────────────────────────────────────────────────
    key_concerns = models.TextField(
        default='general',
        help_text=(
            'Comma-separated. Concern keys from Product.CONCERN_CHOICES. '
            'e.g. acne, aging, hydration, brightening'
        )
    )

    # ── Research citation ─────────────────────────────────────────────────────
    source = models.CharField(
        max_length=255,
        blank=True,
        help_text='Citation e.g. "AAD 20s Skincare + JAAD Delphi Consensus [2,3]"'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Derma Profile'
        verbose_name_plural = 'Derma Profiles'
        unique_together     = [['skin_type', 'age_group', 'gender']]
        ordering            = ['skin_type', 'age_group', 'gender']
        indexes = [
            models.Index(fields=['skin_type', 'age_group', 'gender']),
        ]

    def __str__(self):
        return f"{self.get_skin_type_display()} / {self.get_age_group_display()} / {self.get_gender_display()}"

    # ── Helper methods ────────────────────────────────────────────────────────

    def primary_list(self):
        return [i.strip() for i in self.primary_ingredients.split(',') if i.strip()]

    def secondary_list(self):
        return [i.strip() for i in self.secondary_ingredients.split(',') if i.strip()]

    def avoid_list(self):
        return [i.strip() for i in self.avoid_ingredients.split(',') if i.strip()]

    def concerns_list(self):
        return [i.strip() for i in self.key_concerns.split(',') if i.strip()]


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class Recommendation(models.Model):
    """
    Individual product recommendation linked to a SkinAnalysis.

    Scoring breakdown is stored per recommendation for transparency.
    The reasoning field cites the dermatological source used.
    """

    analysis = models.ForeignKey(
        SkinAnalysis,
        on_delete=models.CASCADE,
        related_name='recommendations',
        help_text='Source skin analysis (contains ML skin_type + user age/gender)'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='recommendations',
    )

    # ── Score components ──────────────────────────────────────────────────────
    match_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Overall weighted match score (0.0 – 1.0)'
    )
    rank = models.PositiveIntegerField(
        default=0,
        help_text='Rank among recommendations for this analysis (1 = best)'
    )
    skin_type_match = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    age_match = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Score based on user-entered age vs product age range'
    )
    gender_match = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Score based on user-entered gender vs product gender'
    )

    # ── Reasoning ─────────────────────────────────────────────────────────────
    reasoning = models.TextField(
        blank=True,
        help_text='Human-readable explanation with dermatological source citations'
    )

    # ── User feedback ─────────────────────────────────────────────────────────
    FEEDBACK_CHOICES = (
        ('none',      'No Feedback'),
        ('liked',     'Liked'),
        ('disliked',  'Disliked'),
        ('purchased', 'Purchased'),
    )
    user_feedback    = models.CharField(max_length=20, choices=FEEDBACK_CHOICES,
                                        default='none', db_index=True)
    feedback_comment = models.TextField(blank=True)

    # ── Tracking ──────────────────────────────────────────────────────────────
    is_clicked = models.BooleanField(default=False)
    clicked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Recommendation'
        verbose_name_plural = 'Recommendations'
        ordering            = ['analysis', 'rank']
        unique_together     = [['analysis', 'product']]
        indexes = [
            models.Index(fields=['analysis', 'rank']),
            models.Index(fields=['product']),
            models.Index(fields=['user_feedback']),
            models.Index(fields=['match_score']),
        ]

    def __str__(self):
        return f"{self.product.name} → Analysis #{self.analysis.id} (Rank {self.rank})"

    @property
    def match_percentage(self):
        return round(self.match_score * 100, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION SESSION
# ═══════════════════════════════════════════════════════════════════════════════

class RecommendationSession(models.Model):
    """
    One session per SkinAnalysis. Records what the engine used and how long it took.
    filters_applied stores: skin_type (ML), age (user), gender (user),
    detected_concern, age_group, derm_source.
    """

    analysis = models.OneToOneField(
        SkinAnalysis,
        on_delete=models.CASCADE,
        related_name='recommendation_session',
        primary_key=True
    )
    total_products_matched = models.PositiveIntegerField(default=0)
    algorithm_version      = models.CharField(
        max_length=50,
        default='v3.0-hybrid-derm-knowledge'
    )
    filters_applied   = models.JSONField(default=dict)
    processing_time_ms = models.PositiveIntegerField(default=0)
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Recommendation Session'
        verbose_name_plural = 'Recommendation Sessions'

    def __str__(self):
        return f"Session for Analysis #{self.analysis_id}"