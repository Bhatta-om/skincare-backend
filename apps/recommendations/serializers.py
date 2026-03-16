# apps/recommendations/serializers.py

from rest_framework import serializers
from .models import Recommendation, RecommendationSession
from apps.products.serializers import ProductListSerializer

# ════════════════════════════════════════════════════════════
# RECOMMENDATION SERIALIZER
# ════════════════════════════════════════════════════════════

class RecommendationSerializer(serializers.ModelSerializer):
    """
    Single recommendation
    
    Includes:
    - Product details
    - Match score & reasoning
    - Why recommended
    """
    
    product = ProductListSerializer(read_only=True)
    match_percentage = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Recommendation
        fields = [
            'id',
            'product',
            'match_score',
            'match_percentage',
            'rank',
            'reasoning',
            'skin_type_match',
            'age_match',
            'gender_match',
            'user_feedback',
            'is_clicked',
        ]


# ════════════════════════════════════════════════════════════
# RECOMMENDATION LIST SERIALIZER
# ════════════════════════════════════════════════════════════

class RecommendationListSerializer(serializers.Serializer):
    """
    Complete recommendation response
    
    Response:
    {
        "success": true,
        "analysis_summary": {...},
        "total_recommendations": 12,
        "recommendations": [...]
    }
    """
    
    analysis_id = serializers.IntegerField()
    skin_type = serializers.CharField()
    age = serializers.IntegerField()
    gender = serializers.CharField()
    total_recommendations = serializers.IntegerField()
    recommendations = RecommendationSerializer(many=True)


# ════════════════════════════════════════════════════════════
# FEEDBACK SERIALIZER
# ════════════════════════════════════════════════════════════

class RecommendationFeedbackSerializer(serializers.ModelSerializer):
    """
    User feedback on recommendation
    
    PATCH /api/recommendations/{id}/feedback/
    {
        "user_feedback": "liked",
        "feedback_comment": "Perfect product!"
    }
    """
    
    class Meta:
        model = Recommendation
        fields = ['user_feedback', 'feedback_comment']
    
    def validate_user_feedback(self, value):
        """Validate feedback choice"""
        valid_choices = ['liked', 'disliked', 'purchased']
        if value not in valid_choices:
            raise serializers.ValidationError(
                f"Invalid feedback. Choose from: {', '.join(valid_choices)}"
            )
        return value


# ════════════════════════════════════════════════════════════
# SESSION SERIALIZER
# ════════════════════════════════════════════════════════════

class RecommendationSessionSerializer(serializers.ModelSerializer):
    """Recommendation session metadata"""
    
    class Meta:
        model = RecommendationSession
        fields = [
            'analysis',
            'total_products_matched',
            'algorithm_version',
            'filters_applied',
            'processing_time_ms',
            'created_at',
        ]