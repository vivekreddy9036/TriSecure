"""
Camera Service — USB/laptop webcam abstraction.

Wraps OpenCV VideoCapture for consistent frame capture across platforms.
On Raspberry Pi the device is typically /dev/video0; on Windows/Mac it is
accessed by integer index (0 = default webcam).
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CaptureResult:
    """Result of a single frame capture."""
    success: bool
    frame: Optional[np.ndarray] = None   # BGR, HxWx3
    error_message: Optional[str] = None


class CameraService:
    """
    Lightweight OpenCV camera wrapper.

    Handles device open/close and provides single-frame capture.
    Optimised for Raspberry Pi 4:
    - 320×240 default resolution (lower USB bandwidth)
    - MJPEG codec (skip slow YUYV→BGR conversion)
    - Buffer flushing for fresh frames
    """

    DEFAULT_DEVICE = 0          # 0 = default webcam (works on all platforms)
    DEFAULT_WIDTH  = 320
    DEFAULT_HEIGHT = 240
    DEFAULT_FPS    = 15
    BUFFER_FLUSH   = 3          # grab() calls before read() to flush stale frames

    def __init__(
        self,
        device=None,
        width:  int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps:    int = DEFAULT_FPS,
    ):
        self.device = device if device is not None else self.DEFAULT_DEVICE
        self.width  = width
        self.height = height
        self.fps    = fps

        self._cap         = None
        self._initialized = False

        logger.info(f"CameraService created (device={self.device}, {width}x{height}@{fps}fps)")

    def initialize(self) -> bool:
        """Open camera. Returns True on success."""
        try:
            import cv2
            self._cap = cv2.VideoCapture(self.device)
            if not self._cap.isOpened():
                logger.error(f"Failed to open camera device: {self.device}")
                return False

            # Request MJPEG codec (avoids slow YUYV→BGR on Pi)
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            self._cap.set(cv2.CAP_PROP_FOURCC, fourcc)

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS,          self.fps)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

            aw = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ah = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            af = int(self._cap.get(cv2.CAP_PROP_FPS))
            logger.info(f"Camera initialized: {aw}x{ah}@{af}fps")
            self._initialized = True
            return True

        except ImportError:
            logger.warning("OpenCV not installed. Camera in simulation mode.")
            return False
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            return False

    def capture_frame(self) -> CaptureResult:
        """Capture one frame. Returns a blank frame if camera not initialised."""
        if not self._initialized or not self._cap:
            logger.warning("Camera not initialized — returning blank frame.")
            return CaptureResult(
                success=True,
                frame=np.zeros((self.height, self.width, 3), dtype=np.uint8)
            )
        try:
            # Flush stale frames from kernel buffer
            for _ in range(self.BUFFER_FLUSH):
                self._cap.grab()

            ret, frame = self._cap.read()
            if not ret or frame is None:
                return CaptureResult(success=False, error_message="Failed to capture frame")
            return CaptureResult(success=True, frame=frame)
        except Exception as e:
            return CaptureResult(success=False, error_message=f"Capture failed: {e}")

    def capture_frame_for_embedding(self) -> Optional[np.ndarray]:
        """Convenience method — returns raw frame or None."""
        result = self.capture_frame()
        return result.frame if result.success else None

    def is_initialized(self) -> bool:
        return self._initialized

    def close(self) -> None:
        if self._cap:
            try:
                self._cap.release()
                self._initialized = False
                logger.info("Camera closed")
            except Exception as e:
                logger.error(f"Error closing camera: {e}")
