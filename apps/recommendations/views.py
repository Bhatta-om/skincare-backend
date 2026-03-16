# apps/recommendations/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView, UpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.skin_analysis.models import SkinAnalysis
from .models import Recommendation
from .serializers import (
    RecommendationSerializer,
    RecommendationFeedbackSerializer,
)
from .services import RecommendationService

# ════════════════════════════════════════════════════════════
# GET RECOMMENDATIONS
# ════════════════════════════════════════════════════════════

class GetRecommendationsView(APIView):
    """
    Get product recommendations for an analysis
    
    GET /api/recommendations/for-analysis/{analysis_id}/
    
    Response:
    {
        "success": true,
        "analysis": {...},
        "total_recommendations": 12,
        "recommendations": [...]
    }
    """
    
    permission_classes = [AllowAny]
    
    def get(self, request, analysis_id):
        # Get analysis
        try:
            analysis = SkinAnalysis.objects.select_related('user').get(
                id=analysis_id,
                status='completed'
            )
        except SkinAnalysis.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Analysis not found or not completed!'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if recommendations already exist
        existing = Recommendation.objects.filter(
            analysis=analysis
        ).select_related('product').order_by('rank')
        
        if existing.exists():
            # Return cached recommendations
            serializer = RecommendationSerializer(existing, many=True)
            
            return Response({
                'success': True,
                'analysis': {
                    'id': analysis.id,
                    'skin_type': analysis.skin_type,
                    'age': analysis.age,
                    'gender': analysis.gender,
                    'confidence': analysis.confidence_percentage,
                },
                'total_recommendations': existing.count(),
                'recommendations': serializer.data
            })
        
        # Generate new recommendations
        try:
            result = RecommendationService.get_recommendations(
                skin_type=analysis.skin_type,
                age=analysis.age,
                gender=analysis.gender,
                limit=12
            )
            
            # Save to database
            saved = RecommendationService.save_recommendations(
                analysis_id=analysis.id,
                recommendation_data=result
            )
            
            serializer = RecommendationSerializer(saved, many=True)
            
            return Response({
                'success': True,
                'analysis': {
                    'id': analysis.id,
                    'skin_type': analysis.skin_type,
                    'age': analysis.age,
                    'gender': analysis.gender,
                    'confidence': analysis.confidence_percentage,
                },
                'total_recommendations': len(saved),
                'processing_time_ms': result['processing_time_ms'],
                'recommendations': serializer.data
            })
        
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to generate recommendations: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ════════════════════════════════════════════════════════════
# QUICK RECOMMENDATIONS (Without Analysis ID)
# ════════════════════════════════════════════════════════════

class QuickRecommendationsView(APIView):
    """
    Get recommendations without saving analysis
    
    POST /api/recommendations/quick/
    
    Request:
    {
        "skin_type": "oily",
        "age": 25,
        "gender": "female"
    }
    
    Response:
    {
        "success": true,
        "recommendations": [...]
    }
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Validate input
        skin_type = request.data.get('skin_type')
        age = request.data.get('age')
        gender = request.data.get('gender')
        
        if not all([skin_type, age, gender]):
            return Response({
                'success': False,
                'error': 'skin_type, age, and gender are required!'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get recommendations
        try:
            result = RecommendationService.get_recommendations(
                skin_type=skin_type,
                age=int(age),
                gender=gender,
                limit=12
            )
            
            # Format response (without saving)
            recommendations = []
            for item in result['recommendations']:
                from apps.products.serializers import ProductListSerializer
                recommendations.append({
                    'product': ProductListSerializer(item['product']).data,
                    'match_score': item['match_score'],
                    'reasoning': item['reasoning'],
                })
            
            return Response({
                'success': True,
                'total_recommendations': len(recommendations),
                'recommendations': recommendations
            })
        
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ════════════════════════════════════════════════════════════
# RECOMMENDATION FEEDBACK
# ════════════════════════════════════════════════════════════

class RecommendationFeedbackView(UpdateAPIView):
    """
    Submit feedback on recommendation
    
    PATCH /api/recommendations/{id}/feedback/
    
    Request:
    {
        "user_feedback": "liked",
        "feedback_comment": "Great product!"
    }
    """
    
    queryset = Recommendation.objects.all()
    serializer_class = RecommendationFeedbackSerializer
    permission_classes = [AllowAny]
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response({
            'success': True,
            'message': 'Feedback submitted successfully!',
            'recommendation': RecommendationSerializer(instance).data
        })


# ════════════════════════════════════════════════════════════
# TRACK PRODUCT CLICK
# ════════════════════════════════════════════════════════════

class TrackProductClickView(APIView):
    """
    Track when user clicks recommended product
    
    POST /api/recommendations/{id}/track-click/
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request, pk):
        try:
            recommendation = Recommendation.objects.get(pk=pk)
            
            if not recommendation.is_clicked:
                from django.utils import timezone
                recommendation.is_clicked = True
                recommendation.clicked_at = timezone.now()
                recommendation.save(update_fields=['is_clicked', 'clicked_at'])
            
            return Response({
                'success': True,
                'message': 'Click tracked!'
            })
        
        except Recommendation.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Recommendation not found!'
            }, status=status.HTTP_404_NOT_FOUND)