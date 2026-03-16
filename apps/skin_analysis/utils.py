# apps/skin_analysis/utils.py

import numpy as np
from PIL import Image
import io

def preprocess_image_for_model(image_file, target_size=(224, 224)):
    """
    CNN model ko lagi image preprocess garcha
    
    Steps:
    1. Open image
    2. Convert to RGB
    3. Resize to target_size
    4. Normalize pixel values (0-1)
    5. Add batch dimension
    
    Args:
        image_file: UploadedFile or file path
        target_size: tuple (width, height)
    
    Returns:
        numpy.ndarray: Preprocessed image array (1, 224, 224, 3)
    """
    
    # Open image
    if hasattr(image_file, 'read'):
        # UploadedFile object
        img = Image.open(image_file)
    else:
        # File path
        img = Image.open(image_file)
    
    # Convert to RGB (grayscale huna sakcha)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Resize
    img = img.resize(target_size, Image.Resampling.LANCZOS)
    
    # Convert to numpy array
    img_array = np.array(img)
    
    # Normalize (0-255 → 0-1)
    img_array = img_array.astype('float32') / 255.0
    
    # Add batch dimension (224, 224, 3) → (1, 224, 224, 3)
    img_array = np.expand_dims(img_array, axis=0)
    
    return img_array


def extract_face_region(image_path):
    """
    Face detection using OpenCV (optional enhancement)
    
    Future implementation:
    - Detect face using Haar Cascade or dlib
    - Crop to face region only
    - Improves CNN accuracy
    
    Args:
        image_path: Path to image
    
    Returns:
        PIL.Image: Cropped face image
    """
    # TODO: Implement face detection
    # import cv2
    # face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
    # ...
    
    # For now, return original image
    return Image.open(image_path)


def calculate_skin_tone(image_array):
    """
    Skin tone calculation (average RGB)
    
    Can be used for:
    - Skin tone classification (fair, medium, dark)
    - Additional feature for CNN
    
    Args:
        image_array: numpy array
    
    Returns:
        tuple: (R, G, B) average values
    """
    # Calculate mean RGB
    r_mean = np.mean(image_array[:, :, 0])
    g_mean = np.mean(image_array[:, :, 1])
    b_mean = np.mean(image_array[:, :, 2])
    
    return (r_mean, g_mean, b_mean)


def augment_image(image_array):
    """
    Image augmentation for training (not used in production)
    
    Augmentations:
    - Rotation
    - Flip
    - Brightness adjustment
    - Contrast adjustment
    
    Used during model training only
    """
    # TODO: Implement if needed for model training
    pass