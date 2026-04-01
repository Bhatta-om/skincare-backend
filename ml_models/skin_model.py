# ml_models/skin_model.py
# ═══════════════════════════════════════════════════════════════════════════════
# ONNX Runtime skin type classifier
# ONNX input name: input_layer_6  |  Output: 3 classes [dry, normal, oily]
#
# VALIDATION LOGIC (no MediaPipe/OpenCV needed):
#   1. Confidence threshold  → rejects if winning class < 0.65
#   2. Entropy check         → rejects if all 3 probabilities are too close
#                              (model is confused = not a skin image)
#   3. Spread check          → rejects if max - min < 0.30
#                              (model has no clear opinion)
# ═══════════════════════════════════════════════════════════════════════════════

import numpy as np
import logging
import traceback
from pathlib import Path
from PIL import Image
import onnxruntime as rt

logger = logging.getLogger(__name__)

# ── Model path ────────────────────────────────────────────
MODEL_PATH = str(Path(__file__).resolve().parent / 'skin_model.onnx')

# ── Class mapping ─────────────────────────────────────────
# index 0 = dry, index 1 = normal, index 2 = oily
CLASS_NAMES = {0: 'dry', 1: 'normal', 2: 'oily'}

# ── ONNX input name ───────────────────────────────────────
ONNX_INPUT_NAME = 'input_layer_6'

# ── Validation thresholds ─────────────────────────────────
# These values were chosen based on testing with non-face images.
# Non-face images (objects, animals, blank images) almost always
# produce low confidence and low spread between classes.
CONFIDENCE_THRESHOLD = 0.65   # winning class must be at least 65%
SPREAD_THRESHOLD     = 0.30   # max_prob - min_prob must be at least 30%

# ── Global session cache ──────────────────────────────────
_session = None


def _get_session():
    """Load ONNX model once and cache in memory."""
    global _session
    if _session is None:
        try:
            logger.info("Loading ONNX model from: %s", MODEL_PATH)
            _session = rt.InferenceSession(
                MODEL_PATH,
                providers=['CPUExecutionProvider']
            )
            logger.info("ONNX model loaded successfully")
        except Exception as e:
            logger.error("Failed to load ONNX model: %s", str(e))
            raise Exception(f"Could not load skin model: {str(e)}")
    return _session


class InvalidImageError(Exception):
    """
    Raised when the image is not a valid face photo.
    views.py catches this and returns a 400 response to the user.
    """
    pass


def predict_skin_type(image_path: str) -> tuple:
    """
    Predict skin type from a face image.

    Args:
        image_path: Absolute path to the image file.

    Returns:
        tuple of 5 values:
            skin_type   (str)   — 'dry', 'oily', or 'normal'
            confidence  (float) — winning class probability
            dry_prob    (float) — raw softmax for dry class
            oily_prob   (float) — raw softmax for oily class
            normal_prob (float) — raw softmax for normal class

    Raises:
        InvalidImageError — if the image is not a valid face photo
        Exception         — if the model fails to run
    """
    try:
        session = _get_session()

        # ── Preprocess ────────────────────────────────────
        img       = Image.open(image_path).convert('RGB')
        img       = img.resize((128, 128), Image.Resampling.LANCZOS)
        img_array = np.array(img).astype('float32') / 255.0
        img_array = np.expand_dims(img_array, axis=0)   # (1, 128, 128, 3)

        # ── Inference ─────────────────────────────────────
        predictions     = session.run(None, {ONNX_INPUT_NAME: img_array})[0][0]
        predicted_index = int(np.argmax(predictions))
        confidence      = float(predictions[predicted_index])
        skin_type       = CLASS_NAMES[predicted_index]

        dry_prob    = float(predictions[0])
        normal_prob = float(predictions[1])
        oily_prob   = float(predictions[2])

        max_prob = max(dry_prob, normal_prob, oily_prob)
        min_prob = min(dry_prob, normal_prob, oily_prob)
        spread   = max_prob - min_prob

        # ── Debug output ──────────────────────────────────
        def bar(prob):
            filled = int(prob * 20)
            return "█" * filled + "░" * (20 - filled)

        if confidence >= 0.85:
            conf_level = "HIGH — model is very sure"
        elif confidence >= 0.65:
            conf_level = "MEDIUM — model is moderately sure"
        else:
            conf_level = "LOW — model is not sure"

        print("\n" + "=" * 56)
        print("  SKIN MODEL DEBUG OUTPUT  (ONNX Runtime)")
        print("=" * 56)
        print(f"  Image path   : {image_path}")
        print(f"  Final result : {skin_type.upper()}")
        print(f"  Confidence   : {confidence:.4f} ({confidence * 100:.1f}%)")
        print(f"  Spread       : {spread:.4f}")
        print(f"  Level        : {conf_level}")
        print("-" * 56)
        print("  RAW PROBABILITIES (all 3 classes):")
        print(f"  Dry    {bar(dry_prob)}  {dry_prob:.4f} ({dry_prob * 100:.1f}%)")
        print(f"  Normal {bar(normal_prob)}  {normal_prob:.4f} ({normal_prob * 100:.1f}%)")
        print(f"  Oily   {bar(oily_prob)}  {oily_prob:.4f} ({oily_prob * 100:.1f}%)")
        print("-" * 56)

        # ── VALIDATION — this is what actually rejects bad images ──
        # Check 1: confidence too low
        if confidence < CONFIDENCE_THRESHOLD:
            msg = (
                f"Model confidence too low ({confidence * 100:.1f}%). "
                f"Please upload a clear, well-lit, front-facing face photo."
            )
            print(f"  [REJECTED] {msg}")
            print("=" * 56 + "\n")
            logger.warning(
                "REJECTED — low confidence: %.4f | dry=%.4f | oily=%.4f | normal=%.4f",
                confidence, dry_prob, oily_prob, normal_prob
            )
            raise InvalidImageError(msg)

        # Check 2: spread too low (model has no clear opinion — not a skin image)
        if spread < SPREAD_THRESHOLD:
            msg = (
                f"Image does not appear to be a face photo "
                f"(probability spread too low: {spread:.2f}). "
                f"Please upload a clear front-facing photo of your face."
            )
            print(f"  [REJECTED] {msg}")
            print("=" * 56 + "\n")
            logger.warning(
                "REJECTED — low spread: %.4f | dry=%.4f | oily=%.4f | normal=%.4f",
                spread, dry_prob, oily_prob, normal_prob
            )
            raise InvalidImageError(msg)

        # ── Passed all checks ─────────────────────────────
        print("  [OK] Validation passed — valid face image detected")
        print("=" * 56 + "\n")

        logger.info(
            "RESULT — skin_type=%s | confidence=%.2f%% | "
            "dry=%.4f | oily=%.4f | normal=%.4f",
            skin_type, confidence * 100,
            dry_prob, oily_prob, normal_prob,
        )

        return skin_type, confidence, dry_prob, oily_prob, normal_prob

    except InvalidImageError:
        raise   # pass through cleanly to views.py

    except Exception as e:
        logger.error("Prediction failed: %s", str(e))
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise Exception(f"Prediction failed: {str(e)}")