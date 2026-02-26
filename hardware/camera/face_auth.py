"""
Face Authentication Module.

Handles camera capture, face detection using Haar Cascade,
and embedding generation using MobileFaceNet.

This module is part of the hardware layer and contains:
- FaceCamera: Webcam capture and face detection
- FaceAuthenticator: Embedding extraction using MobileFaceNet

Design:
- Singleton pattern for Haar Cascade classifier
- CPU-only inference for Raspberry Pi compatibility
- No database or blockchain logic (clean architecture)
"""

import logging
import gc
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
from threading import Lock

import numpy as np

logger = logging.getLogger(__name__)


class FaceDetectionError(Exception):
    """Raised when face detection fails."""
    pass


@dataclass
class FaceDetectionResult:
    """Result of face detection operation."""
    success: bool
    face_image: Optional[np.ndarray] = None
    face_location: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    error_message: Optional[str] = None


@dataclass
class EmbeddingResult:
    """Result of embedding extraction."""
    success: bool
    embedding: Optional[np.ndarray] = None
    error_message: Optional[str] = None


class HaarCascadeLoader:
    """
    Singleton loader for Haar Cascade classifier.
    
    Ensures classifier is loaded only once to save memory
    and improve performance on Raspberry Pi.
    """
    
    _instance = None
    _lock = Lock()
    _classifier = None
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_classifier(self):
        """
        Get or load Haar Cascade classifier.
        
        Returns:
            cv2.CascadeClassifier: Loaded classifier
            
        Raises:
            RuntimeError: If classifier cannot be loaded
        """
        if self._classifier is None:
            with self._lock:
                if self._classifier is None:
                    self._load_classifier()
        return self._classifier
    
    def _load_classifier(self):
        """Load Haar Cascade from OpenCV data directory."""
        try:
            import cv2
            
            # OpenCV's default Haar Cascade path
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            
            if not Path(cascade_path).exists():
                raise RuntimeError(f"Haar Cascade not found: {cascade_path}")
            
            self._classifier = cv2.CascadeClassifier(cascade_path)
            
            if self._classifier.empty():
                raise RuntimeError("Failed to load Haar Cascade classifier")
            
            logger.info(f"Haar Cascade loaded: {cascade_path}")
            
        except ImportError:
            raise RuntimeError("OpenCV not installed. Run: pip install opencv-python")


class FaceCamera:
    """
    Camera capture and face detection class.
    
    Responsibilities:
    - Capture frames from webcam
    - Detect faces using Haar Cascade
    - Crop and resize detected faces to 112x112
    - Securely clear frames from memory
    
    Usage:
        camera = FaceCamera(device=0)
        camera.initialize()
        result = camera.capture_and_detect()
        if result.success:
            face_image = result.face_image  # 112x112 cropped face
        camera.release()
    """
    
    # Standard input size for MobileFaceNet
    FACE_SIZE = (112, 112)
    
    def __init__(
        self,
        device: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30
    ):
        """
        Initialize face camera.
        
        Args:
            device: Camera device index (0 for default webcam)
            width: Capture width in pixels
            height: Capture height in pixels
            fps: Target frames per second
        """
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        
        self._cap = None
        self._initialized = False
        self._cascade_loader = HaarCascadeLoader()
        
        logger.debug(f"FaceCamera created: device={device}, {width}x{height}@{fps}fps")
    
    def initialize(self) -> bool:
        """
        Initialize camera and load classifier.
        
        Returns:
            True if initialization successful
            
        Raises:
            RuntimeError: If camera or classifier cannot be initialized
        """
        try:
            import cv2
            
            # Load Haar Cascade classifier (singleton)
            self._cascade_loader.get_classifier()
            
            # Open camera device
            self._cap = cv2.VideoCapture(self.device)
            
            if not self._cap.isOpened():
                raise RuntimeError(f"Cannot open camera device: {self.device}")
            
            # Configure camera settings
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Verify settings
            actual_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info(f"Camera initialized: {actual_width}x{actual_height}")
            self._initialized = True
            return True
            
        except ImportError:
            raise RuntimeError("OpenCV not installed. Run: pip install opencv-python")
        
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            raise RuntimeError(f"Camera initialization failed: {e}")
    
    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame from camera.
        
        Returns:
            BGR frame as numpy array, or None on failure
        """
        if not self._initialized or self._cap is None:
            logger.error("Camera not initialized")
            return None
        
        try:
            ret, frame = self._cap.read()
            
            if not ret or frame is None:
                logger.error("Failed to capture frame")
                return None
            
            return frame
            
        except Exception as e:
            logger.error(f"Frame capture error: {e}")
            return None
    
    def detect_face(self, frame: np.ndarray) -> FaceDetectionResult:
        """
        Detect face in frame using Haar Cascade.
        
        Args:
            frame: BGR image as numpy array
            
        Returns:
            FaceDetectionResult with cropped face or error
        """
        try:
            import cv2
            
            classifier = self._cascade_loader.get_classifier()
            
            # Step 1: Convert to grayscale for detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Step 2: Detect faces
            # Parameters tuned for Raspberry Pi performance
            faces = classifier.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(60, 60),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            
            if len(faces) == 0:
                return FaceDetectionResult(
                    success=False,
                    error_message="No face detected in frame"
                )
            
            # Step 3: Select largest face (closest to camera)
            largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
            x, y, w, h = largest_face
            
            # Step 4: Add margin for better face capture
            margin = int(min(w, h) * 0.2)
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(frame.shape[1], x + w + margin)
            y2 = min(frame.shape[0], y + h + margin)
            
            # Step 5: Crop face region
            face_crop = frame[y1:y2, x1:x2].copy()
            
            # Step 6: Resize to 112x112 (MobileFaceNet input size)
            face_resized = cv2.resize(face_crop, self.FACE_SIZE, interpolation=cv2.INTER_AREA)
            
            logger.debug(f"Face detected: ({x}, {y}, {w}, {h}), resized to {self.FACE_SIZE}")
            
            return FaceDetectionResult(
                success=True,
                face_image=face_resized,
                face_location=(x, y, w, h)
            )
            
        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return FaceDetectionResult(
                success=False,
                error_message=f"Detection failed: {e}"
            )
    
    def capture_and_detect(self) -> FaceDetectionResult:
        """
        Capture frame and detect face in one operation.
        
        Returns:
            FaceDetectionResult with cropped face or error
        """
        frame = self.capture_frame()
        
        if frame is None:
            return FaceDetectionResult(
                success=False,
                error_message="Failed to capture frame"
            )
        
        result = self.detect_face(frame)
        
        # Securely clear raw frame from memory
        self._clear_frame(frame)
        
        return result
    
    def _clear_frame(self, frame: np.ndarray) -> None:
        """
        Securely clear frame data from memory.
        
        Overwrites frame data before deletion for security.
        """
        if frame is not None:
            try:
                # Overwrite with zeros before deletion
                frame.fill(0)
                del frame
                gc.collect()
            except Exception:
                pass
    
    def release(self) -> None:
        """Release camera resources."""
        if self._cap is not None:
            try:
                self._cap.release()
                logger.info("Camera released")
            except Exception as e:
                logger.warning(f"Error releasing camera: {e}")
            finally:
                self._cap = None
                self._initialized = False
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False


class FaceAuthenticator:
    """
    Face embedding extraction using MobileFaceNet.
    
    Responsibilities:
    - Load MobileFaceNet model (once at startup)
    - Preprocess face images
    - Generate normalized 512-D embeddings
    - Compare embeddings using cosine similarity
    
    Model Architecture:
    - MobileFaceNet: Lightweight CNN for face recognition
    - Input: 112x112 RGB image
    - Output: 512-D normalized embedding vector
    - Optimized for CPU inference on Raspberry Pi
    
    Usage:
        auth = FaceAuthenticator()
        auth.initialize()
        
        # Generate embedding
        embedding = auth.extract_embedding(face_image)
        
        # Compare embeddings
        similarity = auth.compare_embeddings(emb1, emb2)
        if similarity > 0.5:
            print("Face verified!")
    """
    
    # Embedding dimension
    EMBEDDING_SIZE = 512
    
    # Default similarity threshold
    DEFAULT_THRESHOLD = 0.55
    
    def __init__(self, model_path: Optional[str] = None, threshold: float = DEFAULT_THRESHOLD):
        """
        Initialize face authenticator.
        
        Args:
            model_path: Path to MobileFaceNet ONNX model (optional)
            threshold: Similarity threshold for verification (0.5-0.6 recommended)
        """
        self.model_path = model_path
        self.threshold = threshold
        
        self._model = None
        self._initialized = False
        self._simulation_mode = False
        
        logger.debug(f"FaceAuthenticator created: threshold={threshold}")
    
    def initialize(self) -> bool:
        """
        Initialize MobileFaceNet model.
        
        Loads ONNX model for CPU inference.
        Falls back to simulation mode if model unavailable.
        
        Returns:
            True if initialization successful
        """
        try:
            import onnxruntime as ort
            
            # Set ONNX Runtime to CPU-only mode
            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 2  # Optimize for Raspberry Pi
            sess_options.inter_op_num_threads = 2
            
            # Find model path
            model_path = self._find_model_path()
            
            if model_path is None:
                logger.warning("MobileFaceNet model not found. Running in simulation mode.")
                self._simulation_mode = True
                self._initialized = True
                return True
            
            # Load ONNX model
            self._model = ort.InferenceSession(
                str(model_path),
                sess_options=sess_options,
                providers=['CPUExecutionProvider']
            )
            
            # Get model input/output info
            input_info = self._model.get_inputs()[0]
            output_info = self._model.get_outputs()[0]
            
            logger.info(f"MobileFaceNet loaded: input={input_info.shape}, output={output_info.shape}")
            
            self._initialized = True
            return True
            
        except ImportError:
            logger.warning("ONNX Runtime not installed. Running in simulation mode.")
            logger.info("To enable face recognition: pip install onnxruntime")
            self._simulation_mode = True
            self._initialized = True
            return True
        
        except Exception as e:
            logger.error(f"Model initialization failed: {e}")
            self._simulation_mode = True
            self._initialized = True
            return True
    
    def _find_model_path(self) -> Optional[Path]:
        """
        Find MobileFaceNet model file.
        
        Search order:
        1. Explicit model_path
        2. Current directory
        3. models/ directory
        4. ~/.trisecure/models/
        
        Returns:
            Path to model file or None if not found
        """
        model_names = [
            "mobilefacenet.onnx",
            "MobileFaceNet.onnx",
            "mobilefacenet_v2.onnx"
        ]
        
        search_paths = [
            Path.cwd(),
            Path.cwd() / "models",
            Path.cwd() / "hardware" / "camera" / "models",
            Path.home() / ".trisecure" / "models",
            Path("/opt/trisecure/models")
        ]
        
        # Check explicit path first
        if self.model_path:
            path = Path(self.model_path)
            if path.exists():
                return path
        
        # Search in standard locations
        for search_path in search_paths:
            for model_name in model_names:
                model_file = search_path / model_name
                if model_file.exists():
                    logger.debug(f"Found model: {model_file}")
                    return model_file
        
        return None
    
    def extract_embedding(self, face_image: np.ndarray) -> EmbeddingResult:
        """
        Extract face embedding from cropped face image.
        
        Args:
            face_image: 112x112 BGR face image
            
        Returns:
            EmbeddingResult with normalized 512-D embedding
        """
        if not self._initialized:
            return EmbeddingResult(
                success=False,
                error_message="Authenticator not initialized"
            )
        
        # Simulation mode: return random embedding
        if self._simulation_mode:
            logger.debug("Simulation mode: generating random embedding")
            # Generate deterministic embedding based on image hash for testing
            embedding = self._generate_simulation_embedding(face_image)
            return EmbeddingResult(success=True, embedding=embedding)
        
        try:
            # Step 1: Preprocess image
            preprocessed = self._preprocess_image(face_image)
            
            # Step 2: Run inference
            input_name = self._model.get_inputs()[0].name
            output_name = self._model.get_outputs()[0].name
            
            outputs = self._model.run(
                [output_name],
                {input_name: preprocessed}
            )
            
            embedding = outputs[0].flatten()
            
            # Step 3: Normalize embedding (L2 normalization)
            embedding = self._normalize_embedding(embedding)
            
            logger.debug(f"Embedding extracted: shape={embedding.shape}")
            
            return EmbeddingResult(success=True, embedding=embedding)
            
        except Exception as e:
            logger.error(f"Embedding extraction failed: {e}")
            return EmbeddingResult(
                success=False,
                error_message=f"Embedding extraction failed: {e}"
            )
    
    def _preprocess_image(self, face_image: np.ndarray) -> np.ndarray:
        """
        Preprocess face image for MobileFaceNet.
        
        Args:
            face_image: 112x112 BGR image
            
        Returns:
            Preprocessed image tensor [1, 3, 112, 112]
        """
        import cv2
        
        # Ensure correct size
        if face_image.shape[:2] != (112, 112):
            face_image = cv2.resize(face_image, (112, 112))
        
        # Convert BGR to RGB
        rgb_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
        
        # Normalize to [-1, 1] (standard for face models)
        normalized = (rgb_image.astype(np.float32) - 127.5) / 127.5
        
        # Transpose to channel-first format [C, H, W]
        transposed = np.transpose(normalized, (2, 0, 1))
        
        # Add batch dimension [1, C, H, W]
        batched = np.expand_dims(transposed, axis=0)
        
        return batched.astype(np.float32)
    
    def _normalize_embedding(self, embedding: np.ndarray) -> np.ndarray:
        """
        L2 normalize embedding vector.
        
        Args:
            embedding: Raw embedding vector
            
        Returns:
            L2 normalized embedding
        """
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return embedding
        return (embedding / norm).astype(np.float32)
    
    def _generate_simulation_embedding(self, face_image: np.ndarray) -> np.ndarray:
        """
        Generate deterministic simulation embedding for testing.
        
        Uses image hash for reproducibility.
        """
        # Create seed from image hash
        image_hash = hash(face_image.tobytes()) % (2**32)
        rng = np.random.RandomState(image_hash)
        
        # Generate and normalize random embedding
        embedding = rng.randn(self.EMBEDDING_SIZE).astype(np.float32)
        return self._normalize_embedding(embedding)
    
    @staticmethod
    def cosine_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector (normalized)
            embedding2: Second embedding vector (normalized)
            
        Returns:
            Cosine similarity score (-1 to 1, higher = more similar)
        """
        # Ensure 1-D arrays
        e1 = embedding1.flatten()
        e2 = embedding2.flatten()
        
        # For normalized vectors, cosine similarity = dot product
        dot_product = np.dot(e1, e2)
        
        # Clip to valid range (handle floating point errors)
        similarity = float(np.clip(dot_product, -1.0, 1.0))
        
        return similarity
    
    def compare_embeddings(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        threshold: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        Compare two embeddings for verification.
        
        Args:
            embedding1: First face embedding
            embedding2: Second face embedding
            threshold: Similarity threshold (uses default if not provided)
            
        Returns:
            Tuple of (is_match, similarity_score)
        """
        threshold = threshold or self.threshold
        
        similarity = self.cosine_similarity(embedding1, embedding2)
        is_match = similarity >= threshold
        
        logger.debug(f"Embedding comparison: similarity={similarity:.4f}, threshold={threshold}, match={is_match}")
        
        return is_match, similarity
    
    def verify_face(
        self,
        live_embedding: np.ndarray,
        stored_embedding: np.ndarray,
        threshold: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        Verify live face against stored template.
        
        Args:
            live_embedding: Embedding from live capture
            stored_embedding: Stored template embedding
            threshold: Verification threshold
            
        Returns:
            Tuple of (verified, similarity_score)
        """
        return self.compare_embeddings(live_embedding, stored_embedding, threshold)
    
    def release(self) -> None:
        """Release model resources."""
        if self._model is not None:
            self._model = None
            gc.collect()
            logger.info("FaceAuthenticator resources released")
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False


def capture_live_face(camera: FaceCamera) -> Optional[np.ndarray]:
    """
    Convenience function to capture face from camera.
    
    Args:
        camera: Initialized FaceCamera instance
        
    Returns:
        112x112 face image or None on failure
    """
    result = camera.capture_and_detect()
    
    if not result.success:
        logger.error(f"Face capture failed: {result.error_message}")
        return None
    
    return result.face_image


def extract_embedding(
    authenticator: FaceAuthenticator,
    face_image: np.ndarray
) -> Optional[np.ndarray]:
    """
    Convenience function to extract embedding from face image.
    
    Args:
        authenticator: Initialized FaceAuthenticator instance
        face_image: 112x112 face image
        
    Returns:
        Normalized embedding vector or None on failure
    """
    result = authenticator.extract_embedding(face_image)
    
    if not result.success:
        logger.error(f"Embedding extraction failed: {result.error_message}")
        return None
    
    return result.embedding
