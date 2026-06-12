"""Tests for BayesianFusionVerifier."""
import numpy as np
import pytest
from core.biometric_fusion import BayesianFusionVerifier, FusionResult


def test_genuine_face_and_nfc_accepted():
    fv = BayesianFusionVerifier()
    result = fv.verify(face_score=0.80, nfc_match=True)
    assert result.accept
    assert result.log_lr > 0


def test_impostor_face_rejected():
    fv = BayesianFusionVerifier()
    result = fv.verify(face_score=0.20, nfc_match=True)
    assert not result.accept
    assert result.log_lr < 0


def test_nfc_miss_lowers_lr():
    fv = BayesianFusionVerifier()
    lr_with_nfc = fv.compute_lr(0.70, nfc_match=True)
    lr_without_nfc = fv.compute_lr(0.70, nfc_match=False)
    assert lr_with_nfc > lr_without_nfc


def test_fit_updates_parameters():
    fv = BayesianFusionVerifier()
    genuine = np.random.normal(0.72, 0.08, 300)
    impostor = np.random.normal(0.28, 0.12, 300)
    fv.fit(genuine, impostor)
    assert abs(fv._mu_g - 0.72) < 0.05
    assert abs(fv._mu_i - 0.28) < 0.05


def test_far_frr_shape():
    fv = BayesianFusionVerifier()
    gen = np.random.normal(0.72, 0.08, 200)
    imp = np.random.normal(0.28, 0.12, 200)
    far, frr, tar = fv.compute_far_frr(gen, imp, n_thresholds=50)
    assert len(far) == len(frr) == len(tar) == 50


def test_fusion_result_fields():
    fv = BayesianFusionVerifier()
    r = fv.verify(0.65, True)
    assert isinstance(r, FusionResult)
    assert r.face_score == 0.65
    assert r.nfc_match is True
