# apps/skin_analysis/models.py

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

class SkinAnalysis(models.Model):
    """
    Skin Analysis Results
    
    Workflow:
    1. User uploads image + age + gender
    2. CNN model analyzes
    3. Results stored here
    4. Recommendation engine uses this data
    """
    
    # ════════════════════════════════════════════════════════════
    # CHOICES
    # ════════════════════════════════════════════════════════════
    
    SKIN_TYPE_CHOICES = (
        ('normal', 'Normal'),
        ('dry', 'Dry'),
        ('oily', 'Oily'),
        ('combination', 'Combination'),
    )
    
    GENDER_CHOICES = (
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    )
    
    # ════════════════════════════════════════════════════════════
    # USER & INPUTS
    # ════════════════════════════════════════════════════════════
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skin_analyses',
        help_text='Optional — guest users pani analyze garna sakcha'
    )
    
    # Manual inputs from user
    image = models.ImageField(
        upload_to='skin_analysis/%Y/%m/',
        help_text='User uploaded facial image'
    )
    
    age = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES
    )
    
    # ════════════════════════════════════════════════════════════
    # AI MODEL OUTPUTS
    # ════════════════════════════════════════════════════════════
    
    skin_type = models.CharField(
        max_length=20,
        choices=SKIN_TYPE_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text='CNN model le detect gareko skin type'
    )
    
    confidence_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Model confidence (0.0 - 1.0)'
    )
    
    # ════════════════════════════════════════════════════════════
    # STATUS & METADATA
    # ════════════════════════════════════════════════════════════
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    error_message = models.TextField(
        blank=True,
        help_text='Analysis fail bhayo bhane error message'
    )
    
    # ════════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ════════════════════════════════════════════════════════════
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # ════════════════════════════════════════════════════════════
    # META
    # ════════════════════════════════════════════════════════════
    
    class Meta:
        verbose_name = 'Skin Analysis'
        verbose_name_plural = 'Skin Analyses'
        ordering = ['-created_at']
        
        indexes = [
            models.Index(fields=['skin_type']),
            models.Index(fields=['status']),
            models.Index(fields=['user', 'created_at']),
        ]
    
    def __str__(self):
        user_info = self.user.email if self.user else 'Guest'
        return f"Analysis #{self.id} - {user_info} - {self.skin_type or 'Pending'}"
    
    @property
    def confidence_percentage(self):
        """Confidence lai percentage ma"""
        return round(self.confidence_score * 100, 2)


class SkinFeature(models.Model):
    """
    Detailed skin features
    CNN model le detect gareko detailed attributes
    
    Future enhancement:
    - Oiliness detection
    - Dryness detection
    - Texture analysis
    - Pore size detection
    """
    
    analysis = models.OneToOneField(
        SkinAnalysis,
        on_delete=models.CASCADE,
        related_name='features',
        primary_key=True
    )
    
    # Feature scores (0.0 - 1.0)
    oiliness_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='How oily the skin is'
    )
    
    dryness_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='How dry the skin is'
    )
    
    texture_density = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Skin texture roughness'
    )
    
    # Additional attributes (future)
    pore_visibility = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        blank=True
    )
    
    redness_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        blank=True
    )
    
    class Meta:
        verbose_name = 'Skin Feature'
        verbose_name_plural = 'Skin Features'
    
    def __str__(self):
        return f"Features of Analysis #{self.analysis.id}"