# apps/skin_analysis/views.py
# Updated: Face detection now handled inside skin_model.py
# using Haar Cascade (haarcascade_frontalface_alt.xml)
# OpenCV quality check removed — model handles validation

import logging
import tempfile
import os

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import SkinAnalysis, SkinFeature
from .serializers import (
    SkinAnalysisRequestSerializer,
    SkinAnalysisResultSerializer,
    SkinAnalysisHistorySerializer,
)
from apps.recommendations.services import RecommendationService

logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class AnalyzeSkinView(APIView):
    """
    POST /api/skin-analysis/analyze/

    Pipeline:
      Stage 1 — CNN + Haar Cascade  (face detection + skin classification)
      Stage 2 — Confidence check    (rejects confidence < 0.40)
    """

    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    def _confidence_label(self, score):
        if score >= 0.80: return 'High'
        if score >= 0.60: return 'Medium'
        return 'Low'

    def _delete_image_from_cloudinary(self, analysis):
        try:
            import cloudinary.uploader
            if analysis.image:
                public_id = str(analysis.image).rsplit('.', 1)[0]
                result    = cloudinary.uploader.destroy(public_id)
                if result.get('result') == 'ok':
                    logger.info('Image deleted from Cloudinary — analysis #%s', analysis.id)
                    analysis.image = None
                    analysis.save(update_fields=['image'])
                else:
                    logger.warning('Cloudinary delete returned: %s — analysis #%s', result, analysis.id)
        except Exception as e:
            logger.warning('Could not delete image from Cloudinary — analysis #%s: %s', analysis.id, e)

    def post(self, request):

        # ── Size guard ────────────────────────────────────
        image_file_raw = request.FILES.get('image')
        if image_file_raw and image_file_raw.size > MAX_IMAGE_SIZE_BYTES:
            return Response({
                'success':    False,
                'error':      'Image is too large. Maximum allowed size is 10 MB.',
                'error_code': 'IMAGE_TOO_LARGE',
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = SkinAnalysisRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error':   serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        user       = request.user if request.user.is_authenticated else None
        image_file = serializer.validated_data['image']
        suffix     = '.' + image_file.name.split('.')[-1] if '.' in image_file.name else '.jpg'

        logger.info(
            'Analysis request — %s',
            f'user: {user.email} (id={user.id})' if user else 'Guest user'
        )

        # ── Save to temp file ─────────────────────────────
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in image_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            logger.info('Temp file saved: %s', tmp_path)
        except Exception as e:
            logger.error('Failed to save temp file: %s', e)
            return Response({
                'success': False,
                'error':   'Failed to process image. Please try again.',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # ── Stage 1: CNN + Haar Cascade ───────────────
            # Face detection + skin classification in one step
            # Errors raised as exceptions with error codes
            logger.info('Stage 1: Running CNN + face detection...')
            try:
                from ml_models.skin_model import predict_skin_type
                result = predict_skin_type(tmp_path)

                if len(result) == 5:
                    skin_type, confidence, dry_prob, oily_prob, normal_prob = result
                elif len(result) == 2:
                    skin_type, confidence = result
                    dry_prob = oily_prob = normal_prob = 0.0
                else:
                    raise ValueError(f'predict_skin_type() returned {len(result)} values. Expected 5.')

            except Exception as e:
                error_msg = str(e)

                # ── Handle face detection errors ──────────
                if 'NO_FACE_DETECTED' in error_msg:
                    return Response({
                        'success':    False,
                        'error':      'No face detected in the image. Please upload a clear, front-facing photo of your face in good lighting.',
                        'error_code': 'NO_FACE_DETECTED',
                    }, status=status.HTTP_400_BAD_REQUEST)

                elif 'MULTIPLE_FACES' in error_msg:
                    return Response({
                        'success':    False,
                        'error':      'Multiple faces detected. Please upload a photo with only your face.',
                        'error_code': 'MULTIPLE_FACES',
                    }, status=status.HTTP_400_BAD_REQUEST)

                elif 'INVALID_IMAGE' in error_msg:
                    return Response({
                        'success':    False,
                        'error':      'Could not read the image. Please upload a valid JPG, PNG, or WEBP photo.',
                        'error_code': 'INVALID_IMAGE',
                    }, status=status.HTTP_400_BAD_REQUEST)

                elif 'ImportError' in error_msg or 'MODEL_UNAVAILABLE' in error_msg:
                    return Response({
                        'success':    False,
                        'error':      'Skin classification model is unavailable. Please try again later.',
                        'error_code': 'MODEL_UNAVAILABLE',
                    }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

                # Unknown error
                raise

            logger.info(
                'Stage 1 passed — skin_type=%s | confidence=%.4f | dry=%.4f | oily=%.4f | normal=%.4f',
                skin_type, confidence, dry_prob, oily_prob, normal_prob,
            )

            # ── Stage 2: Confidence threshold ────────────
            if confidence < 0.40:
                logger.warning('Stage 2 failed — confidence=%.4f', confidence)
                return Response({
                    'success':    False,
                    'error':      'Could not analyze your skin clearly. Please use a well-lit, front-facing photo without filters or heavy makeup.',
                    'error_code': 'LOW_CONFIDENCE',
                }, status=status.HTTP_400_BAD_REQUEST)

            logger.info('Stage 2 passed')

            # ── Atomic save ───────────────────────────────
            with transaction.atomic():
                image_file.seek(0)
                analysis = SkinAnalysis.objects.create(
                    user               = user,
                    image              = image_file,
                    age                = serializer.validated_data['age'],
                    gender             = serializer.validated_data['gender'],
                    skin_type          = skin_type,
                    confidence_score   = confidence,
                    dry_probability    = dry_prob,
                    oily_probability   = oily_prob,
                    normal_probability = normal_prob,
                    status             = 'completed',
                    completed_at       = timezone.now(),
                )

                SkinFeature.objects.create(
                    analysis        = analysis,
                    oiliness_score  = {'oily': 0.85, 'normal': 0.35, 'dry': 0.10}.get(skin_type, 0.3),
                    dryness_score   = {'dry':  0.85, 'normal': 0.30, 'oily': 0.10}.get(skin_type, 0.3),
                    texture_density = 0.5,
                    pore_visibility = 0.4,
                    redness_score   = 0.2,
                )

                recommendation_result = RecommendationService.get_recommendations(
                    skin_type   = skin_type,
                    age         = analysis.age,
                    gender      = analysis.gender,
                    limit       = 12,
                    analysis_id = analysis.id,
                )
                RecommendationService.save_recommendations(
                    analysis_id         = analysis.id,
                    recommendation_data = recommendation_result,
                )

            # ── Build response ────────────────────────────
            from apps.products.serializers import ProductListSerializer
            recommendations = [
                {
                    'product':          ProductListSerializer(item['product']).data,
                    'match_score':      item['match_score'],
                    'ingredient_match': item.get('ingredient_match', 0.0),
                    'reasoning':        item['reasoning'],
                }
                for item in recommendation_result['recommendations']
            ]

            self._delete_image_from_cloudinary(analysis)

            logger.info(
                'Analysis complete — #%s | user=%s | skin=%s | confidence=%.2f | image=deleted',
                analysis.id, user.email if user else 'Guest', skin_type, confidence,
            )

            return Response({
                'success': True,
                'message': 'Skin analysis completed successfully!',
                'analysis': {
                    'id':               analysis.id,
                    'skin_type':        skin_type,
                    'confidence_label': self._confidence_label(confidence),
                    'age':              analysis.age,
                    'gender':           analysis.gender,
                    'status':           analysis.status,
                    'created_at':       analysis.created_at,
                    'detected_concern': recommendation_result.get('detected_concern'),
                },
                'recommendations': {
                    'total':    len(recommendations),
                    'products': recommendations,
                },
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error('Analysis failed — %s', e, exc_info=True)
            return Response({
                'success': False,
                'error':   'Skin analysis failed. Please try again with a clearer image.',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
                logger.info('Temp file deleted: %s', tmp_path)


class AnalysisDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    def get(self, request, pk):
        analysis = get_object_or_404(SkinAnalysis, pk=pk)
        if analysis.user is not None:
            if not request.user or not request.user.is_authenticated:
                return Response({'success': False, 'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
            if not request.user.is_staff and request.user != analysis.user:
                return Response({'success': False, 'error': 'You are not allowed to view this analysis.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({'success': True, 'analysis': serializer.data})


class MyAnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses   = SkinAnalysis.objects.filter(user=request.user).order_by('-created_at')
        serializer = SkinAnalysisHistorySerializer(analyses, many=True)
        return Response({'success': True, 'count': analyses.count(), 'results': serializer.data})


class LatestAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analysis = SkinAnalysis.objects.filter(user=request.user, status='completed').order_by('-created_at').first()
        if not analysis:
            return Response({'success': False, 'error': 'No completed analysis found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({'success': True, 'analysis': serializer.data})


class AdminSkinAnalysisView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count, Q

        analyses  = SkinAnalysis.objects.select_related('user').order_by('-created_at')
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

        distribution     = list(SkinAnalysis.objects.filter(status='completed').values('skin_type').annotate(count=Count('id')).order_by('-count'))
        status_breakdown = list(SkinAnalysis.objects.values('status').annotate(count=Count('id')).order_by('-count'))

        def confidence_label(score):
            if not score:     return '—'
            if score >= 0.80: return 'High'
            if score >= 0.60: return 'Medium'
            return 'Low'

        results = []
        for a in analyses[:100]:
            if a.user:
                full_name    = f'{a.user.first_name} {a.user.last_name}'.strip()
                user_display = full_name or a.user.email
                user_email   = a.user.email
            else:
                user_display = 'Guest'
                user_email   = '—'
            results.append({
                'id': a.id, 'user': user_email, 'user_name': user_display,
                'skin_type': a.skin_type or '—', 'status': a.status,
                'confidence_label': confidence_label(a.confidence_score),
                'age': a.age, 'gender': a.gender,
                'created_at': a.created_at, 'completed_at': a.completed_at,
            })

        return Response({
            'success': True, 'total': analyses.count(),
            'distribution': distribution, 'status_breakdown': status_breakdown,
            'results': results,
        })