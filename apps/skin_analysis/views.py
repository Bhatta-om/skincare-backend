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

            img = cv2.imread(image_path)
            if img is None:
                return False, "INVALID_IMAGE", (
                    "Could not read the image. "
                    "Please upload a valid JPG, PNG, or WEBP photo."
                )

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w    = img_rgb.shape[:2]

            # ── Method 1: MediaPipe Tasks API ──────────────
            face_count = None
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision as mp_vision
                import urllib.request

                model_path = os.path.join(
                    os.path.dirname(__file__),
                    "blaze_face_short_range.tflite"
                )
                if not os.path.exists(model_path):
                    url = (
                        "https://storage.googleapis.com/mediapipe-models/"
                        "face_detector/blaze_face_short_range/float16/1/"
                        "blaze_face_short_range.tflite"
                    )
                    logger.info("Downloading MediaPipe model...")
                    urllib.request.urlretrieve(url, model_path)

                mp_image = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=img_rgb
                )
                base_options = mp_python.BaseOptions(
                    model_asset_path=model_path
                )
                options = mp_vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=0.6
                )
                with mp_vision.FaceDetector.create_from_options(options) as detector:
                    result     = detector.detect(mp_image)
                    face_count = len(result.detections)
                    logger.info(
                        "MediaPipe Tasks detected %d face(s)", face_count
                    )

            except Exception as e1:
                logger.warning("MediaPipe Tasks API failed: %s", str(e1))

                # ── Method 2: MediaPipe Legacy API ─────────
                try:
                    import mediapipe as mp
                    legacy_mp = mp.solutions.face_detection
                    with legacy_mp.FaceDetection(
                        min_detection_confidence=0.6
                    ) as detector:
                        result     = detector.process(img_rgb)
                        face_count = (
                            len(result.detections)
                            if result.detections else 0
                        )
                        logger.info(
                            "MediaPipe Legacy detected %d face(s)", face_count
                        )
                except Exception as e2:
                    logger.warning(
                        "MediaPipe Legacy API failed: %s", str(e2)
                    )

                    # ── Method 3: OpenCV Haar Cascade ───────
                    # Always works — bundled with OpenCV
                    try:
                        cascade_path = (
                            cv2.data.haarcascades +
                            'haarcascade_frontalface_default.xml'
                        )
                        face_cascade = cv2.CascadeClassifier(cascade_path)
                        gray         = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        faces        = face_cascade.detectMultiScale(
                            gray,
                            scaleFactor  = 1.1,
                            minNeighbors = 5,
                            minSize      = (80, 80),
                            flags        = cv2.CASCADE_SCALE_IMAGE
                        )
                        face_count = len(faces) if len(faces) > 0 else 0
                        logger.info(
                            "OpenCV Haar Cascade detected %d face(s)",
                            face_count
                        )
                    except Exception as e3:
                        logger.error(
                            "ALL face detection methods failed: %s", str(e3)
                        )
                        # Hard fail — never fail-open
                        return False, "FACE_DETECTION_ERROR", (
                            "Face detection service is temporarily unavailable. "
                            "Please try again in a moment."
                        )

            # ── Validate face count ────────────────────────
            if face_count is None:
                return False, "FACE_DETECTION_ERROR", (
                    "Could not verify face in image. "
                    "Please try again with a clearer photo."
                )

            if face_count == 0:
                logger.warning(
                    "No face found in image — rejecting upload"
                )
                return False, "NO_FACE_DETECTED", (
                    "No face detected in the image. "
                    "Please upload a clear, front-facing photo of your face "
                    "in good lighting without heavy filters."
                )

            if face_count > 1:
                logger.warning(
                    "%d faces found in image — rejecting", face_count
                )
                return False, "MULTIPLE_FACES", (
                    "Multiple faces detected. "
                    "Please upload a photo with only your face."
                )

            logger.info("Face validation passed — exactly 1 face detected")
            return True, None, None

        except Exception as e:
            logger.error(
                "Critical error in face validation: %s", str(e)
            )
            # Hard fail — never accept unknown images
            return False, "FACE_DETECTION_ERROR", (
                "Image validation failed. "
                "Please upload a clear front-facing photo and try again."
            )

    # ─────────────────────────────────────────────────────────
    # STAGE 2 — OpenCV Image Quality Check
    #
    # Thresholds (industry standard):
    #   sharpness < 15  → genuinely blurry images
    #   brightness < 20 → genuinely dark images
    #   brightness > 235 → overexposed/flash images
    # ─────────────────────────────────────────────────────────
    def _validate_quality(self, image_path):
        try:
            import cv2

            img = cv2.imread(image_path)
            if img is None:
                return True, None, None

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # ── Sharpness Check ──────────────────────────────
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            if sharpness < 15:
                return False, "IMAGE_TOO_BLURRY", (
                    "Image is too blurry. "
                    "Please take a sharper, clearer photo in good lighting."
                )

            # ── Brightness Check ─────────────────────────────
            brightness = gray.mean()
            if brightness < 20:
                return False, "IMAGE_TOO_DARK", (
                    "Image is too dark. "
                    "Please take the photo in a well-lit area."
                )

            # ── Overexposed Check ────────────────────────────
            if brightness > 235:
                return False, "IMAGE_TOO_BRIGHT", (
                    "Image is overexposed or too bright. "
                    "Please avoid direct sunlight or camera flash."
                )

            return True, None, None

        except Exception as e:
            logger.warning(
                "Stage 2 (OpenCV quality) fail-open: %s", str(e)
            )
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
                    logger.info(
                        "Image deleted from Cloudinary — analysis #%s",
                        analysis.id
                    )
                    analysis.image = None
                    analysis.save(update_fields=["image"])
                else:
                    logger.warning(
                        "Cloudinary delete returned: %s — analysis #%s",
                        result, analysis.id
                    )
        except Exception as e:
            logger.warning(
                "Could not delete image from Cloudinary"
                " — analysis #%s: %s",
                analysis.id, str(e)
            )

    def _get_oiliness_score(self, skin_type):
        return {
            "oily":   0.85,
            "normal": 0.35,
            "dry":    0.10,
        }.get(skin_type, 0.3)

    def _get_dryness_score(self, skin_type):
        return {
            "dry":    0.85,
            "normal": 0.30,
            "oily":   0.10,
        }.get(skin_type, 0.3)

    def post(self, request):
        serializer = SkinAnalysisRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "error": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        user       = request.user if request.user.is_authenticated else None
        image_file = serializer.validated_data["image"]
        suffix     = (
            "." + image_file.name.split(".")[-1]
            if "." in image_file.name else ".jpg"
        )

        if user:
            logger.info(
                "Analysis request — user: %s (%s)",
                user.get_full_name() or user.email, user.id
            )
        else:
            logger.info("Analysis request — Guest user")

        # ── Save temp file ─────────────────────────────────
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix
            ) as tmp:
                for chunk in image_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            logger.info("Temp file saved: %s", tmp_path)
        except Exception as e:
            logger.error("Failed to save temp file: %s", str(e))
            return Response(
                {
                    "success": False,
                    "error": "Failed to process image. Please try again.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            # ── STAGE 1: MediaPipe / OpenCV Face Detection ──
            logger.info("Stage 1: Running face detection...")
            is_valid, error_code, error_msg = self._validate_face(tmp_path)
            if not is_valid:
                logger.warning("Stage 1 failed — %s", error_code)
                return Response(
                    {
                        "success":    False,
                        "error":      error_msg,
                        "error_code": error_code,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logger.info("Stage 1 passed")

            # ── STAGE 2: OpenCV Image Quality Check ────────
            logger.info("Stage 2: Running quality check...")
            is_valid, error_code, error_msg = self._validate_quality(
                tmp_path
            )
            if not is_valid:
                logger.warning("Stage 2 failed — %s", error_code)
                return Response(
                    {
                        "success":    False,
                        "error":      error_msg,
                        "error_code": error_code,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logger.info("Stage 2 passed")

            # ── STAGE 3: ONNX CNN Skin Classification ───────
            logger.info("Stage 3: Running skin classification...")
            from ml_models.skin_model import predict_skin_type
            skin_type, confidence = predict_skin_type(tmp_path)
            logger.info(
                "Stage 3 passed — skin_type: %s | confidence: %.2f",
                skin_type, confidence
            )

            # ── STAGE 4: Confidence Threshold Check ─────────
            logger.info(
                "Stage 4: Checking confidence threshold (%.2f)...",
                confidence
            )
            if confidence < 0.55:
                logger.warning(
                    "Stage 4 failed — low confidence: %.2f", confidence
                )
                return Response(
                    {
                        "success": False,
                        "error": (
                            "Could not analyze your skin clearly. "
                            "Please use a well-lit, front-facing photo "
                            "without filters or heavy makeup."
                        ),
                        "error_code": "LOW_CONFIDENCE",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logger.info("Stage 4 passed")

            # ── ALL STAGES PASSED: Save to DB ───────────────
            logger.info("All stages passed — saving analysis to DB...")
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

            # ── Get Recommendations ──────────────────────────
            recommendation_result = RecommendationService.get_recommendations(
                skin_type = skin_type,
                age       = analysis.age,
                gender    = analysis.gender,
                limit     = 12,
            )
            RecommendationService.save_recommendations(
                analysis_id         = analysis.id,
                recommendation_data = recommendation_result,
            )

            recommendations = []
            for item in recommendation_result["recommendations"]:
                from apps.products.serializers import ProductListSerializer
                recommendations.append({
                    "product":     ProductListSerializer(
                        item["product"]
                    ).data,
                    "match_score": item["match_score"],
                    "reasoning":   item["reasoning"],
                })

            # ── Delete image from Cloudinary ─────────────────
            self._delete_image_from_cloudinary(analysis)

            logger.info(
                "Analysis complete — #%s | user: %s | skin: %s"
                " | confidence: %.2f | image: deleted",
                analysis.id,
                user.email if user else "Guest",
                skin_type,
                confidence,
            )

            return Response(
                {
                    "success": True,
                    "message": "Skin analysis completed successfully!",
                    "analysis": {
                        "id":               analysis.id,
                        "skin_type":        skin_type,
                        "confidence_label": self._confidence_label(
                            confidence
                        ),
                        "age":              analysis.age,
                        "gender":           analysis.gender,
                        "status":           analysis.status,
                        "created_at":       analysis.created_at,
                    },
                    "recommendations": {
                        "total":    len(recommendations),
                        "products": recommendations,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error("Analysis failed — %s", str(e))
            return Response(
                {
                    "success": False,
                    "error": (
                        "Skin analysis failed. "
                        "Please try again with a clearer image."
                    ),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
                logger.info("Temp file deleted: %s", tmp_path)


# ════════════════════════════════════════════════════════════
# ANALYSIS DETAIL VIEW
# ════════════════════════════════════════════════════════════

class AnalysisDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    def get(self, request, pk):
        analysis = get_object_or_404(SkinAnalysis, pk=pk)
        if analysis.user and request.user.is_authenticated:
            if (
                analysis.user != request.user
                and not request.user.is_staff
            ):
                return Response(
                    {
                        "success": False,
                        "error": (
                            "You are not allowed to view this analysis."
                        ),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({"success": True, "analysis": serializer.data})


# ════════════════════════════════════════════════════════════
# MY ANALYSIS HISTORY
# ════════════════════════════════════════════════════════════

class MyAnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses = SkinAnalysis.objects.filter(
            user=request.user
        ).order_by("-created_at")
        serializer = SkinAnalysisHistorySerializer(analyses, many=True)
        return Response(
            {
                "success": True,
                "count":   analyses.count(),
                "results": serializer.data,
            }
        )


# ════════════════════════════════════════════════════════════
# LATEST ANALYSIS
# ════════════════════════════════════════════════════════════

class LatestAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analysis = (
            SkinAnalysis.objects
            .filter(user=request.user, status="completed")
            .order_by("-created_at")
            .first()
        )
        if not analysis:
            return Response(
                {
                    "success": False,
                    "error":   "No completed analysis found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({"success": True, "analysis": serializer.data})


# ════════════════════════════════════════════════════════════
# ADMIN SKIN ANALYSIS VIEW
# ════════════════════════════════════════════════════════════

class AdminSkinAnalysisView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count, Q

        analyses = SkinAnalysis.objects.select_related(
            "user"
        ).order_by("-created_at")

        skin_type = request.query_params.get("skin_type", "").strip()
        status_f  = request.query_params.get("status",    "").strip()
        search    = request.query_params.get("search",    "").strip()

        if skin_type:
            analyses = analyses.filter(skin_type=skin_type)
        if status_f:
            analyses = analyses.filter(status=status_f)
        if search:
            analyses = analyses.filter(
                Q(user__email__icontains=search)      |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search)
            )

        total = analyses.count()

        distribution = list(
            SkinAnalysis.objects
            .filter(status="completed")
            .values("skin_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        status_breakdown = list(
            SkinAnalysis.objects
            .values("status")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        def confidence_label(score):
            if not score:     return "—"
            if score >= 0.80: return "High"
            if score >= 0.60: return "Medium"
            return "Low"

        results = []
        for a in analyses[:100]:
            if a.user:
                full_name    = (
                    f"{a.user.first_name} {a.user.last_name}".strip()
                )
                user_display = full_name if full_name else a.user.email
                user_email   = a.user.email
            else:
                user_display = "Guest"
                user_email   = "—"

            results.append({
                "id":               a.id,
                "user":             user_email,
                "user_name":        user_display,
                "skin_type":        a.skin_type or "—",
                "status":           a.status,
                "confidence_label": confidence_label(a.confidence_score),
                "age":              a.age,
                "gender":           a.gender,
                "created_at":       a.created_at,
                "completed_at":     a.completed_at,
            })

        return Response(
            {
                "success":          True,
                "total":            total,
                "distribution":     distribution,
                "status_breakdown": status_breakdown,
                "results":          results,
            }
        )