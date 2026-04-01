# ml_models/skin_model.py
# Uses ONNX runtime for inference + Haar Cascade for face detection
# Matches friend's interference.py exactly:
#   - Face detection first (haarcascade_frontalface_alt.xml)
#   - Crops face ROI before prediction
#   - Resize to 128x128, normalize /255.0
#   - Class order: 0=Dry, 1=Oily, 2=Normal

import numpy as np
import logging
import traceback
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
MODEL_PATH   = str(Path(__file__).resolve().parent / 'skin_analysis_updated.onnx')
CASCADE_PATH = str(Path(__file__).resolve().parent / 'haarcascade_frontalface_alt.xml')

# ── Class mapping — matches friend's interference.py ───────────────────────────
# 0=Dry, 1=Oily, 2=Normal
CLASS_NAMES = {0: 'dry', 1: 'oily', 2: 'normal'}

# ── Global cache — load once, reuse forever ────────────────────────────────────
_onnx_session = None
_face_cascade  = None


def _get_session():
    """Load ONNX model once and cache in memory."""
    global _onnx_session
    if _onnx_session is None:
        try:
            import onnxruntime as ort
            logger.info("Loading ONNX model from: %s", MODEL_PATH)
            _onnx_session = ort.InferenceSession(
                MODEL_PATH,
                providers=['CPUExecutionProvider'],
            )
            logger.info("ONNX model loaded ✅  |  input: %s", _onnx_session.get_inputs()[0].name)
        except Exception as e:
            logger.error("Failed to load ONNX model: %s", str(e))
            raise Exception(f"Could not load skin model: {str(e)}")
    return _onnx_session


def _get_face_cascade():
    """Load Haar Cascade once and cache in memory."""
    global _face_cascade
    if _face_cascade is None:
        try:
            import cv2
            logger.info("Loading Haar Cascade from: %s", CASCADE_PATH)
            _face_cascade = cv2.CascadeClassifier(CASCADE_PATH)
            if _face_cascade.empty():
                raise Exception("Haar Cascade file is empty or not found!")
            logger.info("Haar Cascade loaded ✅")
        except Exception as e:
            logger.error("Failed to load Haar Cascade: %s", str(e))
            raise Exception(f"Could not load face detector: {str(e)}")
    return _face_cascade


def predict_skin_type(image_path: str) -> tuple:
    """
    Predict skin type from a face image.

    Pipeline (matches friend's interference.py):
      1. Load image with OpenCV
      2. Detect face using Haar Cascade
      3. Crop face ROI
      4. Resize to 128x128 and normalize /255.0
      5. Run ONNX model prediction
      6. Return result

    Args:
        image_path: Absolute path to the image file.

    Returns:
        tuple: (skin_type, confidence, dry_prob, oily_prob, normal_prob)

    Raises:
        Exception with codes: NO_FACE_DETECTED | MULTIPLE_FACES | INVALID_IMAGE
    """
    try:
        import cv2

        session      = _get_session()
        face_cascade = _get_face_cascade()

        # ── Step 1: Load image ─────────────────────────────────────────────────
        img = cv2.imread(image_path)
        if img is None:
            raise Exception("INVALID_IMAGE: Could not read the image file.")

        # ── Step 2: Face detection (Haar Cascade) ──────────────────────────────
        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor  = 1.1,
            minNeighbors = 5,
        )

        logger.info("Haar Cascade detected %d face(s)", len(faces))

        if len(faces) == 0:
            raise Exception("NO_FACE_DETECTED: No face detected in the image.")
        elif len(faces) > 1:
            raise Exception("MULTIPLE_FACES: Multiple faces detected in the image.")

        # ── Step 3: Crop face ROI ──────────────────────────────────────────────
        (x, y, w, h) = faces[0]
        roi = img[y:y+h, x:x+w]
        logger.info("Face ROI cropped: x=%d y=%d w=%d h=%d", x, y, w, h)

        # ── Step 4: Preprocess — matches interference.py exactly ───────────────
        roi_resized = cv2.resize(roi, (128, 128))
        img_array   = roi_resized.astype('float32') / 255.0
        img_array   = np.expand_dims(img_array, axis=0)   # shape: (1, 128, 128, 3)

        logger.info("Input array shape: %s  dtype: %s", img_array.shape, img_array.dtype)

        # ── Step 5: ONNX inference ─────────────────────────────────────────────
        input_name  = session.get_inputs()[0].name
        pred_probs  = session.run(None, {input_name: img_array})[0][0]  # shape: (3,)

        predicted_index = int(np.argmax(pred_probs))
        confidence      = float(pred_probs[predicted_index])
        skin_type       = CLASS_NAMES[predicted_index]

        # ── Per-class probabilities (order: 0=dry, 1=oily, 2=normal) ──────────
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
        print("  SKIN MODEL DEBUG OUTPUT  (ONNX + Haar Cascade)")
        print("=" * 56)
        print(f"  Image path   : {image_path}")
        print(f"  Faces found  : {len(faces)}")
        print(f"  Final result : {skin_type.upper()}")
        print(f"  Confidence   : {confidence:.4f} ({confidence*100:.1f}%)")
        print(f"  Level        : {conf_level}")
        print("-" * 56)
        print("  RAW PROBABILITIES (all 3 classes):")
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

        # Re-raise face detection / image errors with clean codes
        if "NO_FACE_DETECTED" in error_msg:
            raise Exception("NO_FACE_DETECTED")
        elif "MULTIPLE_FACES" in error_msg:
            raise Exception("MULTIPLE_FACES")
        elif "INVALID_IMAGE" in error_msg:
            raise Exception("INVALID_IMAGE")

        logger.error("Prediction failed: %s", error_msg)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise Exception(f"Prediction failed: {error_msg}")