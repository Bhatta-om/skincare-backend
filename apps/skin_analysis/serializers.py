# apps/skin_analysis/serializers.py

from rest_framework import serializers
from .models import SkinAnalysis, SkinFeature
from core.utils import validate_image_file


# ════════════════════════════════════════════════════════════
# ANALYSIS REQUEST
# ════════════════════════════════════════════════════════════

class SkinAnalysisRequestSerializer(serializers.ModelSerializer):
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
    features              = SkinFeatureSerializer(read_only=True)
    confidence_percentage = serializers.FloatField(read_only=True)
    user_email            = serializers.SerializerMethodField()

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
        return obj.user.email if obj.user else None


# ════════════════════════════════════════════════════════════
# ANALYSIS HISTORY
# ════════════════════════════════════════════════════════════

class SkinAnalysisHistorySerializer(serializers.ModelSerializer):
    """
    History list serializer.

    FIX: Added confidence_label and recommendations
    so MyAnalysis.jsx can display products correctly.

    confidence_label  → 'High' / 'Medium' / 'Low'
    recommendations   → list of matched products with reasoning
    """

    confidence_percentage = serializers.FloatField(read_only=True)
    confidence_label      = serializers.SerializerMethodField()
    recommendations       = serializers.SerializerMethodField()

    class Meta:
        model  = SkinAnalysis
        fields = [
            'id',
            'image',
            'skin_type',
            'confidence_score',
            'confidence_percentage',
            'confidence_label',       # ✅ NEW — High/Medium/Low
            'age',
            'gender',
            'status',
            'created_at',
            'recommendations',        # ✅ NEW — products list
        ]

    def get_confidence_label(self, obj):
        """Convert confidence score to High / Medium / Low label."""
        score = obj.confidence_score
        if not score:      return 'Medium'
        if score >= 0.80:  return 'High'
        if score >= 0.60:  return 'Medium'
        return 'Low'

    def get_recommendations(self, obj):
        """
        Return saved recommendations for this analysis.
        Each item has: product data, match_score, reasoning.
        """
        try:
            from apps.recommendations.models import Recommendation
            from apps.products.serializers import ProductListSerializer

            recs = (
                Recommendation.objects
                .filter(analysis=obj)
                .select_related('product')
                .order_by('rank')[:12]
            )

            result = []
            for rec in recs:
                try:
                    result.append({
                        'product':     ProductListSerializer(rec.product).data,
                        'match_score': rec.match_score,
                        'reasoning':   rec.reasoning or '',
                    })
                except Exception:
                    # Skip any individual product that fails
                    continue

            return result

        except Exception:
            return []