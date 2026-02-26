"""
Face Recognition Service (dlib / face_recognition backend).

Used when the `face_recognition` Python library (dlib) is installed.
Generates 128-D embeddings instead of the 512-D MobileFaceNet ones.

Note:
  The primary production pipeline uses FaceCamera + FaceAuthenticator
  (hardware/camera/face_auth.py) which works without dlib.
  This service is kept as an alternative / fallback for systems where
  dlib wheels are available.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FaceDetectionResult:
    success: bool
    face_found: bool = False
    face_location: Optional[Tuple[int, int, int, int]] = None
    error_message: Optional[str] = None


@dataclass
class FaceEmbeddingResult:
    success: bool
    embedding: Optional[np.ndarray] = None
    error_message: Optional[str] = None


@dataclass
class FaceComparisonResult:
    success: bool
    confidence: float = 0.0
    match: bool = False
    error_message: Optional[str] = None


class FaceService:
    """
    Face recognition service backed by the `face_recognition` library (dlib).

    Falls back to simulation mode (random embeddings) when the library is
    not installed — useful for pipeline testing without dlib.

    Produces 128-D embedding vectors.  For the production 512-D MobileFaceNet
    pipeline see hardware/camera/face_auth.py (FaceAuthenticator).
    """

    DEFAULT_MODEL  = "hog"   # "hog" = fast CPU,  "cnn" = accurate GPU
    DEFAULT_JITTER = 1

    def __init__(self, model: str = DEFAULT_MODEL, jitter: int = DEFAULT_JITTER):
        self.model  = model
        self.jitter = jitter
        self._face_recognition = None
        self._initialized = False
        logger.info(f"FaceService initialized (model={model}, jitter={jitter})")

    def initialize(self) -> bool:
        try:
            import face_recognition
            self._face_recognition = face_recognition
            self._initialized = True
            logger.info("face_recognition (dlib) library loaded")
            return True
        except ImportError:
            logger.warning("face_recognition not installed — running in simulation mode.")
            self._initialized = False
            return False
        except Exception as e:
            logger.error(f"Face library initialization failed: {e}")
            self._initialized = False
            return False

    def detect_face(self, frame: np.ndarray) -> FaceDetectionResult:
        if not self._initialized or not self._face_recognition:
            h, w = frame.shape[:2]
            return FaceDetectionResult(
                success=True, face_found=True,
                face_location=(h // 4, w // 4, 3 * h // 4, 3 * w // 4)
            )
        try:
            rgb = frame[..., ::-1]
            locs = self._face_recognition.face_locations(rgb, model=self.model)
            if not locs:
                return FaceDetectionResult(success=True, face_found=False)
            top, right, bottom, left = locs[0]
            return FaceDetectionResult(success=True, face_found=True,
                                       face_location=(top, right, bottom, left))
        except Exception as e:
            return FaceDetectionResult(success=False, error_message=str(e))

    def generate_embedding(self, frame: np.ndarray) -> FaceEmbeddingResult:
        if not self._initialized or not self._face_recognition:
            return FaceEmbeddingResult(
                success=True,
                embedding=np.random.randn(128).astype(np.float32)
            )
        try:
            rgb  = frame[..., ::-1]
            locs = self._face_recognition.face_locations(rgb, model=self.model)
            if not locs:
                return FaceEmbeddingResult(success=False, error_message="No face detected")
            encs = self._face_recognition.face_encodings(rgb, locs, num_jitters=self.jitter)
            if not encs:
                return FaceEmbeddingResult(success=False, error_message="Embedding failed")
            return FaceEmbeddingResult(success=True,
                                       embedding=np.array(encs[0], dtype=np.float32))
        except Exception as e:
            return FaceEmbeddingResult(success=False, error_message=str(e))

    def compare_embeddings(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        tolerance: float = 0.6,
    ) -> FaceComparisonResult:
        if not self._initialized or not self._face_recognition:
            return FaceComparisonResult(success=True, confidence=1.0, match=True)
        try:
            if embedding1.shape != (128,) or embedding2.shape != (128,):
                return FaceComparisonResult(success=False,
                                            error_message="Invalid embedding dimensions")
            dist  = self._face_recognition.face_distance([embedding1], embedding2)[0]
            conf  = float(np.clip(1.0 - dist / 0.6, 0.0, 1.0))
            return FaceComparisonResult(success=True, confidence=conf, match=dist <= tolerance)
        except Exception as e:
            return FaceComparisonResult(success=False, error_message=str(e))

    def is_initialized(self) -> bool:
        return self._initialized
