# apps/recommendations/views.py
# ═══════════════════════════════════════════════════════════════════════════════
# Changes from original:
#
#   1. SECURITY — GetRecommendationsView now verifies the analysis belongs to
#      the requesting user (or user is admin). Prevents user A reading user B's
#      recommendations.
#
#   2. SECURITY — RecommendationFeedbackView and TrackProductClickView now use
#      IsAuthenticated instead of AllowAny. Feedback/clicks must come from a
#      logged-in user who owns the recommendation.
#
#   3. BUG FIX — ingredient_match score is now included in the serialized
#      response for GetRecommendationsView and QuickRecommendationsView.
#      Previously it was scored in services.py but never returned to frontend.
#
#   4. BUG FIX — QuickRecommendationsView now validates skin_type against
#      VALID_SKIN_TYPES before calling the service, returning a clear 400
#      instead of a 500.
#
#   5. ROBUSTNESS — age is validated as a positive integer (1–100) in
#      QuickRecommendationsView. Previously a string or negative value would
#      crash inside services.py with an unhelpful error.
#
#   6. CLARITY — GetRecommendationsView now returns ingredient_match per
#      recommendation in the cached path as well (was missing there).
# ═══════════════════════════════════════════════════════════════════════════════

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import UpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.skin_analysis.models import SkinAnalysis
from apps.products.serializers import ProductListSerializer
from .models import Recommendation
from .serializers import (
    RecommendationSerializer,
    RecommendationFeedbackSerializer,
)
from .services import RecommendationService, VALID_SKIN_TYPES


# ═══════════════════════════════════════════════════════════════════════════════
# GET RECOMMENDATIONS (analysis-based)
# ═══════════════════════════════════════════════════════════════════════════════

class GetRecommendationsView(APIView):
    """
    GET /api/recommendations/for-analysis/{analysis_id}/

    Returns recommendations for a completed SkinAnalysis.

    Auth rules:
      - Authenticated users can only fetch their own analysis results.
      - Staff/admin users can fetch any analysis.
      - Guest analyses (analysis.user is None) are accessible without auth,
        so guest flows on the frontend still work.

    Response:
    {
        "success": true,
        "analysis": {
            "id": 1,
            "skin_type": "oily",
            "age": 25,
            "gender": "female",
            "confidence": 87.5,
            "detected_concern": "acne",
            "derm_source": "AAD 20s + JAAD [2,3]"
        },
        "total_recommendations": 12,
        "cached": false,
        "recommendations": [
            {
                "id": ...,
                "product": {...},
                "match_score": 0.87,
                "match_percentage": 87.0,
                "rank": 1,
                "reasoning": "...",
                "skin_type_match": 1.0,
                "age_match": 0.91,
                "gender_match": 1.0,
                "ingredient_match": 0.75,   ← now included
                "user_feedback": "none",
                "is_clicked": false
            },
            ...
        ]
    }
    """

    # AllowAny here — ownership check is done manually inside get()
    # so that guest analyses (user=None) still work without a token.
    permission_classes = [AllowAny]

    def get(self, request, analysis_id):
        # ── Fetch the analysis ─────────────────────────────────────────────
        try:
            analysis = SkinAnalysis.objects.select_related('user').get(
                id=analysis_id,
                status='completed'
            )
        except SkinAnalysis.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Analysis not found or not completed.'
            }, status=status.HTTP_404_NOT_FOUND)

        # ── Ownership check ────────────────────────────────────────────────
        # Allow if:
        #   a) The analysis has no user (guest analysis)
        #   b) The requesting user is authenticated and owns the analysis
        #   c) The requesting user is staff/admin
        if analysis.user is not None:
            if not request.user or not request.user.is_authenticated:
                return Response({
                    'success': False,
                    'error': 'Authentication required to view this analysis.'
                }, status=status.HTTP_401_UNAUTHORIZED)
            if not request.user.is_staff and request.user != analysis.user:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to view this analysis.'
                }, status=status.HTTP_403_FORBIDDEN)

        # ── Return cached recommendations if they exist ────────────────────
        existing = Recommendation.objects.filter(
            analysis=analysis
        ).select_related('product').order_by('rank')

        if existing.exists():
            serializer = RecommendationSerializer(existing, many=True)
            session    = getattr(analysis, 'recommendation_session', None)
            filters    = session.filters_applied if session else {}

            return Response({
                'success': True,
                'analysis': {
                    'id':               analysis.id,
                    'skin_type':        analysis.skin_type,
                    'age':              analysis.age,
                    'gender':           analysis.gender,
                    'confidence':       analysis.confidence_percentage,
                    'detected_concern': filters.get('detected_concern', 'general'),
                    'derm_source':      filters.get('derm_source', ''),
                },
                'total_recommendations': existing.count(),
                'recommendations':       serializer.data,
                'cached': True,
            })

        # ── Generate fresh recommendations ────────────────────────────────
        try:
            result = RecommendationService.get_recommendations(
                skin_type   = analysis.skin_type,
                age         = analysis.age,
                gender      = analysis.gender,
                limit       = 12,
                analysis_id = analysis.id,
            )

            saved      = RecommendationService.save_recommendations(
                analysis_id         = analysis.id,
                recommendation_data = result,
            )
            serializer = RecommendationSerializer(saved, many=True)

            return Response({
                'success': True,
                'analysis': {
                    'id':               analysis.id,
                    'skin_type':        analysis.skin_type,
                    'age':              analysis.age,
                    'gender':           analysis.gender,
                    'confidence':       analysis.confidence_percentage,
                    'detected_concern': result.get('detected_concern', 'general'),
                    'derm_source':      result.get('derm_profile_source', ''),
                },
                'total_recommendations': len(saved),
                'processing_time_ms':    result['processing_time_ms'],
                'recommendations':       serializer.data,
                'cached': False,
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to generate recommendations: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ═══════════════════════════════════════════════════════════════════════════════
# QUICK RECOMMENDATIONS (no analysis ID)
# ═══════════════════════════════════════════════════════════════════════════════

class QuickRecommendationsView(APIView):
    """
    POST /api/recommendations/quick/

    No SkinAnalysis needed — concern is inferred from the derma profile.
    Useful for a quick product search widget without a face scan.

    Request:
    {
        "skin_type": "oily",   ← must be dry / oily / normal
        "age": 25,             ← integer 1–100
        "gender": "female"     ← male / female / other
    }

    Response:
    {
        "success": true,
        "total_recommendations": 12,
        "detected_concern": "acne",
        "derm_source": "AAD 20s + JAAD [2,3]",
        "recommendations": [
            {
                "product": {...},
                "match_score": 0.87,
                "ingredient_match": 0.75,   ← included
                "reasoning": "..."
            },
            ...
        ]
    }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        skin_type = request.data.get('skin_type', '').strip().lower()
        age       = request.data.get('age')
        gender    = request.data.get('gender', '').strip().lower()

        # ── Input validation ───────────────────────────────────────────────
        errors = {}

        if not skin_type:
            errors['skin_type'] = 'This field is required.'
        elif skin_type not in VALID_SKIN_TYPES:
            errors['skin_type'] = (
                f"Invalid value '{skin_type}'. "
                f"Must be one of: {', '.join(VALID_SKIN_TYPES)}."
            )

        if age is None:
            errors['age'] = 'This field is required.'
        else:
            try:
                age = int(age)
                if not (1 <= age <= 100):
                    errors['age'] = 'Age must be between 1 and 100.'
            except (ValueError, TypeError):
                errors['age'] = 'Age must be a valid integer.'

        if not gender:
            errors['gender'] = 'This field is required.'

        if errors:
            return Response({
                'success': False,
                'errors': errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── Generate recommendations ───────────────────────────────────────
        try:
            result = RecommendationService.get_recommendations(
                skin_type   = skin_type,
                age         = age,
                gender      = gender,
                limit       = 12,
                analysis_id = None,
            )

            recommendations = [
                {
                    'product':          ProductListSerializer(item['product']).data,
                    'match_score':      item['match_score'],
                    'ingredient_match': item.get('ingredient_match', 0.0),
                    'reasoning':        item['reasoning'],
                }
                for item in result['recommendations']
            ]

            return Response({
                'success':               True,
                'total_recommendations': len(recommendations),
                'detected_concern':      result.get('detected_concern', 'general'),
                'derm_source':           result.get('derm_profile_source', ''),
                'age_group':             result.get('age_group', ''),
                'recommendations':       recommendations,
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION FEEDBACK
# ═══════════════════════════════════════════════════════════════════════════════

class RecommendationFeedbackView(UpdateAPIView):
    """
    PATCH /api/recommendations/{id}/feedback/

    Requires authentication. Only the owner of the recommendation's analysis
    can submit feedback.

    {
        "user_feedback": "liked",
        "feedback_comment": "Great product!"
    }
    """

    queryset           = Recommendation.objects.all()
    serializer_class   = RecommendationFeedbackSerializer
    # FIX: was AllowAny — anyone could submit feedback on any recommendation
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # Ownership check — only the analysis owner can give feedback
        analysis_user = instance.analysis.user
        if analysis_user is not None and not request.user.is_staff:
            if request.user != analysis_user:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to update this recommendation.'
                }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response({
            'success':        True,
            'message':        'Feedback submitted successfully.',
            'recommendation': RecommendationSerializer(instance).data,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# TRACK PRODUCT CLICK
# ═══════════════════════════════════════════════════════════════════════════════

class TrackProductClickView(APIView):
    """
    POST /api/recommendations/{id}/track-click/

    Requires authentication. Only the analysis owner can track their clicks.
    Idempotent — clicking the same recommendation twice has no extra effect.
    """

    # FIX: was AllowAny — any anonymous request could pollute click analytics
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            rec = Recommendation.objects.select_related('analysis__user').get(pk=pk)
        except Recommendation.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Recommendation not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Ownership check
        analysis_user = rec.analysis.user
        if analysis_user is not None and not request.user.is_staff:
            if request.user != analysis_user:
                return Response({
                    'success': False,
                    'error': 'You do not have permission to track this click.'
                }, status=status.HTTP_403_FORBIDDEN)

        if not rec.is_clicked:
            from django.utils import timezone
            rec.is_clicked = True
            rec.clicked_at = timezone.now()
            rec.save(update_fields=['is_clicked', 'clicked_at'])

        return Response({'success': True, 'message': 'Click tracked.'})