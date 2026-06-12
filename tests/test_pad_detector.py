"""Tests for PADDetector (simulation mode — no ONNX model required)."""
import numpy as np
import pytest
from hardware.camera.pad_detector import PADDetector, PADResult


@pytest.fixture
def pad():
    return PADDetector(threshold=0.5)


def test_simulation_mode_returns_live(pad):
    face = np.zeros((112, 112, 3), dtype=np.uint8)
    result = pad.detect(face)
    assert result.simulated
    assert result.is_live
    assert result.confidence == 1.0


def test_result_has_latency(pad):
    face = np.zeros((112, 112, 3), dtype=np.uint8)
    result = pad.detect(face)
    assert result.latency_ms >= 0.0


def test_pad_result_fields(pad):
    face = np.random.randint(0, 255, (80, 80, 3), dtype=np.uint8)
    result = pad.detect(face)
    assert isinstance(result, PADResult)
    assert isinstance(result.is_live, bool)
    assert 0.0 <= result.confidence <= 1.0


def test_preprocess_output_shape():
    img = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    blob = PADDetector._preprocess(img)
    assert blob.shape == (1, 3, 80, 80)
    assert blob.dtype == np.float32
    assert blob.min() >= -1.0 and blob.max() <= 1.0
