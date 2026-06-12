"""
Presentation Attack Detection (PAD / Liveness Detection).

Uses SilentFace (MiniFASNet) ONNX model from:
  hardware/camera/silent_face/resources/anti_spoof_models/

Simulation mode (always returns is_live=True) when model file is missing,
so development and testing work on any machine without the model weights.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_SUBPATH = "hardware/camera/silent_face/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx"
_INPUT_SIZE = (80, 80)
_LIVE_CLASS = 1  # softmax index 1 = live


@dataclass
class PADResult:
    is_live: bool
    confidence: float        # live probability 0.0–1.0
    attack_type: Optional[str]  # None when live; "print" / "replay" / "unknown" when spoof
    latency_ms: float
    simulated: bool = False  # True when running without the ONNX model


class PADDetector:
    """
    Liveness detector wrapping SilentFace MiniFASNetV2 ONNX.

    Input : BGR uint8 face crop (any size — resized internally to 80×80).
    Output: PADResult with is_live, confidence, attack_type, latency_ms.

    Falls back to simulation mode (always live) when the ONNX model file is absent
    or onnxruntime is unavailable.
    """

    def __init__(self, threshold: float = 0.5, model_path: Optional[str] = None) -> None:
        self._threshold = threshold
        self._session = None
        self._simulated = False

        resolved_path = Path(model_path) if model_path else Path(_MODEL_SUBPATH)
        if not resolved_path.is_absolute():
            resolved_path = Path.cwd() / resolved_path

        if not resolved_path.exists():
            logger.warning(f"PAD model not found at {resolved_path} — running in simulation mode (always live)")
            self._simulated = True
            return

        try:
            import onnxruntime as ort  # type: ignore
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            self._session = ort.InferenceSession(str(resolved_path), sess_options=opts)
            self._input_name = self._session.get_inputs()[0].name
            logger.info(f"PADDetector initialized: {resolved_path.name}")
        except Exception as exc:
            logger.warning(f"Failed to load PAD model ({exc}) — simulation mode")
            self._simulated = True

    def detect(self, face_image: np.ndarray) -> PADResult:
        """
        Classify face_image as live or spoof.

        Args:
            face_image: BGR uint8 ndarray (any spatial size, ≥3 channels).

        Returns:
            PADResult with is_live, confidence, attack_type, latency_ms.
        """
        t0 = time.perf_counter()

        if self._simulated or self._session is None:
            latency = (time.perf_counter() - t0) * 1000
            return PADResult(is_live=True, confidence=1.0, attack_type=None,
                             latency_ms=latency, simulated=True)

        try:
            blob = self._preprocess(face_image)
            outputs = self._session.run(None, {self._input_name: blob})
            probs = _softmax(outputs[0][0])
            live_prob = float(probs[_LIVE_CLASS])
            is_live = live_prob >= self._threshold
            attack_type = None if is_live else _classify_attack(probs)
            latency = (time.perf_counter() - t0) * 1000
            return PADResult(is_live=is_live, confidence=live_prob,
                             attack_type=attack_type, latency_ms=latency)
        except Exception as exc:
            logger.error(f"PAD inference error: {exc}")
            latency = (time.perf_counter() - t0) * 1000
            return PADResult(is_live=True, confidence=0.5, attack_type=None,
                             latency_ms=latency, simulated=True)

    @staticmethod
    def _preprocess(img: np.ndarray) -> np.ndarray:
        try:
            import cv2  # type: ignore
            resized = cv2.resize(img, _INPUT_SIZE)
        except ImportError:
            # Fallback: simple nearest-neighbour resize via numpy
            h, w = img.shape[:2]
            y = (np.arange(_INPUT_SIZE[1]) * h / _INPUT_SIZE[1]).astype(int)
            x = (np.arange(_INPUT_SIZE[0]) * w / _INPUT_SIZE[0]).astype(int)
            resized = img[np.ix_(y, x)]

        # Normalize to [-1, 1] and convert HWC→NCHW float32
        arr = resized.astype(np.float32) / 127.5 - 1.0
        arr = arr.transpose(2, 0, 1)[np.newaxis, ...]
        return arr


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / e.sum()


def _classify_attack(probs: np.ndarray) -> str:
    # SilentFace: class 0 = spoof (paper does not sub-classify attack type)
    return "spoof"
