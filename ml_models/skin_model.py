# ml_models/skin_model.py
# Uses ONNX runtime for inference + MediaPipe 0.10.x for face detection
# Falls back to Haar Cascade if MediaPipe fails
# Class order: 0=Dry, 1=Oily, 2=Normal

import numpy as np
import logging
import traceback
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
MODEL_PATH   = str(Path(__file__).resolve().parent / 'skin_analysis_updated.onnx')
CASCADE_PATH = str(Path(__file__).resolve().parent / 'haarcascade_frontalface_alt.xml')

# ── Class mapping ───────────────────────────────────────────────────────────────
# 0=Dry, 1=Oily, 2=Normal
CLASS_NAMES = {0: 'dry', 1: 'oily', 2: 'normal'}

# ── Global cache ────────────────────────────────────────────────────────────────
_onnx_session = None
_face_cascade = None
_mp_detector  = None


def _get_session():
    """Load ONNX model once and cache."""
    global _onnx_session
    if _onnx_session is None:
        try:
            import onnxruntime as ort
            logger.info("Loading ONNX model from: %s", MODEL_PATH)
            _onnx_session = ort.InferenceSession(
                MODEL_PATH,
                providers=['CPUExecutionProvider'],
            )
            logger.info("ONNX loaded ✅  input: %s", _onnx_session.get_inputs()[0].name)
        except Exception as e:
            logger.error("Failed to load ONNX model: %s", str(e))
            raise Exception(f"Could not load skin model: {str(e)}")
    return _onnx_session


def _detect_face_mediapipe(img):
    """
    Detect face using MediaPipe 0.10.x new API (FaceDetector task).
    Returns:
        list of (x, y, w, h)  — empty list means no faces found
        None                   — MediaPipe unavailable, use Haar fallback
    """
    global _mp_detector
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        import cv2

        if _mp_detector is None:
            base_options = mp_python.BaseOptions(
                model_asset_path=str(
                    Path(__file__).resolve().parent / 'blaze_face_short_range.tflite'
                )
            )
            options = mp_vision.FaceDetectorOptions(
                base_options            = base_options,
                min_detection_confidence= 0.4,
            )
            _mp_detector = mp_vision.FaceDetector.create_from_options(options)
            logger.info("MediaPipe 0.10.x FaceDetector loaded ✅")

        h, w    = img.shape[:2]
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        results  = _mp_detector.detect(mp_image)

        if not results.detections:
            return []

        faces = []
        for det in results.detections:
            box = det.bounding_box
            faces.append((box.origin_x, box.origin_y, box.width, box.height))

        return faces

    except Exception as e:
        logger.warning("MediaPipe failed (%s) — falling back to Haar Cascade", str(e))
        return None   # signals caller to use Haar Cascade


def _detect_face_haar(img):
    """
    Detect face using Haar Cascade (fallback).
    Tries multiple settings from strict to lenient.
    Returns list of (x, y, w, h) or empty list.
    """
    global _face_cascade
    import cv2

    if _face_cascade is None:
        _face_cascade = cv2.CascadeClassifier(CASCADE_PATH)
        if _face_cascade.empty():
            raise Exception("Haar Cascade file not found!")
        logger.info("Haar Cascade loaded ✅")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Try increasingly lenient settings until a face is found
    for (scale, neighbors) in [(1.05, 3), (1.1, 3), (1.1, 2), (1.15, 2)]:
        faces = _face_cascade.detectMultiScale(
            gray,
            scaleFactor  = scale,
            minNeighbors = neighbors,
            minSize      = (30, 30),
        )
        if len(faces) > 0:
            logger.info("Haar found face — scale=%.2f neighbors=%d", scale, neighbors)
            return list(faces)

    return []


def predict_skin_type(image_path: str) -> tuple:
    """
    Predict skin type from a face image.

    Pipeline:
      1. Load image with OpenCV
      2. Detect face (MediaPipe first, Haar Cascade fallback)
      3. Validate — reject if no face or multiple faces
      4. Crop face ROI with 10% padding
      5. Resize to 128x128 and normalize /255.0
      6. Run ONNX model prediction
      7. Return result

    Args:
        image_path: Absolute path to the image file.

    Returns:
        tuple: (skin_type, confidence, dry_prob, oily_prob, normal_prob)

    Raises:
        Exception with codes: NO_FACE_DETECTED | MULTIPLE_FACES | INVALID_IMAGE
    """
    try:
        import cv2

        session = _get_session()

        # ── Step 1: Load image ─────────────────────────────────────────────────
        img = cv2.imread(image_path)
        if img is None:
            raise Exception("INVALID_IMAGE: Could not read the image file.")

        logger.info("Image loaded — shape: %s", img.shape)

        # ── Step 2: Face detection ─────────────────────────────────────────────
        # Try MediaPipe first, fall back to Haar Cascade automatically
        faces = _detect_face_mediapipe(img)

        if faces is None:
            # MediaPipe failed — use Haar Cascade
            faces         = _detect_face_haar(img)
            detector_used = "Haar Cascade"
        else:
            detector_used = "MediaPipe"

        logger.info("%s detected %d face(s)", detector_used, len(faces))

        # ── Step 3: Validate face count ────────────────────────────────────────
        if len(faces) == 0:
            raise Exception("NO_FACE_DETECTED: No face detected in the image.")
        elif len(faces) > 1:
            raise Exception("MULTIPLE_FACES: Multiple faces detected in the image.")

        # ── Step 4: Crop face ROI with 10% padding ─────────────────────────────
        (x, y, w, h) = faces[0]
        pad_x = int(w * 0.10)
        pad_y = int(h * 0.10)
        x1    = max(0, x - pad_x)
        y1    = max(0, y - pad_y)
        x2    = min(img.shape[1], x + w + pad_x)
        y2    = min(img.shape[0], y + h + pad_y)
        roi   = img[y1:y2, x1:x2]
        logger.info("ROI: x=%d y=%d w=%d h=%d", x1, y1, x2-x1, y2-y1)

        # ── Step 5: Preprocess — matches interference.py exactly ───────────────
        roi_resized = cv2.resize(roi, (128, 128))
        img_array   = roi_resized.astype('float32') / 255.0
        img_array   = np.expand_dims(img_array, axis=0)   # (1, 128, 128, 3)

        # ── Step 6: ONNX inference ─────────────────────────────────────────────
        input_name = session.get_inputs()[0].name
        pred_probs = session.run(None, {input_name: img_array})[0][0]  # (3,)

        predicted_index = int(np.argmax(pred_probs))
        confidence      = float(pred_probs[predicted_index])
        skin_type       = CLASS_NAMES[predicted_index]

        dry_prob    = float(pred_probs[0])
        oily_prob   = float(pred_probs[1])
        normal_prob = float(pred_probs[2])

        # ── Confidence label ───────────────────────────────────────────────────
        if confidence >= 0.85:
            conf_level = "HIGH — model is very sure"
        elif confidence >= 0.65:
            conf_level = "MEDIUM — model is moderately sure"
        else:
            conf_level = "LOW — model is guessing"

        # ── Terminal debug output ──────────────────────────────────────────────
        def bar(prob):
            filled = int(prob * 20)
            return "█" * filled + "░" * (20 - filled)

        print("\n")
        print("=" * 56)
        print("  SKIN MODEL DEBUG OUTPUT  (ONNX + Face Detection)")
        print("=" * 56)
        print(f"  Image path   : {image_path}")
        print(f"  Detector     : {detector_used}")
        print(f"  Faces found  : {len(faces)}")
        print(f"  Final result : {skin_type.upper()}")
        print(f"  Confidence   : {confidence:.4f} ({confidence*100:.1f}%)")
        print(f"  Level        : {conf_level}")
        print("-" * 56)
        print("  RAW PROBABILITIES:")
        print(f"  Dry    {bar(dry_prob)}  {dry_prob:.4f} ({dry_prob*100:.1f}%)")
        print(f"  Oily   {bar(oily_prob)}  {oily_prob:.4f} ({oily_prob*100:.1f}%)")
        print(f"  Normal {bar(normal_prob)}  {normal_prob:.4f} ({normal_prob*100:.1f}%)")
        print("-" * 56)
        print("  DIAGNOSIS:")
        max_prob = max(dry_prob, oily_prob, normal_prob)
        min_prob = min(dry_prob, oily_prob, normal_prob)
        if confidence < 0.65:
            print("  [!] LOW CONFIDENCE — model is not sure")
        if max_prob - min_prob < 0.30:
            print("  [!] All probabilities close — model uncertain")
        if confidence >= 0.75 and max_prob - min_prob >= 0.40:
            print("  [OK] Model is confident and decisive ✅")
        print("=" * 56)
        print("\n")

        logger.info(
            "RESULT — skin_type=%s | confidence=%.2f%% | "
            "dry=%.4f | oily=%.4f | normal=%.4f | level=%s",
            skin_type, confidence * 100,
            dry_prob, oily_prob, normal_prob, conf_level,
        )

        return skin_type, confidence, dry_prob, oily_prob, normal_prob

    except Exception as e:
        error_msg = str(e)

        if "NO_FACE_DETECTED" in error_msg:
            raise Exception("NO_FACE_DETECTED")
        elif "MULTIPLE_FACES" in error_msg:
            raise Exception("MULTIPLE_FACES")
        elif "INVALID_IMAGE" in error_msg:
            raise Exception("INVALID_IMAGE")

        logger.error("Prediction failed: %s", error_msg)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise Exception(f"Prediction failed: {error_msg}")