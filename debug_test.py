# -*- coding: utf-8 -*-
# TEMPORARY DEBUG FILE
# Run: python debug_test.py

import os
import sys

print("=" * 60)
print("SKIN ANALYSIS PIPELINE DEBUG TEST")
print("=" * 60)

# Test 1: OpenCV
print("\n[TEST 1] Importing OpenCV...")
try:
    import cv2
    print(f"  OK OpenCV: {cv2.__version__}")
except ImportError as e:
    print(f"  FAIL: {e}")

# Test 2: MediaPipe
print("\n[TEST 2] Importing MediaPipe...")
try:
    import mediapipe as mp
    print(f"  OK MediaPipe: {mp.__version__}")
except ImportError as e:
    print(f"  FAIL: {e}")

# Test 3: numpy
print("\n[TEST 3] Creating test images...")
try:
    import numpy as np
    black_img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.imwrite("test_black.jpg", black_img)
    bright_img = np.ones((480, 640, 3), dtype=np.uint8) * 180
    cv2.imwrite("test_bright.jpg", bright_img)
    print("  OK test images created")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 4: MediaPipe new API (v0.10.x)
print("\n[TEST 4] MediaPipe FaceDetector (new v0.10 API)...")
try:
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    # Download model
    import urllib.request
    model_path = "blaze_face_short_range.tflite"
    if not os.path.exists(model_path):
        print("  Downloading face detection model...")
        url = (
            "https://storage.googleapis.com/mediapipe-models/"
            "face_detector/blaze_face_short_range/float16/1/"
            "blaze_face_short_range.tflite"
        )
        urllib.request.urlretrieve(url, model_path)
        print("  Model downloaded")

    img = cv2.imread("test_black.jpg")
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)

    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = mp_vision.FaceDetectorOptions(
        base_options=base_options,
        min_detection_confidence=0.6
    )
    with mp_vision.FaceDetector.create_from_options(options) as detector:
        result = detector.detect(mp_image)
        count  = len(result.detections)

    print(f"  Faces in BLACK image: {count}")
    if count == 0:
        print("  OK Correctly rejected black image")
    else:
        print(f"  WARN: Detected {count} faces in black image")

except Exception as e:
    print(f"  New API failed: {e}")
    print("  Trying legacy API...")
    try:
        img     = cv2.imread("test_black.jpg")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face    = mp.solutions.face_detection
        with face.FaceDetection(min_detection_confidence=0.6) as det:
            res   = det.process(img_rgb)
            count = len(res.detections) if res.detections else 0
        print(f"  Legacy API - faces in black image: {count}")
        if count == 0:
            print("  OK Legacy API works correctly")
    except Exception as e2:
        print(f"  Legacy API also failed: {e2}")

# Test 5: OpenCV quality
print("\n[TEST 5] OpenCV quality check on BLACK image...")
try:
    img        = cv2.imread("test_black.jpg")
    gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharpness  = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = gray.mean()
    print(f"  Sharpness : {sharpness:.2f} (threshold < 50)")
    print(f"  Brightness: {brightness:.2f} (threshold < 40)")
    if brightness < 40:
        print("  OK Correctly detected as TOO DARK")
    if sharpness < 50:
        print("  OK Correctly detected as TOO BLURRY")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 6: Check views.py
print("\n[TEST 6] Checking views.py...")
views_path = os.path.join("apps", "skin_analysis", "views.py")
if os.path.exists(views_path):
    try:
        with open(views_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "_validate_quality" in content:
            print("  OK _validate_quality found — new views.py is active")
        else:
            print("  FAIL _validate_quality NOT found — still old views.py!")
            print("  ACTION: Replace apps/skin_analysis/views.py with new file")
        if "_validate_face" in content:
            print("  OK _validate_face found")
        else:
            print("  FAIL _validate_face NOT found")
    except Exception as e:
        print(f"  Error reading: {e}")
else:
    print(f"  FAIL views.py not found at {views_path}")

# Cleanup
print("\n[CLEANUP]")
for f in ["test_black.jpg", "test_bright.jpg"]:
    if os.path.exists(f):
        os.remove(f)
        print(f"  Removed {f}")

print("\n" + "=" * 60)
print("DONE — share output above")
print("=" * 60)