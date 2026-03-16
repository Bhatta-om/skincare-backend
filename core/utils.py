# core/utils.py

import os
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
import io

# ════════════════════════════════════════════════════════════
# IMAGE VALIDATION
# ════════════════════════════════════════════════════════════

def validate_image_file(image):
    """
    Image file validation — size, format check
    
    Args:
        image: UploadedFile object
    
    Raises:
        ValidationError: Invalid image bhayo bhane
    """
    # File size check (5MB max)
    max_size = 5 * 1024 * 1024  # 5MB
    if image.size > max_size:
        raise ValidationError("Image size must be under 5MB!")
    
    # File extension check
    valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    ext = os.path.splitext(image.name)[1].lower()
    if ext not in valid_extensions:
        raise ValidationError(f"Invalid file format. Allowed: {', '.join(valid_extensions)}")
    
    # Actual image ho ki nai verify gara
    try:
        img = Image.open(image)
        img.verify()  # Corrupted image detect garcha
    except Exception:
        raise ValidationError("Invalid or corrupted image file!")
    
    return True


def compress_image(image, max_width=1024, quality=85):
    """
    Image compress gara — storage bachaucha
    
    Args:
        image: UploadedFile object
        max_width: Maximum width in pixels
        quality: JPEG quality (0-100)
    
    Returns:
        InMemoryUploadedFile: Compressed image
    """
    img = Image.open(image)
    
    # Convert RGBA to RGB (PNG → JPEG ko lagi)
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    
    # Resize if too large
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    
    # Save to BytesIO
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    
    # Return as UploadedFile
    return InMemoryUploadedFile(
        output, 'ImageField',
        f"{os.path.splitext(image.name)[0]}.jpg",
        'image/jpeg',
        output.getbuffer().nbytes,
        None
    )


# ════════════════════════════════════════════════════════════
# IMAGE PREPROCESSING FOR CNN
# ════════════════════════════════════════════════════════════

def preprocess_image_for_cnn(image_path, target_size=(224, 224)):
    """
    CNN model ko lagi image prepare garcha
    
    Args:
        image_path: File path or UploadedFile
        target_size: Target dimensions (width, height)
    
    Returns:
        PIL.Image: Preprocessed image
    """
    img = Image.open(image_path)
    
    # RGB convert (grayscale huna sakcha)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Resize
    img = img.resize(target_size, Image.Resampling.LANCZOS)
    
    return img


def image_to_array(image):
    """
    PIL Image lai numpy array ma convert garcha (CNN input ko lagi)
    
    Args:
        image: PIL.Image object
    
    Returns:
        numpy.ndarray: Normalized array
    """
    import numpy as np
    
    # Convert to array
    img_array = np.array(image)
    
    # Normalize (0-255 → 0-1)
    img_array = img_array.astype('float32') / 255.0
    
    # Add batch dimension (224, 224, 3) → (1, 224, 224, 3)
    img_array = np.expand_dims(img_array, axis=0)
    
    return img_array


# ════════════════════════════════════════════════════════════
# GENERAL UTILITIES
# ════════════════════════════════════════════════════════════

def generate_unique_filename(instance, filename):
    """
    Unique filename generate garcha — duplicate files avoid huncha
    
    Usage in models:
    image = models.ImageField(upload_to=generate_unique_filename)
    """
    import uuid
    ext = os.path.splitext(filename)[1]
    new_filename = f"{uuid.uuid4().hex}{ext}"
    return os.path.join('uploads', new_filename)


def calculate_discount_price(original_price, discount_percent):
    """
    Discount calculate garcha
    
    Args:
        original_price: Decimal
        discount_percent: Float (e.g., 15.0 for 15%)
    
    Returns:
        Decimal: Discounted price
    """
    from decimal import Decimal
    discount_amount = original_price * Decimal(discount_percent / 100)
    return original_price - discount_amount


def format_price(price):
    """
    Price lai readable format ma convert garcha
    
    Args:
        price: Decimal or float
    
    Returns:
        str: "Rs. 1,299.00"
    """
    return f"Rs. {price:,.2f}"