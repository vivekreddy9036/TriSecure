"""
Camera hardware package.

Modules
-------
face_auth.py      Primary pipeline: FaceCamera (Haar Cascade) +
                  FaceAuthenticator (MobileFaceNet / pixel-based fallback).
                  This is what app.py uses — works on Windows, Mac & Pi.

camera_service.py Thin OpenCV wrapper for raw frame capture.

face_service.py   Alternative pipeline using the `face_recognition` (dlib)
                  library — 128-D embeddings, requires dlib wheel.
"""

from hardware.camera.face_auth      import FaceCamera, FaceAuthenticator, FaceDetectionError
from hardware.camera.camera_service import CameraService, CaptureResult
from hardware.camera.face_service   import FaceService, FaceDetectionResult, FaceEmbeddingResult, FaceComparisonResult

__all__ = [
    # Primary pipeline
    "FaceCamera",
    "FaceAuthenticator",
    "FaceDetectionError",
    # Raw capture
    "CameraService",
    "CaptureResult",
    # dlib alternative
    "FaceService",
    "FaceDetectionResult",
    "FaceEmbeddingResult",
    "FaceComparisonResult",
]
