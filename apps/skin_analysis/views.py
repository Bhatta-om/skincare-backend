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


class AnalyzeSkinView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    def _validate_face(self, image_path):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            img = cv2.imread(image_path)
            if img is None:
                return False, "INVALID_IMAGE", (
                    "Could not read the image. "
                    "Please upload a valid JPG, PNG, or WEBP photo."
                )

            img_rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)

            try:
                import urllib.request
                model_path = os.path.join(os.path.dirname(__file__), "blaze_face_short_range.tflite")
                if not os.path.exists(model_path):
                    url = (
                        "https://storage.googleapis.com/mediapipe-models/"
                        "face_detector/blaze_face_short_range/float16/1/"
                        "blaze_face_short_range.tflite"
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
                legacy_mp = mp.solutions.face_detection
                with legacy_mp.FaceDetection(min_detection_confidence=0.6) as detector:
                    result = detector.process(img_rgb)
                    count  = len(result.detections) if result.detections else 0

            if count == 0:
                return False, "NO_FACE_DETECTED", (
                    "No face detected in the image. "
                    "Please upload a clear, front-facing photo of your face."
                )
            if count > 1:
                return False, "MULTIPLE_FACES", (
                    "Multiple faces detected. "
                    "Please upload a photo with only your face."
                )

            return True, None, None

        except Exception as e:
            logger.warning("Stage 1 (MediaPipe) fail-open: %s", str(e))
            return True, None, None

    # ─────────────────────────────────────────────────────────
    # STAGE 2 — OpenCV Image Quality Check
    # FIXED: Relaxed thresholds to stop wrongly rejecting
    #        good quality webcam and Google images.
    #
    # OLD thresholds (too strict):
    #   sharpness < 50  → rejected good webcam photos
    #   brightness < 40 → rejected slightly dim but usable photos
    #
    # NEW thresholds (industry standard):
    #   sharpness < 15  → only genuinely blurry images rejected
    #   brightness < 20 → only genuinely dark images rejected
    #   brightness > 235 → overexposed/flash images rejected (NEW)
    #
    # Real world Laplacian variance scores:
    #   Genuinely blurry  →  2 - 12
    #   Webcam photo      → 20 - 50   ← was wrongly rejected before
    #   Google image      → 30 - 80   ← was wrongly rejected before
    #   Normal selfie     → 45 - 120  ← was wrongly rejected before
    #   Sharp photo       → 80 - 300
    # ─────────────────────────────────────────────────────────
    def _validate_quality(self, image_path):
        try:
            import cv2

            img = cv2.imread(image_path)
            if img is None:
                return True, None, None

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # ── Sharpness Check ──────────────────────────────
            # Laplacian variance — measures edge clarity
            # Threshold lowered from 50 → 15
            # Only rejects genuinely motion-blurred or out-of-focus photos
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            if sharpness < 15:
                return False, "IMAGE_TOO_BLURRY", (
                    "Image is too blurry. "
                    "Please take a sharper, clearer photo in good lighting."
                )

            # ── Brightness Check ─────────────────────────────
            # Mean pixel value (0=black, 255=white)
            # Threshold lowered from 40 → 20
            # Only rejects photos taken in very dark rooms
            brightness = gray.mean()
            if brightness < 20:
                return False, "IMAGE_TOO_DARK", (
                    "Image is too dark. "
                    "Please take the photo in a well-lit area."
                )

            # ── Overexposed Check (NEW) ───────────────────────
            # Catches photos taken in direct sunlight or with flash
            # These appear washed out and CNN cannot analyze them well
            if brightness > 235:
                return False, "IMAGE_TOO_BRIGHT", (
                    "Image is overexposed or too bright. "
                    "Please avoid direct sunlight or camera flash."
                )

            return True, None, None

        except Exception as e:
            logger.warning("Stage 2 (OpenCV quality) fail-open: %s", str(e))
            return True, None, None

    def _confidence_label(self, score):
        if score >= 0.80: return "High"
        if score >= 0.60: return "Medium"
        return "Low"

    def _delete_image_from_cloudinary(self, analysis):
        try:
            import cloudinary.uploader
            if analysis.image:
                image_name = str(analysis.image)
                public_id  = image_name.rsplit(".", 1)[0]
                result     = cloudinary.uploader.destroy(public_id)
                if result.get("result") == "ok":
                    logger.info("Image deleted from Cloudinary — analysis #%s", analysis.id)
                    analysis.image = None
                    analysis.save(update_fields=["image"])
                else:
                    logger.warning("Cloudinary delete returned: %s — analysis #%s", result, analysis.id)
        except Exception as e:
            logger.warning("Could not delete image from Cloudinary — analysis #%s: %s", analysis.id, str(e))

    def _get_oiliness_score(self, skin_type):
        return {"oily": 0.85, "normal": 0.35, "dry": 0.10}.get(skin_type, 0.3)

    def _get_dryness_score(self, skin_type):
        return {"dry": 0.85, "normal": 0.30, "oily": 0.10}.get(skin_type, 0.3)

    def post(self, request):
        serializer = SkinAnalysisRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        user       = request.user if request.user.is_authenticated else None
        image_file = serializer.validated_data["image"]
        suffix     = ("." + image_file.name.split(".")[-1] if "." in image_file.name else ".jpg")

        if user:
            logger.info("Analysis request — user: %s (%s)", user.get_full_name() or user.email, user.id)
        else:
            logger.info("Analysis request — Guest user")

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in image_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            logger.info("Temp file saved: %s", tmp_path)
        except Exception as e:
            logger.error("Failed to save temp file: %s", str(e))
            return Response({"success": False, "error": "Failed to process image. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # STAGE 1 — MediaPipe: Face Detection
            is_valid, error_code, error_msg = self._validate_face(tmp_path)
            if not is_valid:
                logger.warning("Stage 1 failed — %s", error_code)
                return Response({"success": False, "error": error_msg, "error_code": error_code}, status=status.HTTP_400_BAD_REQUEST)

            # STAGE 2 — OpenCV: Image Quality Check (fixed thresholds)
            is_valid, error_code, error_msg = self._validate_quality(tmp_path)
            if not is_valid:
                logger.warning("Stage 2 failed — %s", error_code)
                return Response({"success": False, "error": error_msg, "error_code": error_code}, status=status.HTTP_400_BAD_REQUEST)

            # STAGE 3 — CNN Model: Skin Classification
            from ml_models.skin_model import predict_skin_type
            skin_type, confidence = predict_skin_type(tmp_path)

            # STAGE 4 — Confidence Threshold
            if confidence < 0.55:
                logger.warning("Stage 4 failed — confidence=%.2f", confidence)
                return Response({
                    "success": False,
                    "error": (
                        "Could not analyze your skin clearly. "
                        "Please use a well-lit, front-facing photo "
                        "without filters or heavy makeup."
                    ),
                    "error_code": "LOW_CONFIDENCE",
                }, status=status.HTTP_400_BAD_REQUEST)

            # ALL STAGES PASSED — Save to DB
            image_file.seek(0)
            analysis = SkinAnalysis.objects.create(
                user             = user,
                image            = image_file,
                age              = serializer.validated_data["age"],
                gender           = serializer.validated_data["gender"],
                skin_type        = skin_type,
                confidence_score = confidence,
                status           = "completed",
                completed_at     = timezone.now(),
            )

            SkinFeature.objects.create(
                analysis        = analysis,
                oiliness_score  = self._get_oiliness_score(skin_type),
                dryness_score   = self._get_dryness_score(skin_type),
                texture_density = 0.5,
                pore_visibility = 0.4,
                redness_score   = 0.2,
            )

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

            recommendations = []
            for item in recommendation_result["recommendations"]:
                from apps.products.serializers import ProductListSerializer
                recommendations.append({
                    "product":     ProductListSerializer(item["product"]).data,
                    "match_score": item["match_score"],
                    "reasoning":   item["reasoning"],
                })

            self._delete_image_from_cloudinary(analysis)

            logger.info(
                "Analysis complete — #%s | user: %s | skin: %s | confidence: %.2f | image: deleted",
                analysis.id, user.email if user else "Guest", skin_type, confidence
            )

            return Response({
                "success": True,
                "message": "Skin analysis completed successfully!",
                "analysis": {
                    "id":               analysis.id,
                    "skin_type":        skin_type,
                    "confidence_label": self._confidence_label(confidence),
                    "age":              analysis.age,
                    "gender":           analysis.gender,
                    "status":           analysis.status,
                    "created_at":       analysis.created_at,
                },
                "recommendations": {
                    "total":    len(recommendations),
                    "products": recommendations,
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Analysis failed — %s", str(e))
            return Response({"success": False, "error": "Skin analysis failed. Please try again with a clearer image."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


class AnalysisDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    def get(self, request, pk):
        analysis = get_object_or_404(SkinAnalysis, pk=pk)
        if analysis.user and request.user.is_authenticated:
            if analysis.user != request.user and not request.user.is_staff:
                return Response({"success": False, "error": "You are not allowed to view this analysis."}, status=status.HTTP_403_FORBIDDEN)
        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({"success": True, "analysis": serializer.data})


class MyAnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses   = SkinAnalysis.objects.filter(user=request.user).order_by("-created_at")
        serializer = SkinAnalysisHistorySerializer(analyses, many=True)
        return Response({"success": True, "count": analyses.count(), "results": serializer.data})


class LatestAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analysis = SkinAnalysis.objects.filter(user=request.user, status="completed").order_by("-created_at").first()
        if not analysis:
            return Response({"success": False, "error": "No completed analysis found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({"success": True, "analysis": serializer.data})


class AdminSkinAnalysisView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count, Q
        analyses = SkinAnalysis.objects.select_related("user").order_by("-created_at")

        skin_type = request.query_params.get("skin_type", "").strip()
        status_f  = request.query_params.get("status",    "").strip()
        search    = request.query_params.get("search",    "").strip()

        if skin_type: analyses = analyses.filter(skin_type=skin_type)
        if status_f:  analyses = analyses.filter(status=status_f)
        if search:
            analyses = analyses.filter(
                Q(user__email__icontains=search)      |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search)
            )

        total        = analyses.count()
        distribution = list(SkinAnalysis.objects.filter(status="completed").values("skin_type").annotate(count=Count("id")).order_by("-count"))
        status_breakdown = list(SkinAnalysis.objects.values("status").annotate(count=Count("id")).order_by("-count"))

        def confidence_label(score):
            if not score:     return "—"
            if score >= 0.80: return "High"
            if score >= 0.60: return "Medium"
            return "Low"

        results = []
        for a in analyses[:100]:
            if a.user:
                full_name    = f"{a.user.first_name} {a.user.last_name}".strip()
                user_display = full_name if full_name else a.user.email
                user_email   = a.user.email
            else:
                user_display = "Guest"
                user_email   = "—"
            results.append({
                "id": a.id, "user": user_email, "user_name": user_display,
                "skin_type": a.skin_type or "—", "status": a.status,
                "confidence_label": confidence_label(a.confidence_score),
                "age": a.age, "gender": a.gender,
                "created_at": a.created_at, "completed_at": a.completed_at,
            })

        return Response({
            "success": True, "total": total,
            "distribution": distribution, "status_breakdown": status_breakdown,
            "results": results,
        })