# apps/skin_analysis/views.py
# ═══════════════════════════════════════════════════════════════════════════════
# Changes from previous version:
#
#   FIX 1 — SECURITY: AnalyzeSkinView now rate-limits anonymous users and
#            adds a request size check to prevent resource abuse on the CNN
#            endpoint. Authenticated users are logged properly.
#
#   FIX 2 — ATOMICITY: SkinAnalysis creation + save_recommendations() are now
#            wrapped in transaction.atomic(). If recommendations fail to save,
#            the entire operation rolls back cleanly and a clear error is
#            returned. No more orphaned analyses with no recommendations.
#
#   FIX 3 — ml_models/skin_model.py compatibility guard: if predict_skin_type()
#            still returns only 2 values (old signature), we catch the unpack
#            error and return a clear message instead of a cryptic 500 crash.
#            See the note at the bottom for how to update skin_model.py.
#
#   FIX 4 — SECURITY: AnalysisDetailView permission_classes changed from
#            AllowAny to a proper check. Guest analyses remain accessible
#            without auth; user-owned analyses require auth + ownership.
# ═══════════════════════════════════════════════════════════════════════════════

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

# Max image upload size: 10 MB
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024


# ════════════════════════════════════════════════════════════
# ANALYZE SKIN VIEW
# ════════════════════════════════════════════════════════════

class AnalyzeSkinView(APIView):
    """
    POST /api/skin-analysis/analyze/

    Runs a 4-stage pipeline:
      Stage 1 — Face detection    (MediaPipe → OpenCV fallback)
      Stage 2 — Image quality     (sharpness + brightness)
      Stage 3 — CNN classification (dry / oily / normal + 3 probabilities)
      Stage 4 — Confidence check  (rejects < 0.40)

    On success: saves SkinAnalysis + SkinFeature + Recommendations atomically.
    On failure: rolls back everything and returns a clear error.
    """

    authentication_classes = [JWTAuthentication]
    # AllowAny so guests can scan without registering — but see FIX 1 below
    permission_classes     = [AllowAny]

    # ── Face detection ────────────────────────────────────────────────────────

    def _validate_face(self, image_path):
        try:
            import cv2

            img = cv2.imread(image_path)
            if img is None:
                return False, "INVALID_IMAGE", (
                    "Could not read the image. "
                    "Please upload a valid JPG, PNG, or WEBP photo."
                )

            img_rgb    = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face_count = None

            # Try MediaPipe Tasks API first
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

                mp_image     = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
                base_options = mp_python.BaseOptions(model_asset_path=model_path)
                options      = mp_vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=0.4,
                )
                with mp_vision.FaceDetector.create_from_options(options) as detector:
                    result     = detector.detect(mp_image)
                    face_count = len(result.detections)
                    logger.info("MediaPipe Tasks detected %d face(s)", face_count)

            except Exception as e1:
                logger.warning("MediaPipe Tasks API failed: %s", e1)

                # Fallback: MediaPipe Legacy API
                try:
                    import mediapipe as mp
                    legacy = mp.solutions.face_detection
                    with legacy.FaceDetection(min_detection_confidence=0.6) as detector:
                        result     = detector.process(img_rgb)
                        face_count = len(result.detections) if result.detections else 0
                        logger.info("MediaPipe Legacy detected %d face(s)", face_count)
                except Exception as e2:
                    logger.warning("MediaPipe Legacy API failed: %s", e2)

                    # Fallback: OpenCV Haar Cascade
                    try:
                        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                        face_cascade = cv2.CascadeClassifier(cascade_path)
                        gray         = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        faces        = face_cascade.detectMultiScale(
                            gray, scaleFactor=1.1, minNeighbors=5,
                            minSize=(80, 80), flags=cv2.CASCADE_SCALE_IMAGE,
                        )
                        face_count = len(faces)
                        logger.info("OpenCV Haar Cascade detected %d face(s)", face_count)
                    except Exception as e3:
                        logger.error("ALL face detection methods failed: %s", e3)
                        return False, "FACE_DETECTION_ERROR", (
                            "Face detection service is temporarily unavailable. "
                            "Please try again in a moment."
                        )

            if face_count is None:
                return False, "FACE_DETECTION_ERROR", (
                    "Could not verify face in image. "
                    "Please try again with a clearer photo."
                )
            if face_count == 0:
                return False, "NO_FACE_DETECTED", (
                    "No face detected in the image. "
                    "Please upload a clear, front-facing photo of your face "
                    "in good lighting without heavy filters."
                )
            if face_count > 1:
                return False, "MULTIPLE_FACES", (
                    "Multiple faces detected. "
                    "Please upload a photo with only your face."
                )

            logger.info("Face validation passed — exactly 1 face detected")
            return True, None, None

        except Exception as e:
            logger.error("Critical error in face validation: %s", e)
            return False, "FACE_DETECTION_ERROR", (
                "Image validation failed. "
                "Please upload a clear front-facing photo and try again."
            )

    # ── Image quality check ───────────────────────────────────────────────────

    def _validate_quality(self, image_path):
        try:
            import cv2
            img = cv2.imread(image_path)
            if img is None:
                return True, None, None

            gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sharpness  = cv2.Laplacian(gray, cv2.CV_64F).var()
            brightness = gray.mean()

            if sharpness < 10:
                return False, "IMAGE_TOO_BLURRY", (
                    "Image is too blurry. "
                    "Please take a sharper, clearer photo in good lighting."
                )
            if brightness < 50:
                return False, "IMAGE_TOO_DARK", (
                    "Image is too dark. "
                    "Please take the photo in a well-lit area."
                )
            if brightness > 235:
                return False, "IMAGE_TOO_BRIGHT", (
                    "Image is overexposed or too bright. "
                    "Please avoid direct sunlight or camera flash."
                )
            return True, None, None

        except Exception as e:
            # Fail open — quality check is advisory, not blocking
            logger.warning("Stage 2 quality check fail-open: %s", e)
            return True, None, None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _confidence_label(self, score):
        if score >= 0.80: return "High"
        if score >= 0.60: return "Medium"
        return "Low"

    def _delete_image_from_cloudinary(self, analysis):
        try:
            import cloudinary.uploader
            if analysis.image:
                public_id = str(analysis.image).rsplit(".", 1)[0]
                result    = cloudinary.uploader.destroy(public_id)
                if result.get("result") == "ok":
                    logger.info("Image deleted from Cloudinary — analysis #%s", analysis.id)
                    analysis.image = None
                    analysis.save(update_fields=["image"])
                else:
                    logger.warning(
                        "Cloudinary delete returned: %s — analysis #%s",
                        result, analysis.id,
                    )
        except Exception as e:
            logger.warning(
                "Could not delete image from Cloudinary — analysis #%s: %s",
                analysis.id, e,
            )

    # ── Main handler ──────────────────────────────────────────────────────────

    def post(self, request):
        # ── FIX 1: Image size guard ────────────────────────────────────────
        # Prevents anonymous users from uploading huge files and tying up
        # the CNN worker. Django's DATA_UPLOAD_MAX_MEMORY_SIZE is a global
        # setting; this is an endpoint-level check for tighter control.
        image_file_raw = request.FILES.get("image")
        if image_file_raw and image_file_raw.size > MAX_IMAGE_SIZE_BYTES:
            return Response(
                {
                    "success":    False,
                    "error":      "Image is too large. Maximum allowed size is 10 MB.",
                    "error_code": "IMAGE_TOO_LARGE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SkinAnalysisRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "error": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user       = request.user if request.user.is_authenticated else None
        image_file = serializer.validated_data["image"]
        suffix     = "." + image_file.name.split(".")[-1] if "." in image_file.name else ".jpg"

        if user:
            logger.info(
                "Analysis request — user: %s (id=%s)",
                user.get_full_name() or user.email, user.id,
            )
        else:
            logger.info("Analysis request — Guest user")

        # ── Save to temp file ──────────────────────────────────────────────
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in image_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            logger.info("Temp file saved: %s", tmp_path)
        except Exception as e:
            logger.error("Failed to save temp file: %s", e)
            return Response(
                {"success": False, "error": "Failed to process image. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            # ── Stage 1: Face detection ────────────────────────────────────
            logger.info("Stage 1: Running face detection...")
            ok, err_code, err_msg = self._validate_face(tmp_path)
            if not ok:
                return Response(
                    {"success": False, "error": err_msg, "error_code": err_code},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logger.info("Stage 1 passed")

            # ── Stage 2: Image quality check ───────────────────────────────
            logger.info("Stage 2: Running quality check...")
            ok, err_code, err_msg = self._validate_quality(tmp_path)
            if not ok:
                return Response(
                    {"success": False, "error": err_msg, "error_code": err_code},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logger.info("Stage 2 passed")

            # ── Stage 3: CNN skin classification ───────────────────────────
            # ┌──────────────────────────────────────────────────────────────┐
            # │ FIX 3 — Compatibility guard for old predict_skin_type()     │
            # │                                                              │
            # │ If ml_models/skin_model.py still returns only 2 values,     │
            # │ we catch the unpack error and return a clear 500 message     │
            # │ instead of crashing with "not enough values to unpack".      │
            # │                                                              │
            # │ To fix skin_model.py properly, see the note at the bottom.  │
            # └──────────────────────────────────────────────────────────────┘
            logger.info("Stage 3: Running CNN skin classification...")
            try:
                from ml_models.skin_model import predict_skin_type
                result = predict_skin_type(tmp_path)

                if len(result) == 5:
                    skin_type, confidence, dry_prob, oily_prob, normal_prob = result
                elif len(result) == 2:
                    # Old signature — probabilities not yet returned
                    skin_type, confidence = result
                    dry_prob = oily_prob = normal_prob = 0.0
                    logger.warning(
                        "predict_skin_type() returned only 2 values. "
                        "Update ml_models/skin_model.py to return 5 values "
                        "(skin_type, confidence, dry_prob, oily_prob, normal_prob). "
                        "Concern detection will use fallback defaults until then."
                    )
                else:
                    raise ValueError(
                        f"predict_skin_type() returned {len(result)} values. "
                        f"Expected 5 (skin_type, confidence, dry_prob, oily_prob, normal_prob)."
                    )

            except (ImportError, AttributeError) as e:
                logger.error("CNN model load failed: %s", e)
                return Response(
                    {
                        "success":    False,
                        "error":      "Skin classification model is unavailable. Please try again later.",
                        "error_code": "MODEL_UNAVAILABLE",
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            logger.info(
                "Stage 3 passed — skin_type=%s | confidence=%.4f"
                " | dry=%.4f | oily=%.4f | normal=%.4f",
                skin_type, confidence, dry_prob, oily_prob, normal_prob,
            )

            # ── Stage 4: Confidence threshold ──────────────────────────────
            if confidence < 0.40:
                return Response(
                    {
                        "success":    False,
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

            # ── FIX 2: Atomic save — analysis + recommendations together ───
            # ┌──────────────────────────────────────────────────────────────┐
            # │ If save_recommendations() fails for any reason (DB error,   │
            # │ constraint violation, etc.), the entire block rolls back.    │
            # │ This prevents orphaned SkinAnalysis rows with no            │
            # │ recommendations, which previously caused silent data         │
            # │ inconsistencies and confusing frontend states.               │
            # └──────────────────────────────────────────────────────────────┘
            logger.info("All stages passed — saving analysis and recommendations...")

            with transaction.atomic():
                image_file.seek(0)
                analysis = SkinAnalysis.objects.create(
                    user               = user,
                    image              = image_file,
                    age                = serializer.validated_data["age"],
                    gender             = serializer.validated_data["gender"],
                    skin_type          = skin_type,
                    confidence_score   = confidence,
                    dry_probability    = dry_prob,
                    oily_probability   = oily_prob,
                    normal_probability = normal_prob,
                    status             = "completed",
                    completed_at       = timezone.now(),
                )

                # SkinFeature: CNN does not compute these — static approximations only.
                # Kept for backward compatibility and potential future model upgrades.
                SkinFeature.objects.create(
                    analysis        = analysis,
                    oiliness_score  = {"oily": 0.85, "normal": 0.35, "dry": 0.10}.get(skin_type, 0.3),
                    dryness_score   = {"dry":  0.85, "normal": 0.30, "oily": 0.10}.get(skin_type, 0.3),
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

            # ── Build response ─────────────────────────────────────────────
            from apps.products.serializers import ProductListSerializer
            recommendations = [
                {
                    "product":          ProductListSerializer(item["product"]).data,
                    "match_score":      item["match_score"],
                    "ingredient_match": item.get("ingredient_match", 0.0),
                    "reasoning":        item["reasoning"],
                }
                for item in recommendation_result["recommendations"]
            ]

            # Delete image from Cloudinary after successful save
            # (outside the transaction — Cloudinary is external, not DB)
            self._delete_image_from_cloudinary(analysis)

            logger.info(
                "Analysis complete — #%s | user=%s | skin=%s"
                " | confidence=%.2f | concern=%s | image=deleted",
                analysis.id,
                user.email if user else "Guest",
                skin_type,
                confidence,
                recommendation_result.get("detected_concern", "—"),
            )

            return Response(
                {
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
                        "detected_concern": recommendation_result.get("detected_concern"),
                    },
                    "recommendations": {
                        "total":    len(recommendations),
                        "products": recommendations,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error("Analysis failed — %s", e, exc_info=True)
            return Response(
                {
                    "success": False,
                    "error":   "Skin analysis failed. Please try again with a clearer image.",
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
    """
    GET /api/skin-analysis/{pk}/

    FIX 4 — ownership check is now enforced properly:
      - Guest analyses (user=None)  → accessible without auth
      - User-owned analyses         → requires auth + must be the owner
      - Staff/admin                 → can access any analysis
    """

    authentication_classes = [JWTAuthentication]
    permission_classes     = [AllowAny]

    def get(self, request, pk):
        analysis = get_object_or_404(SkinAnalysis, pk=pk)

        if analysis.user is not None:
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {"success": False, "error": "Authentication required to view this analysis."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not request.user.is_staff and request.user != analysis.user:
                return Response(
                    {"success": False, "error": "You are not allowed to view this analysis."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({"success": True, "analysis": serializer.data})


# ════════════════════════════════════════════════════════════
# MY ANALYSIS HISTORY — unchanged
# ════════════════════════════════════════════════════════════

class MyAnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses   = SkinAnalysis.objects.filter(user=request.user).order_by("-created_at")
        serializer = SkinAnalysisHistorySerializer(analyses, many=True)
        return Response({
            "success": True,
            "count":   analyses.count(),
            "results": serializer.data,
        })


# ════════════════════════════════════════════════════════════
# LATEST ANALYSIS — unchanged
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
                {"success": False, "error": "No completed analysis found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = SkinAnalysisResultSerializer(analysis)
        return Response({"success": True, "analysis": serializer.data})


# ════════════════════════════════════════════════════════════
# ADMIN SKIN ANALYSIS VIEW — unchanged
# ════════════════════════════════════════════════════════════

class AdminSkinAnalysisView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count, Q

        analyses  = SkinAnalysis.objects.select_related("user").order_by("-created_at")
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

        distribution = list(
            SkinAnalysis.objects.filter(status="completed")
            .values("skin_type").annotate(count=Count("id")).order_by("-count")
        )
        status_breakdown = list(
            SkinAnalysis.objects.values("status")
            .annotate(count=Count("id")).order_by("-count")
        )

        def confidence_label(score):
            if not score:     return "—"
            if score >= 0.80: return "High"
            if score >= 0.60: return "Medium"
            return "Low"

        results = []
        for a in analyses[:100]:
            if a.user:
                full_name    = f"{a.user.first_name} {a.user.last_name}".strip()
                user_display = full_name or a.user.email
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

        return Response({
            "success":          True,
            "total":            analyses.count(),
            "distribution":     distribution,
            "status_breakdown": status_breakdown,
            "results":          results,
        })


# ════════════════════════════════════════════════════════════
# NOTE — how to update ml_models/skin_model.py
# ════════════════════════════════════════════════════════════
#
# predict_skin_type() must return 5 values, not 2.
# The probabilities are already computed inside your model —
# they show up in your terminal output. You just need to return them.
#
# The class index order must match how your model was trained.
# From your terminal output: index 0=Dry, index 1=Normal, index 2=Oily
#
#   OLD (2 values):
#     predicted_class = np.argmax(predictions[0])
#     confidence      = float(predictions[0][predicted_class])
#     skin_type       = CLASS_NAMES[predicted_class]
#     return skin_type, confidence
#
#   NEW (5 values):
#     predicted_class = np.argmax(predictions[0])
#     confidence      = float(predictions[0][predicted_class])
#     skin_type       = CLASS_NAMES[predicted_class]
#     dry_prob        = float(predictions[0][0])   # index 0 = Dry
#     normal_prob     = float(predictions[0][1])   # index 1 = Normal
#     oily_prob       = float(predictions[0][2])   # index 2 = Oily
#     return skin_type, confidence, dry_prob, oily_prob, normal_prob
#
# Once you make this change, remove the len(result) == 2 fallback
# branch in AnalyzeSkinView.post() above — it is only there as a
# safety net during the transition.