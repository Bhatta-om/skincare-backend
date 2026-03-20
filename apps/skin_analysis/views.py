# apps/skin_analysis/views.py

import logging
import tempfile
import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
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
    Guest users can also analyze — no login required.
    Logged-in users are detected via JWT token automatically.

    Request (multipart/form-data):
    {
        "image"  : <file>,
        "age"    : 25,
        "gender" : "female"
    }

    Pipeline:
        Stage 1 → MediaPipe  — face detection
        Stage 2 → OpenCV     — image quality check
        Stage 3 → CNN model  — skin classification
        Stage 4 → Confidence — threshold check

    FIX 1: JWTAuthentication added so logged-in users are
           properly detected instead of showing as Guest.
    FIX 2: Validation happens BEFORE saving to DB/Cloudinary
           so rejected images are never stored.
    """

    # ✅ JWTAuthentication reads token if present
    # AllowAny means guests can still use it without token
    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    # ─────────────────────────────────────────────────────────
    # STAGE 1 — MediaPipe Face Detection
    # ─────────────────────────────────────────────────────────
    def _validate_face(self, image_path):
        """
        Detect human faces using MediaPipe FaceDetector.
        Fail-open: if MediaPipe crashes → allow through.

        Returns:
            (is_valid: bool, error_code: str|None, error_msg: str|None)
        """
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            img = cv2.imread(image_path)
            if img is None:
                return False, 'INVALID_IMAGE', (
                    'Could not read the image. '
                    'Please upload a valid JPG, PNG, or WEBP photo.'
                )

            img_rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=img_rgb
            )

            try:
                import urllib.request
                model_path = os.path.join(
                    os.path.dirname(__file__),
                    'blaze_face_short_range.tflite'
                )
                if not os.path.exists(model_path):
                    url = (
                        'https://storage.googleapis.com/mediapipe-models/'
                        'face_detector/blaze_face_short_range/float16/1/'
                        'blaze_face_short_range.tflite'
                    )
                    urllib.request.urlretrieve(url, model_path)

                base_options = mp_python.BaseOptions(model_asset_path=model_path)
                options      = mp_vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=0.6
                )
                with mp_vision.FaceDetector.create_from_options(options) as detector:
                    detection_result = detector.detect(mp_image)
                    count = len(detection_result.detections)

            except Exception:
                # Fallback to legacy API
                legacy_mp = mp.solutions.face_detection
                with legacy_mp.FaceDetection(min_detection_confidence=0.6) as detector:
                    result = detector.process(img_rgb)
                    count  = len(result.detections) if result.detections else 0

            if count == 0:
                return False, 'NO_FACE_DETECTED', (
                    'No face detected in the image. '
                    'Please upload a clear, front-facing photo of your face.'
                )
            if count > 1:
                return False, 'MULTIPLE_FACES', (
                    'Multiple faces detected. '
                    'Please upload a photo with only your face.'
                )

            return True, None, None

        except Exception as e:
            logger.warning("Stage 1 (MediaPipe) fail-open: %s", str(e))
            return True, None, None

    # ─────────────────────────────────────────────────────────
    # STAGE 2 — OpenCV Image Quality Check
    # ─────────────────────────────────────────────────────────
    def _validate_quality(self, image_path):
        """
        Check image sharpness and brightness.
        Fail-open: if OpenCV crashes → allow through.

        Returns:
            (is_valid: bool, error_code: str|None, error_msg: str|None)
        """
        try:
            import cv2

            img = cv2.imread(image_path)
            if img is None:
                return True, None, None

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Sharpness check
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            if sharpness < 50:
                return False, 'IMAGE_TOO_BLURRY', (
                    'Image is too blurry. '
                    'Please take a sharper, clearer photo in good lighting.'
                )

            # Brightness check
            brightness = gray.mean()
            if brightness < 40:
                return False, 'IMAGE_TOO_DARK', (
                    'Image is too dark. '
                    'Please take the photo in a well-lit area.'
                )

            return True, None, None

        except Exception as e:
            logger.warning("Stage 2 (OpenCV quality) fail-open: %s", str(e))
            return True, None, None

    # ─────────────────────────────────────────────────────────
    # CONFIDENCE LABEL HELPER
    # Returns High/Medium/Low instead of raw percentage
    # ─────────────────────────────────────────────────────────
    def _confidence_label(self, score):
        if score >= 0.80: return 'High'
        if score >= 0.60: return 'Medium'
        return 'Low'

    # ─────────────────────────────────────────────────────────
    # SCORE HELPERS
    # ─────────────────────────────────────────────────────────
    def _get_oiliness_score(self, skin_type):
        return { 'oily': 0.85, 'normal': 0.35, 'dry': 0.10 }.get(skin_type, 0.3)

    def _get_dryness_score(self, skin_type):
        return { 'dry': 0.85, 'normal': 0.30, 'oily': 0.10 }.get(skin_type, 0.3)

    # ─────────────────────────────────────────────────────────
    # MAIN HANDLER
    # ─────────────────────────────────────────────────────────
    def post(self, request):
        serializer = SkinAnalysisRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error':   serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Correctly detects logged-in user via JWT token
        # Returns None for guests (no token sent)
        user       = request.user if request.user.is_authenticated else None
        image_file = serializer.validated_data['image']
        suffix     = (
            '.' + image_file.name.split('.')[-1]
            if '.' in image_file.name else '.jpg'
        )

        if user:
            logger.info(
                "Analysis request — user: %s (%s)",
                user.get_full_name() or user.email, user.id
            )
        else:
            logger.info("Analysis request — Guest user")

        # ── Save to temp file ─────────────────────────────────
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in image_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            logger.info("Temp file saved: %s", tmp_path)
        except Exception as e:
            logger.error("Failed to save temp file: %s", str(e))
            return Response({
                'success': False,
                'error':   'Failed to process image. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # ══════════════════════════════════════════════════
            # STAGE 1 — MediaPipe: Face Detection
            # Validate BEFORE saving to DB/Cloudinary
            # ══════════════════════════════════════════════════
            is_valid, error_code, error_msg = self._validate_face(tmp_path)
            if not is_valid:
                logger.warning("Stage 1 failed — %s", error_code)
                return Response({
                    'success':    False,
                    'error':      error_msg,
                    'error_code': error_code,
                }, status=status.HTTP_400_BAD_REQUEST)

            # ══════════════════════════════════════════════════
            # STAGE 2 — OpenCV: Image Quality Check
            # ══════════════════════════════════════════════════
            is_valid, error_code, error_msg = self._validate_quality(tmp_path)
            if not is_valid:
                logger.warning("Stage 2 failed — %s", error_code)
                return Response({
                    'success':    False,
                    'error':      error_msg,
                    'error_code': error_code,
                }, status=status.HTTP_400_BAD_REQUEST)

            # ══════════════════════════════════════════════════
            # STAGE 3 — CNN Model: Skin Classification
            # ══════════════════════════════════════════════════
            from ml_models.skin_model import predict_skin_type
            skin_type, confidence = predict_skin_type(tmp_path)

            # ══════════════════════════════════════════════════
            # STAGE 4 — Confidence Threshold
            # ══════════════════════════════════════════════════
            if confidence < 0.55:
                logger.warning("Stage 4 failed — confidence=%.2f", confidence)
                return Response({
                    'success':    False,
                    'error':      (
                        'Could not analyze your skin clearly. '
                        'Please use a well-lit, front-facing photo '
                        'without filters or heavy makeup.'
                    ),
                    'error_code': 'LOW_CONFIDENCE',
                }, status=status.HTTP_400_BAD_REQUEST)

            # ══════════════════════════════════════════════════
            # ALL STAGES PASSED
            # NOW save to DB and Cloudinary — no wasted storage
            # ══════════════════════════════════════════════════
            image_file.seek(0)
            analysis = SkinAnalysis.objects.create(
                user             = user,
                image            = image_file,
                age              = serializer.validated_data['age'],
                gender           = serializer.validated_data['gender'],
                skin_type        = skin_type,
                confidence_score = confidence,
                status           = 'completed',
                completed_at     = timezone.now(),
            )

            # Save skin features
            SkinFeature.objects.create(
                analysis        = analysis,
                oiliness_score  = self._get_oiliness_score(skin_type),
                dryness_score   = self._get_dryness_score(skin_type),
                texture_density = 0.5,
                pore_visibility = 0.4,
                redness_score   = 0.2,
            )

            # Get & save recommendations
            recommendation_result = RecommendationService.get_recommendations(
                skin_type = skin_type,
                age       = analysis.age,
                gender    = analysis.gender,
                limit     = 12
            )
            RecommendationService.save_recommendations(
                analysis_id         = analysis.id,
                recommendation_data = recommendation_result
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
                "Analysis complete — #%s | user: %s | skin: %s | confidence: %.2f",
                analysis.id,
                user.email if user else 'Guest',
                skin_type,
                confidence
            )

            return Response({
                'success': True,
                'message': 'Skin analysis completed successfully!',
                'analysis': {
                    'id':               analysis.id,
                    'skin_type':        analysis.skin_type,
                    'confidence_label': self._confidence_label(confidence),
                    'age':              analysis.age,
                    'gender':           analysis.gender,
                    'status':           analysis.status,
                    'created_at':       analysis.created_at,
                },
                'recommendations': {
                    'total':    len(recommendations),
                    'products': recommendations,
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Analysis failed — %s", str(e))
            return Response({
                'success': False,
                'error':   'Skin analysis failed. Please try again with a clearer image.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        finally:
            # Always clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


# ════════════════════════════════════════════════════════════
# ANALYSIS DETAIL
# ════════════════════════════════════════════════════════════

class AnalysisDetailView(APIView):
    """GET /api/skin-analysis/<pk>/"""

    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    def get(self, request, pk):
        analysis = get_object_or_404(SkinAnalysis, pk=pk)

        if analysis.user and request.user.is_authenticated:
            if analysis.user != request.user and not request.user.is_staff:
                return Response({
                    'success': False,
                    'error':   'You are not allowed to view this analysis.'
                }, status=status.HTTP_403_FORBIDDEN)

        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({ 'success': True, 'analysis': serializer.data })


# ════════════════════════════════════════════════════════════
# MY ANALYSIS HISTORY
# ════════════════════════════════════════════════════════════

class MyAnalysisHistoryView(APIView):
    """GET /api/skin-analysis/my-history/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses   = SkinAnalysis.objects.filter(
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
    """GET /api/skin-analysis/latest/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        analysis = SkinAnalysis.objects.filter(
            user   = request.user,
            status = 'completed'
        ).order_by('-created_at').first()

        if not analysis:
            return Response({
                'success': False,
                'error':   'No completed analysis found.'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({ 'success': True, 'analysis': serializer.data })


# ════════════════════════════════════════════════════════════
# ADMIN — ALL ANALYSES
# ════════════════════════════════════════════════════════════

class AdminSkinAnalysisView(APIView):
    """
    GET /api/admin/skin-analysis/
    Admin only.

    Query params:
        skin_type : oily | dry | normal
        status    : completed | processing | failed
        search    : email or name
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count, Q

        analyses = SkinAnalysis.objects.select_related('user').order_by('-created_at')

        # ── Filters ───────────────────────────────────────────
        skin_type = request.query_params.get('skin_type', '').strip()
        status_f  = request.query_params.get('status',    '').strip()
        search    = request.query_params.get('search',    '').strip()

        if skin_type: analyses = analyses.filter(skin_type=skin_type)
        if status_f:  analyses = analyses.filter(status=status_f)
        if search:
            analyses = analyses.filter(
                Q(user__email__icontains=search)      |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search)
            )

        total = analyses.count()

        # ── Skin type distribution ────────────────────────────
        distribution = list(
            SkinAnalysis.objects.filter(status='completed')
            .values('skin_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # ── Status breakdown ──────────────────────────────────
        status_breakdown = list(
            SkinAnalysis.objects.values('status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # ── Confidence label helper ───────────────────────────
        def confidence_label(score):
            if not score:      return '—'
            if score >= 0.80:  return 'High'
            if score >= 0.60:  return 'Medium'
            return 'Low'

        # ── Results ───────────────────────────────────────────
        results = []
        for a in analyses[:100]:
            # Properly detect logged-in user vs guest
            if a.user:
                full_name    = f"{a.user.first_name} {a.user.last_name}".strip()
                user_display = full_name if full_name else a.user.email
                user_email   = a.user.email
            else:
                user_display = 'Guest'
                user_email   = '—'

            results.append({
                'id':               a.id,
                'user':             user_email,
                'user_name':        user_display,
                'skin_type':        a.skin_type or '—',
                'status':           a.status,
                'confidence_label': confidence_label(a.confidence_score),
                'age':              a.age,
                'gender':           a.gender,
                'created_at':       a.created_at,
                'completed_at':     a.completed_at,
            })

        return Response({
            'success':          True,
            'total':            total,
            'distribution':     distribution,
            'status_breakdown': status_breakdown,
            'results':          results,
        })