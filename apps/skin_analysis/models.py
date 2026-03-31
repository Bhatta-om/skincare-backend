# apps/skin_analysis/models.py
# ─────────────────────────────────────────────────────────────────────────────
# ML model outputs (confirmed from terminal):
#   skin_type          → 'dry', 'oily', or 'normal'
#   confidence_score   → float (winning class probability)
#   dry_probability    → float (raw prob for dry class)   ← NEW
#   oily_probability   → float (raw prob for oily class)  ← NEW
#   normal_probability → float (raw prob for normal class) ← NEW
#
# age and gender → entered manually by user, NOT from ML.
# Image → file upload OR camera capture, handled identically by storage.
# SkinFeature (oiliness_score etc.) is NOT populated by your CNN — ignored.
# ─────────────────────────────────────────────────────────────────────────────

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from cloudinary_storage.storage import RawMediaCloudinaryStorage


class SkinAnalysis(models.Model):
    """
    One row per analysis request.

    CNN writes:  skin_type, confidence_score,
                 dry_probability, oily_probability, normal_probability
    User enters: age, gender
    User provides: image (file upload or camera)
    """

    SKIN_TYPE_CHOICES = (
        ('dry',    'Dry'),
        ('oily',   'Oily'),
        ('normal', 'Normal'),
    )

    GENDER_CHOICES = (
        ('male',   'Male'),
        ('female', 'Female'),
        ('other',  'Other'),
    )

    STATUS_CHOICES = (
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
    )

    # ── User relation ─────────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skin_analyses',
        help_text='Null for guest users'
    )

    # ── Image — file upload or camera capture ─────────────────────────────────
    image = models.ImageField(
        upload_to='skin_analysis/%Y/%m/',
        storage=RawMediaCloudinaryStorage(),
        help_text='Facial image — uploaded from device or captured via camera'
    )

    # ── User-entered inputs ───────────────────────────────────────────────────
    age = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text='Entered manually by the user'
    )
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        help_text='Selected manually by the user'
    )

    # ── CNN model outputs — primary ───────────────────────────────────────────
    skin_type = models.CharField(
        max_length=10,
        choices=SKIN_TYPE_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text='Winning class from CNN — dry, oily, or normal only'
    )
    confidence_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Probability of winning class (e.g. 0.7137 for 71.4%)'
    )

    # ── CNN model outputs — raw class probabilities ───────────────────────────
    # These are the 3 softmax outputs your CNN produces for every analysis.
    # From terminal: Dry=0.2855, Normal=0.7137, Oily=0.0007
    # Used by recommendation engine for concern detection.
    # Your skin_analysis/views.py must save these after the CNN runs.
    dry_probability = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='CNN raw probability for dry class (e.g. 0.2855)'
    )
    oily_probability = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='CNN raw probability for oily class (e.g. 0.0007)'
    )
    normal_probability = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='CNN raw probability for normal class (e.g. 0.7137)'
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    error_message = models.TextField(blank=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Skin Analysis'
        verbose_name_plural = 'Skin Analyses'
        ordering            = ['-created_at']
        indexes = [
            models.Index(fields=['skin_type']),
            models.Index(fields=['status']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        user_info = self.user.email if self.user else 'Guest'
        return f"Analysis #{self.id} — {user_info} — {self.skin_type or 'Pending'}"

    @property
    def confidence_percentage(self):
        return round(self.confidence_score * 100, 2)


class SkinFeature(models.Model):
    """
    NOTE: Your CNN does NOT write to this table.
    These fields are always 0.0 and are NOT used by the recommendation engine.
    Kept for potential future ML model upgrades only.
    """

    analysis = models.OneToOneField(
        SkinAnalysis,
        on_delete=models.CASCADE,
        related_name='features',
        primary_key=True
    )

    oiliness_score  = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    dryness_score   = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    texture_density = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    pore_visibility = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    redness_score   = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    class Meta:
        verbose_name        = 'Skin Feature'
        verbose_name_plural = 'Skin Features'

    def __str__(self):
        return f"Features of Analysis #{self.analysis_id}"