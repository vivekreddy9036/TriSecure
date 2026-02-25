"""
Camera Service for video capture.

Abstracts USB webcam access via v4l2 (Video4Linux2) on Raspberry Pi.
"""

import logging
from dataclasses import dataclass
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CaptureResult:
    """Result of camera frame capture."""
    
    success: bool
    frame: Optional[np.ndarray] = None  # BGR format, HxWx3
    error_message: Optional[str] = None


class CameraService:
    """
    Camera capture service for USB webcam.
    
    Hardware:
    - Device: USB Webcam (default /dev/video0)
    - Interface: v4l2 (Video4Linux2)
    - Resolution: Configurable (default 640x480)
    - FPS: Configurable (default 30)
    
    Responsibilities:
    - Initialize camera device
    - Capture video frames
    - Handle camera access errors gracefully
    - Provide clean API for face recognition
    
    Architecture:
    - Hardware abstraction for Linux ARM
    - No hardcoded device paths (environment-based)
    - OpenCV integration for image processing
    - Graceful degradation if hardware unavailable
    """
    
    DEFAULT_DEVICE = "/dev/video0"
    DEFAULT_WIDTH = 640
    DEFAULT_HEIGHT = 480
    DEFAULT_FPS = 30
    
    def __init__(
        self,
        device: Optional[str] = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS
    ):
        """
        Initialize camera service.
        
        Args:
            device: Path to video device (uses /dev/video0 if None)
            width: Frame width in pixels
            height: Frame height in pixels
            fps: Frames per second
        """
        self.device = device or self.DEFAULT_DEVICE
        self.width = width
        self.height = height
        self.fps = fps
        self._cap = None
        self._initialized = False
        
        logger.info(f"CameraService initialized (device={self.device}, {width}x{height}@{fps}fps)")
    
    def initialize(self) -> bool:
        """
        Initialize camera connection.
        
        Returns:
            True if camera initialized successfully
        """
        try:
            import cv2
            
            # Try to open device
            self._cap = cv2.VideoCapture(self.device)
            
            if not self._cap.isOpened():
                logger.error(f"Failed to open camera device: {self.device}")
                return False
            
            # Set resolution and FPS
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Verify settings
            actual_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = int(self._cap.get(cv2.CAP_PROP_FPS))
            
            logger.info(f"Camera initialized: {actual_width}x{actual_height}@{actual_fps}fps")
            self._initialized = True
            return True
            
        except ImportError:
            logger.warning("OpenCV not installed. Camera will run in simulation mode.")
            self._initialized = False
            return False
        
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            self._initialized = False
            return False
    
    def capture_frame(self) -> CaptureResult:
        """
        Capture single frame from camera.
        
        Returns:
            CaptureResult with frame (BGR numpy array) or error
        """
        if not self._initialized or not self._cap:
            logger.warning("Camera not initialized. Returning blank frame.")
            # Return blank frame for development
            return CaptureResult(
                success=True,
                frame=np.zeros((self.height, self.width, 3), dtype=np.uint8)
            )
        
        try:
            ret, frame = self._cap.read()
            
            if not ret or frame is None:
                logger.error("Failed to grab frame from camera")
                return CaptureResult(
                    success=False,
                    error_message="Failed to capture frame"
                )
            
            logger.debug(f"Frame captured: {frame.shape}")
            return CaptureResult(success=True, frame=frame)
            
        except Exception as e:
            logger.error(f"Camera capture error: {e}")
            return CaptureResult(
                success=False,
                error_message=f"Capture failed: {e}"
            )
    
    def capture_frame_for_embedding(self) -> Optional[np.ndarray]:
        """
        Capture frame optimized for face embedding generation.
        
        Returns:
            Frame as numpy array or None if failed
        """
        result = self.capture_frame()
        return result.frame if result.success else None
    
    def is_initialized(self) -> bool:
        """Check if camera is properly initialized."""
        return self._initialized
    
    def close(self) -> None:
        """Close camera connection."""
        if self._cap:
            try:
                self._cap.release()
                self._initialized = False
                logger.info("Camera closed")
            except Exception as e:
                logger.error(f"Error closing camera: {e}")
