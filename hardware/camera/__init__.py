"""
Camera and face authentication module.

Provides:
- FaceCamera: Webcam capture with face detection
- FaceAuthenticator: MobileFaceNet embedding extraction
"""

from hardware.camera.face_auth import FaceCamera, FaceAuthenticator, FaceDetectionError

__all__ = ["FaceCamera", "FaceAuthenticator", "FaceDetectionError"]
