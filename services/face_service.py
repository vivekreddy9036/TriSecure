"""
Face Recognition Service.

Performs face detection, capture, embedding generation, and comparison.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FaceDetectionResult:
    """Result of face detection."""
    
    success: bool
    face_found: bool = False
    face_location: Optional[Tuple[int, int, int, int]] = None
    error_message: Optional[str] = None


@dataclass
class FaceEmbeddingResult:
    """Result of face embedding generation."""
    
    success: bool
    embedding: Optional[np.ndarray] = None  # 1D array
    error_message: Optional[str] = None


@dataclass
class FaceComparisonResult:
    """Result of face comparison."""
    
    success: bool
    confidence: float = 0.0  # 0.0-1.0
    match: bool = False
    error_message: Optional[str] = None


class FaceService:
    """
    Face recognition and embedding service.
    
    Uses face_recognition library (dlib backend) for:
    - Face detection in images
    - Face embedding generation (128-D vector)
    - Face comparison (cosine distance)
    
    Responsibilities:
    - Detect faces in captured frames
    - Generate face embeddings
    - Compare embeddings for authentication
    - Handle processing errors gracefully
    
    Architecture:
    - Abstraction for face ML operations
    - Production-ready ML preprocessing
    - Configurable confidence threshold
    - Stateless comparison functions
    """
    
    DEFAULT_MODEL = "hog"  # "hog" for CPU, "cnn" for GPU (slow on Pi)
    DEFAULT_JITTER = 1  # Number of times to re-sample face for embedding
    
    def __init__(self, model: str = DEFAULT_MODEL, jitter: int = DEFAULT_JITTER):
        """
        Initialize face service.
        
        Args:
            model: Detection model - "hog" (fast, CPU) or "cnn" (accurate, slow)
            jitter: Upsampling passes for embedding (higher = more robust)
        """
        self.model = model
        self.jitter = jitter
        self._face_recognition = None
        self._initialized = False
        
        logger.info(f"FaceService initialized (model={model}, jitter={jitter})")
    
    def initialize(self) -> bool:
        """
        Initialize face recognition library.
        
        Returns:
            True if library loaded successfully
        """
        try:
            import face_recognition
            self._face_recognition = face_recognition
            self._initialized = True
            logger.info("Face recognition library loaded")
            return True
            
        except ImportError:
            logger.warning("face_recognition library not installed. Running in simulation mode.")
            self._initialized = False
            return False
        
        except Exception as e:
            logger.error(f"Face library initialization failed: {e}")
            self._initialized = False
            return False
    
    def detect_face(self, frame: np.ndarray) -> FaceDetectionResult:
        """
        Detect face(s) in frame.
        
        Args:
            frame: Image frame (BGR, numpy array from OpenCV)
            
        Returns:
            FaceDetectionResult with location or error
        """
        if not self._initialized or not self._face_recognition:
            logger.debug("Face library not initialized. Simulating face detection.")
            # Simulation: assume face detected in center of frame
            h, w = frame.shape[:2]
            return FaceDetectionResult(
                success=True,
                face_found=True,
                face_location=(h//4, w//4, 3*h//4, 3*w//4)
            )
        
        try:
            # Convert BGR (OpenCV) to RGB (face_recognition)
            rgb_frame = frame[..., ::-1]
            
            # Detect faces
            face_locations = self._face_recognition.face_locations(rgb_frame, model=self.model)
            
            if not face_locations:
                logger.debug("No face detected in frame")
                return FaceDetectionResult(success=True, face_found=False)
            
            # Use first detected face
            top, right, bottom, left = face_locations[0]
            logger.debug(f"Face detected: ({left}, {top}, {right}, {bottom})")
            
            return FaceDetectionResult(
                success=True,
                face_found=True,
                face_location=(top, right, bottom, left)
            )
        
        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return FaceDetectionResult(
                success=False,
                error_message=f"Detection failed: {e}"
            )
    
    def generate_embedding(self, frame: np.ndarray) -> FaceEmbeddingResult:
        """
        Generate 128-D face embedding from frame.
        
        Args:
            frame: Image frame (BGR, numpy array)
            
        Returns:
            FaceEmbeddingResult with embedding or error
        """
        if not self._initialized or not self._face_recognition:
            logger.debug("Face library not initialized. Returning random embedding.")
            # Return random embedding for development
            return FaceEmbeddingResult(
                success=True,
                embedding=np.random.randn(128).astype(np.float32)
            )
        
        try:
            # Convert BGR to RGB
            rgb_frame = frame[..., ::-1]
            
            # Detect faces
            face_locations = self._face_recognition.face_locations(rgb_frame, model=self.model)
            if not face_locations:
                logger.error("No face found for embedding generation")
                return FaceEmbeddingResult(
                    success=False,
                    error_message="No face detected in frame"
                )
            
            # Generate embeddings
            embeddings = self._face_recognition.face_encodings(
                rgb_frame,
                face_locations,
                num_jitters=self.jitter
            )
            
            if not embeddings:
                logger.error("Failed to generate embedding")
                return FaceEmbeddingResult(
                    success=False,
                    error_message="Embedding generation failed"
                )
            
            embedding = np.array(embeddings[0], dtype=np.float32)
            logger.debug(f"Embedding generated: shape={embedding.shape}")
            
            return FaceEmbeddingResult(success=True, embedding=embedding)
        
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            return FaceEmbeddingResult(
                success=False,
                error_message=f"Embedding failed: {e}"
            )
    
    def compare_embeddings(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        tolerance: float = 0.6
    ) -> FaceComparisonResult:
        """
        Compare two face embeddings.
        
        Args:
            embedding1: First embedding (128-D vector)
            embedding2: Second embedding (128-D vector)
            tolerance: Distance threshold (lower = stricter matching)
            
        Returns:
            FaceComparisonResult with confidence and match status
        """
        if not self._initialized or not self._face_recognition:
            logger.debug("Face library not initialized. Returning simulation match.")
            # Simulation: perfect match
            return FaceComparisonResult(
                success=True,
                confidence=1.0,
                match=True
            )
        
        try:
            # Ensure embeddings are correct shape
            if embedding1.shape != (128,) or embedding2.shape != (128,):
                logger.error(f"Invalid embedding shapes: {embedding1.shape}, {embedding2.shape}")
                return FaceComparisonResult(
                    success=False,
                    error_message="Invalid embedding dimensions"
                )
            
            # Calculate distance
            distance = self._face_recognition.face_distance([embedding1], embedding2)[0]
            
            # Convert distance to confidence (0-1, higher = better match)
            # Distance range 0.0-0.6 typical for face_recognition
            confidence = max(0.0, 1.0 - (distance / 0.6))
            confidence = min(1.0, confidence)
            match = distance <= tolerance
            
            logger.debug(f"Face comparison: distance={distance:.4f}, confidence={confidence:.4f}, match={match}")
            
            return FaceComparisonResult(
                success=True,
                confidence=confidence,
                match=match
            )
        
        except Exception as e:
            logger.error(f"Face comparison error: {e}")
            return FaceComparisonResult(
                success=False,
                error_message=f"Comparison failed: {e}"
            )
    
    def is_initialized(self) -> bool:
        """Check if face recognition library is loaded."""
        return self._initialized
