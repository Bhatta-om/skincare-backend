# ml_models/skin_model.py
# ═══════════════════════════════════════════════════════════════════════════════
# FIX — return value order corrected (was causing silent data corruption)
#
# BEFORE (wrong):
#   return skin_type, confidence, dry_prob, normal_prob, oily_prob
#   positions:                          2           3          4
#
# AFTER (correct):
#   return skin_type, confidence, dry_prob, oily_prob, normal_prob
#   positions:                          2          3           4
#
# Why this matters:
#   skin_analysis/views.py unpacks as:
#     skin_type, confidence, dry_prob, oily_prob, normal_prob = result
#   The old order had oily_prob and normal_prob SWAPPED, meaning:
#     - analysis.oily_probability  was being saved with normal_prob's value
#     - analysis.normal_probability was being saved with oily_prob's value
#   This corrupted concern detection for every single analysis silently.
#   An oily-skin user detected as "oily" with 85% confidence would have
#   their oily_probability saved as ~0.05 (normal value) instead of 0.85.
# ═══════════════════════════════════════════════════════════════════════════════

import numpy as np
import logging
import traceback
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

# ── Model path ────────────────────────────────────────────
MODEL_PATH = str(Path(__file__).resolve().parent / 'skin_analysis_updated.keras')

# ── Class mapping ─────────────────────────────────────────
# index 0 = dry, index 1 = normal, index 2 = oily
# Must match the class order your model was trained with.
CLASS_NAMES = {0: 'dry', 1: 'normal', 2: 'oily'}

# ── Global model cache ────────────────────────────────────
# Loaded once on first request, then reused for all subsequent requests.
# Avoids the 3–5 second Keras load time on every API call.
_model = None


def _get_model():
    """Load Keras model once and cache in memory."""
    global _model
    if _model is None:
        try:
            import tensorflow as tf
            logger.info("Loading Keras model from: %s", MODEL_PATH)
            _model = tf.keras.models.load_model(MODEL_PATH)
            logger.info("Keras model loaded successfully ✅")
        except Exception as e:
            logger.error("Failed to load Keras model: %s", str(e))
            raise Exception(f"Could not load skin model: {str(e)}")
    return _model


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
        model = _get_model()

        # ── Preprocess ────────────────────────────────────
        img       = Image.open(image_path).convert('RGB')
        img       = img.resize((128, 128), Image.Resampling.LANCZOS)
        img_array = np.array(img).astype('float32') / 255.0
        img_array = np.expand_dims(img_array, axis=0)   # → (1, 128, 128, 3)

        logger.info("Input shape: %s", img_array.shape)

        # ── Inference ─────────────────────────────────────
        predictions     = model.predict(img_array, verbose=0)[0]  # shape: (3,)
        predicted_index = int(np.argmax(predictions))
        confidence      = float(predictions[predicted_index])
        skin_type       = CLASS_NAMES[predicted_index]

        # ── Extract per-class probabilities ───────────────
        # Index order matches CLASS_NAMES: 0=dry, 1=normal, 2=oily
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
        print("  SKIN MODEL DEBUG OUTPUT  (Keras)")
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

        # ── Structured log for deployed server ────────────
        logger.info(
            "RESULT — skin_type=%s | confidence=%.2f%% | "
            "dry=%.4f | oily=%.4f | normal=%.4f | level=%s",
            skin_type, confidence * 100,
            dry_prob, oily_prob, normal_prob,
            conf_level,
        )

        # ═══════════════════════════════════════════════════
        # CRITICAL: return order must match how views.py unpacks
        #
        # views.py:  skin_type, confidence, dry_prob, oily_prob, normal_prob
        #                                        ↑          ↑           ↑
        # OLD wrong: dry_prob, normal_prob, oily_prob  (positions 3,4 swapped)
        # FIXED now: dry_prob,   oily_prob, normal_prob (correct)
        # ═══════════════════════════════════════════════════
        return skin_type, confidence, dry_prob, oily_prob, normal_prob

    except Exception as e:
        logger.error("Prediction failed: %s", str(e))
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise Exception(f"Prediction failed: {str(e)}")