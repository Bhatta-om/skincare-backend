# apps/skin_analysis/views.py

import logging
import requests
import tempfile
import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import SkinAnalysis, SkinFeature
from .serializers import (
    SkinAnalysisRequestSerializer,
    SkinAnalysisResultSerializer,
    SkinAnalysisHistorySerializer,
)
from apps.recommendations.services import RecommendationService

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# ANALYZE SKIN
# ════════════════════════════════════════════════════════════

class AnalyzeSkinView(APIView):
    """
    POST /api/skin-analysis/analyze/
    Login chainaa — guest users pani analyze garna sakcha.

    Request (multipart/form-data):
    {
        "image": <file>,
        "age": 25,
        "gender": "female"
    }
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SkinAnalysisRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get user if logged in, else guest
        user = request.user if request.user.is_authenticated else None

        # Create analysis record with pending status
        analysis = SkinAnalysis.objects.create(
            user=user,
            image=serializer.validated_data['image'],
            age=serializer.validated_data['age'],
            gender=serializer.validated_data['gender'],
            status='processing'
        )

        try:
            # ── CNN Model Predict ──────────────────────────────────────────────
            skin_type, confidence = self._predict_skin_type(analysis.image)
            # ──────────────────────────────────────────────────────────────────

            # Update analysis with results
            analysis.skin_type        = skin_type
            analysis.confidence_score = confidence
            analysis.status           = 'completed'
            analysis.completed_at     = timezone.now()
            analysis.save(update_fields=[
                'skin_type', 'confidence_score', 'status', 'completed_at'
            ])

            # Save skin features
            SkinFeature.objects.create(
                analysis        = analysis,
                oiliness_score  = self._get_oiliness_score(skin_type),
                dryness_score   = self._get_dryness_score(skin_type),
                texture_density = 0.5,
                pore_visibility = 0.4,
                redness_score   = 0.2,
            )

            # Get recommendations
            recommendation_result = RecommendationService.get_recommendations(
                skin_type=skin_type,
                age=analysis.age,
                gender=analysis.gender,
                limit=12
            )

            # Save recommendations to DB
            RecommendationService.save_recommendations(
                analysis_id=analysis.id,
                recommendation_data=recommendation_result
            )

            # Format recommendations for response
            recommendations = []
            for item in recommendation_result['recommendations']:
                from apps.products.serializers import ProductListSerializer
                recommendations.append({
                    'product':     ProductListSerializer(item['product']).data,
                    'match_score': item['match_score'],
                    'reasoning':   item['reasoning'],
                })

            logger.info(
                "Skin analysis completed for analysis #%s — skin_type: %s, confidence: %.2f",
                analysis.id, skin_type, confidence
            )

            return Response({
                'success': True,
                'message': 'Skin analysis completed successfully!',
                'analysis': {
                    'id':                 analysis.id,
                    'skin_type':          analysis.skin_type,
                    'confidence':         analysis.confidence_score,
                    'confidence_percent': analysis.confidence_percentage,
                    'age':                analysis.age,
                    'gender':             analysis.gender,
                    'status':             analysis.status,
                    'created_at':         analysis.created_at,
                },
                'recommendations': {
                    'total':    len(recommendations),
                    'products': recommendations,
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # Mark analysis as failed
            analysis.status        = 'failed'
            analysis.error_message = str(e)
            analysis.save(update_fields=['status', 'error_message'])

            logger.error("Skin analysis failed for analysis #%s: %s", analysis.id, str(e))

            return Response({
                'success': False,
                'error':   'Skin analysis failed. Please try again with a clearer image.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ── CNN Model Integration ──────────────────────────────────────────────────
    def _predict_skin_type(self, image):
        """
        Download image from Cloudinary then predict skin type.
        Works both locally and on Render.
        """
        from ml_models.skin_model import predict_skin_type

        try:
            # Try local path first (development)
            image_path = image.path
            skin_type, confidence = predict_skin_type(image_path)
            return skin_type, confidence

        except NotImplementedError:
            pass

        except Exception as e:
            logger.warning("Local path failed, trying Cloudinary URL: %s", str(e))

        try:
            # Production — download from Cloudinary URL
            image_url = image.url
            logger.info("Downloading image from Cloudinary: %s", image_url)

            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            # Save to temp file
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix='.jpg'
            ) as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name

            try:
                skin_type, confidence = predict_skin_type(tmp_path)
                return skin_type, confidence
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            logger.error("CNN prediction failed: %s", str(e))
            raise Exception(f"Skin analysis failed: {str(e)}")
    # ──────────────────────────────────────────────────────────────────────────

    def _get_oiliness_score(self, skin_type):
        """Skin type anusar oiliness score."""
        return {
            'oily':   0.85,
            'normal': 0.35,
            'dry':    0.10,
        }.get(skin_type, 0.3)

    def _get_dryness_score(self, skin_type):
        """Skin type anusar dryness score."""
        return {
            'dry':    0.85,
            'normal': 0.30,
            'oily':   0.10,
        }.get(skin_type, 0.3)


# ════════════════════════════════════════════════════════════
# ANALYSIS DETAIL
# ════════════════════════════════════════════════════════════

class AnalysisDetailView(APIView):
    """
    GET /api/skin-analysis/<pk>/
    Get a specific analysis by ID.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, pk):
        analysis = get_object_or_404(SkinAnalysis, pk=pk)

        if analysis.user and request.user.is_authenticated:
            if analysis.user != request.user and not request.user.is_staff:
                return Response({
                    'success': False,
                    'error':   'You are not allowed to view this analysis.'
                }, status=status.HTTP_403_FORBIDDEN)

        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({
            'success':  True,
            'analysis': serializer.data
        })


# ════════════════════════════════════════════════════════════
# MY ANALYSIS HISTORY
# ════════════════════════════════════════════════════════════

class MyAnalysisHistoryView(APIView):
    """
    GET /api/skin-analysis/my-history/
    Returns all analyses for the logged-in user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses = SkinAnalysis.objects.filter(
            user=request.user
        ).order_by('-created_at')

        serializer = SkinAnalysisHistorySerializer(analyses, many=True)
        return Response({
            'success': True,
            'count':   analyses.count(),
            'results': serializer.data
        })


# ════════════════════════════════════════════════════════════
# LATEST ANALYSIS
# ════════════════════════════════════════════════════════════

class LatestAnalysisView(APIView):
    """
    GET /api/skin-analysis/latest/
    Returns the most recent completed analysis for the logged-in user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        analysis = SkinAnalysis.objects.filter(
            user=request.user,
            status='completed'
        ).order_by('-created_at').first()

        if not analysis:
            return Response({
                'success': False,
                'error':   'No completed analysis found.'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({
            'success':  True,
            'analysis': serializer.data
        })