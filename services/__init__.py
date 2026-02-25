"""
Services package.

Hardware abstraction layer for NFC, Camera, and Face Recognition.
"""

from .nfc_service import NFCService, NFCReadResult
from .camera_service import CameraService, CaptureResult
from .face_service import FaceService, FaceDetectionResult, FaceEmbeddingResult, FaceComparisonResult

__all__ = [
    'NFCService',
    'NFCReadResult',
    'CameraService',
    'CaptureResult',
    'FaceService',
    'FaceDetectionResult',
    'FaceEmbeddingResult',
    'FaceComparisonResult',
]
