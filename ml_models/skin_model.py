# ml_models/skin_model.py
# ═══════════════════════════════════════════════════════════════════════════════
# Migrated from TensorFlow/Keras → ONNX Runtime
# Benefits: ~10x faster cold start, no TensorFlow dependency on server
# ONNX input name: input_layer_6  |  Output: 3 classes [dry, normal, oily]
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

# ── ONNX input name (from conversion output) ─────────────
ONNX_INPUT_NAME = 'input_layer_6'

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
            logger.info("ONNX model loaded successfully ✅")
        except Exception as e:
            logger.error("Failed to load ONNX model: %s", str(e))
            raise Exception(f"Could not load skin model: {str(e)}")
    return _session


def predict_skin_type(image_path: str) -> tuple:
    """
    Predict skin type from a face image.

    Args:
        image_path: Absolute path to the image file.

    Returns:
        tuple of 5 values — MUST be unpacked in this exact order:
            skin_type   (str)   — 'dry', 'oily', or 'normal'
            confidence  (float) — winning class probability, e.g. 0.8571
            dry_prob    (float) — raw softmax output for dry class
            oily_prob   (float) — raw softmax output for oily class
            normal_prob (float) — raw softmax output for normal class

    Consumer (skin_analysis/views.py) unpacks exactly as:
        skin_type, confidence, dry_prob, oily_prob, normal_prob = predict_skin_type(path)
    """
    try:
        session = _get_session()

        # ── Preprocess ────────────────────────────────────
        img       = Image.open(image_path).convert('RGB')
        img       = img.resize((128, 128), Image.Resampling.LANCZOS)
        img_array = np.array(img).astype('float32') / 255.0
        img_array = np.expand_dims(img_array, axis=0)   # → (1, 128, 128, 3)

        logger.info("Input shape: %s", img_array.shape)

        # ── Inference ─────────────────────────────────────
        predictions     = session.run(None, {ONNX_INPUT_NAME: img_array})[0][0]  # shape: (3,)
        predicted_index = int(np.argmax(predictions))
        confidence      = float(predictions[predicted_index])
        skin_type       = CLASS_NAMES[predicted_index]

        # ── Extract per-class probabilities ───────────────
        dry_prob    = float(predictions[0])
        normal_prob = float(predictions[1])
        oily_prob   = float(predictions[2])

        # ── Confidence label ──────────────────────────────
        if confidence >= 0.85:
            conf_level = "HIGH — model is very sure"
        elif confidence >= 0.65:
            conf_level = "MEDIUM — model is moderately sure"
        else:
            conf_level = "LOW — model is guessing"

        # ── Terminal debug output ─────────────────────────
        def bar(prob):
            filled = int(prob * 20)
            return "█" * filled + "░" * (20 - filled)

        print("\n")
        print("=" * 56)
        print("  SKIN MODEL DEBUG OUTPUT  (ONNX Runtime)")
        print("=" * 56)
        print(f"  Image path   : {image_path}")
        print(f"  Final result : {skin_type.upper()}")
        print(f"  Confidence   : {confidence:.4f} ({confidence * 100:.1f}%)")
        print(f"  Level        : {conf_level}")
        print("-" * 56)
        print("  RAW PROBABILITIES (all 3 classes):")
        print(f"  Dry    {bar(dry_prob)}  {dry_prob:.4f} ({dry_prob * 100:.1f}%)")
        print(f"  Normal {bar(normal_prob)}  {normal_prob:.4f} ({normal_prob * 100:.1f}%)")
        print(f"  Oily   {bar(oily_prob)}  {oily_prob:.4f} ({oily_prob * 100:.1f}%)")
        print("-" * 56)

        # ── Diagnosis ─────────────────────────────────────
        print("  DIAGNOSIS:")
        if confidence < 0.65:
            print("  [!] LOW CONFIDENCE — model is not sure")
            print("      Image may not be a clear face photo")
        elif oily_prob > 0.70:
            print("  [!] Strong oily prediction")
        elif dry_prob > 0.70:
            print("  [!] Strong dry prediction")
        elif normal_prob > 0.70:
            print("  [!] Strong normal prediction")

        max_prob = max(dry_prob, normal_prob, oily_prob)
        min_prob = min(dry_prob, normal_prob, oily_prob)
        if max_prob - min_prob < 0.30:
            print("  [!] All probabilities close — model uncertain")
        if confidence >= 0.75 and max_prob - min_prob >= 0.40:
            print("  [OK] Model is confident and decisive ✅")

        print("=" * 56)
        print("\n")

        # ── Structured log ────────────────────────────────
        logger.info(
            "RESULT — skin_type=%s | confidence=%.2f%% | "
            "dry=%.4f | oily=%.4f | normal=%.4f | level=%s",
            skin_type, confidence * 100,
            dry_prob, oily_prob, normal_prob,
            conf_level,
        )

        return skin_type, confidence, dry_prob, oily_prob, normal_prob

    except Exception as e:
        logger.error("Prediction failed: %s", str(e))
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise Exception(f"Prediction failed: {str(e)}")