import numpy as np
import logging
import traceback
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

# Model path — using ONNX now
MODEL_PATH = str(Path(__file__).resolve().parent / 'skin_best.onnx')

# Class mapping
CLASS_NAMES = {0: 'dry', 1: 'normal', 2: 'oily'}


def predict_skin_type(image_path):
    """
    Predict skin type using ONNX model.
    Args:    image_path: Path to uploaded image
    Returns: (skin_type, confidence_score)
    """
    try:
        import onnxruntime as ort

        # Load ONNX session
        session = ort.InferenceSession(MODEL_PATH)
        input_name = session.get_inputs()[0].name
        logger.info("ONNX model loaded, input name: %s", input_name)

        # Preprocess image
        img = Image.open(image_path).convert('RGB')
        img = img.resize((128, 128), Image.Resampling.LANCZOS)
        img_array = np.array(img).astype('float32') / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        logger.info("Input shape: %s", img_array.shape)

        # Run inference
        predictions = session.run(None, {input_name: img_array})[0][0]
        predicted_index = int(np.argmax(predictions))
        confidence = float(predictions[predicted_index])
        skin_type = CLASS_NAMES[predicted_index]

        logger.info(
            "RESULT — skin_type: %s | confidence: %.2f%% | dry=%.4f, normal=%.4f, oily=%.4f",
            skin_type, confidence * 100,
            predictions[0], predictions[1], predictions[2]
        )

        return skin_type, confidence

    except Exception as e:
        logger.error("Prediction failed: %s", str(e))
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise Exception(f"Prediction failed: {str(e)}")