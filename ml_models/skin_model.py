import numpy as np
import logging
import traceback
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

# Model path
MODEL_PATH = str(Path(__file__).resolve().parent / 'skin_best.tflite')

# Class mapping
CLASS_NAMES = {0: 'dry', 1: 'normal', 2: 'oily'}

def predict_skin_type(image_path):
    """
    Predict skin type using TFLite model.
    Args:    image_path: Path to uploaded image
    Returns: (skin_type, confidence_score)
    """
    try:
        # Load TFLite interpreter
        try:
            import tflite_runtime.interpreter as tflite
            interpreter = tflite.Interpreter(model_path=MODEL_PATH)
            logger.info("Using tflite_runtime")
        except ImportError:
            import tensorflow as tf
            interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
            logger.info("Using tensorflow lite")

        interpreter.allocate_tensors()
        input_details  = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        # Preprocess image
        img = Image.open(image_path).convert('RGB')
        img = img.resize((128, 128), Image.Resampling.LANCZOS)
        img_array = np.array(img).astype('float32') / 255.0
        img_array = np.expand_dims(img_array, axis=0)

        logger.info("Input shape: %s", img_array.shape)

        # Run inference
        interpreter.set_tensor(input_details[0]['index'], img_array)
        interpreter.invoke()

        # Get predictions
        predictions = interpreter.get_tensor(output_details[0]['index'])[0]
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