# apps/skin_analysis/serializers.py

from rest_framework import serializers
from .models import SkinAnalysis, SkinFeature
from core.utils import validate_image_file


# ════════════════════════════════════════════════════════════
# ANALYSIS REQUEST
# ════════════════════════════════════════════════════════════

class SkinAnalysisRequestSerializer(serializers.ModelSerializer):
    """
    POST /api/skin-analysis/analyze/
    Input validation — image, age, gender
    """

    class Meta:
        model  = SkinAnalysis
        fields = ['image', 'age', 'gender']

    def validate_image(self, value):
        validate_image_file(value)
        return value

    def validate_age(self, value):
        if value < 13:
            raise serializers.ValidationError("Age must be at least 13!")
        if value > 80:
            raise serializers.ValidationError("Age must be below 80!")
        return value

    def validate_gender(self, value):
        valid = ['male', 'female', 'other']
        if value.lower() not in valid:
            raise serializers.ValidationError(
                f"Gender must be one of: {', '.join(valid)}"
            )
        return value.lower()


# ════════════════════════════════════════════════════════════
# SKIN FEATURES
# ════════════════════════════════════════════════════════════

class SkinFeatureSerializer(serializers.ModelSerializer):
    """Detailed skin features from CNN analysis."""

    oiliness_percentage = serializers.SerializerMethodField()
    dryness_percentage  = serializers.SerializerMethodField()
    texture_percentage  = serializers.SerializerMethodField()

    class Meta:
        model  = SkinFeature
        fields = [
            'oiliness_score',
            'oiliness_percentage',
            'dryness_score',
            'dryness_percentage',
            'texture_density',
            'texture_percentage',
            'pore_visibility',
            'redness_score',
        ]

    def get_oiliness_percentage(self, obj):
        return round(obj.oiliness_score * 100, 2)

    def get_dryness_percentage(self, obj):
        return round(obj.dryness_score * 100, 2)

    def get_texture_percentage(self, obj):
        return round(obj.texture_density * 100, 2)


# ════════════════════════════════════════════════════════════
# ANALYSIS RESULT
# ════════════════════════════════════════════════════════════

class SkinAnalysisResultSerializer(serializers.ModelSerializer):
    """Full analysis result including features."""

    features            = SkinFeatureSerializer(read_only=True)
    confidence_percentage = serializers.FloatField(read_only=True)
    # ── UPDATED: user_email optional — guest ko lagi null aaucha ─────────────
    user_email = serializers.SerializerMethodField()
    # ─────────────────────────────────────────────────────────────────────────

    class Meta:
        model  = SkinAnalysis
        fields = [
            'id',
            'user_email',
            'image',
            'age',
            'gender',
            'skin_type',
            'confidence_score',
            'confidence_percentage',
            'features',
            'status',
            'error_message',
            'created_at',
            'completed_at',
        ]

    def get_user_email(self, obj):
        """Guest bhaye null return garcha."""
        return obj.user.email if obj.user else None


# ════════════════════════════════════════════════════════════
# ANALYSIS HISTORY
# ════════════════════════════════════════════════════════════

class SkinAnalysisHistorySerializer(serializers.ModelSerializer):
    """Short info for history list."""

    confidence_percentage = serializers.FloatField(read_only=True)

    class Meta:
        model  = SkinAnalysis
        fields = [
            'id',
            'image',
            'skin_type',
            'confidence_percentage',
            'age',
            'gender',
            'status',
            'created_at',
        ]