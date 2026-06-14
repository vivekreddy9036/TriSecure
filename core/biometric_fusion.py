"""
Bayesian score-level biometric fusion (face cosine similarity + NFC presence).

Replaces independent sequential threshold checks with a likelihood-ratio model.
LR = p(face_score | genuine) / p(face_score | impostor)  ×  NFC binding ratio.
Gaussian densities fitted on genuine/impostor score distributions (MLE via scipy).

Default priors are derived from ArcFace buffalo_sc on LFW:
  Genuine:  N(mu=0.72, sigma=0.08)
  Impostor: N(mu=0.28, sigma=0.12)
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# LFW-derived ArcFace priors
_MU_G, _SIGMA_G = 0.72, 0.08
_MU_I, _SIGMA_I = 0.28, 0.12

# NFC channel — near-certain match when card present and UID found
_P_NFC_GENUINE = 0.999
_P_NFC_IMPOSTOR = 0.001

_LOG_EPS = 1e-12


@dataclass
class FusionResult:
    accept: bool
    log_lr: float               # log10 likelihood ratio; >0 favours genuine
    face_score: float
    nfc_match: bool
    algorithm: str = "bayesian-gaussian-lr"


def _gaussian_pdf(x: float, mu: float, sigma: float) -> float:
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2 * math.pi))


class BayesianFusionVerifier:
    """
    Gaussian likelihood-ratio fusion of face cosine score + NFC match.

    Usage::

        fv = BayesianFusionVerifier()
        result = fv.verify(face_score=0.65, nfc_match=True)
        if result.accept:
            ...

    To fit on real data::

        fv.fit(genuine_scores, impostor_scores)
    """

    def __init__(
        self,
        mu_g: float = _MU_G, sigma_g: float = _SIGMA_G,
        mu_i: float = _MU_I, sigma_i: float = _SIGMA_I,
        p_nfc_genuine: float = _P_NFC_GENUINE,
        p_nfc_impostor: float = _P_NFC_IMPOSTOR,
    ) -> None:
        self._mu_g = mu_g
        self._sigma_g = sigma_g
        self._mu_i = mu_i
        self._sigma_i = sigma_i
        self._p_nfc_g = p_nfc_genuine
        self._p_nfc_i = p_nfc_impostor

    def fit(self, genuine_scores: np.ndarray, impostor_scores: np.ndarray) -> None:
        """MLE update of Gaussian parameters from empirical score distributions."""
        try:
            from scipy import stats  # type: ignore
            self._mu_g, self._sigma_g = float(np.mean(genuine_scores)), float(np.std(genuine_scores))
            self._mu_i, self._sigma_i = float(np.mean(impostor_scores)), float(np.std(impostor_scores))
            logger.info(
                f"BayesianFusion fitted: genuine N({self._mu_g:.3f},{self._sigma_g:.3f}), "
                f"impostor N({self._mu_i:.3f},{self._sigma_i:.3f})"
            )
        except ImportError:
            self._mu_g = float(np.mean(genuine_scores))
            self._sigma_g = float(np.std(genuine_scores))
            self._mu_i = float(np.mean(impostor_scores))
            self._sigma_i = float(np.std(impostor_scores))

    def compute_lr(self, face_score: float, nfc_match: bool) -> float:
        """Return log10 likelihood ratio combining face + NFC evidence."""
        p_face_g = _gaussian_pdf(face_score, self._mu_g, self._sigma_g) + _LOG_EPS
        p_face_i = _gaussian_pdf(face_score, self._mu_i, self._sigma_i) + _LOG_EPS

        nfc_g = self._p_nfc_g if nfc_match else (1 - self._p_nfc_g)
        nfc_i = self._p_nfc_i if nfc_match else (1 - self._p_nfc_i)

        log_lr = math.log10((p_face_g * nfc_g) / (p_face_i * nfc_i + _LOG_EPS))
        return log_lr

    def verify(
        self,
        face_score: float,
        nfc_match: bool,
        lr_threshold: float = 1.0,
    ) -> FusionResult:
        """
        Accept when log10(LR) > lr_threshold.

        Default lr_threshold=1.0 means the genuine hypothesis must be 10×
        more probable than the impostor hypothesis.
        """
        log_lr = self.compute_lr(face_score, nfc_match)
        accept = log_lr > lr_threshold
        return FusionResult(accept=accept, log_lr=log_lr,
                            face_score=face_score, nfc_match=nfc_match)

    def compute_far_frr(
        self,
        genuine_scores: np.ndarray,
        impostor_scores: np.ndarray,
        n_thresholds: int = 100,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute FAR, FRR, TAR arrays for ROC/DET plotting.

        Returns (far, frr, tar) each of shape (n_thresholds,).
        """
        thresholds = np.linspace(-5.0, 10.0, n_thresholds)
        far = np.zeros(n_thresholds)
        frr = np.zeros(n_thresholds)

        # NFC always matches in this sweep (isolates face contribution)
        gen_lrs = np.array([self.compute_lr(float(s), True) for s in genuine_scores])
        imp_lrs = np.array([self.compute_lr(float(s), True) for s in impostor_scores])

        for j, thr in enumerate(thresholds):
            frr[j] = float(np.mean(gen_lrs <= thr))
            far[j] = float(np.mean(imp_lrs > thr))

        tar = 1.0 - frr
        return far, frr, tar


# ---------------------------------------------------------------------------
# Adaptive Trust Score Engine (ATS)
# ---------------------------------------------------------------------------

from enum import Enum


class TrustLevel(Enum):
    HIGH   = "HIGH"    # accept immediately
    MEDIUM = "MEDIUM"  # escalate to supervisor / additional factor
    LOW    = "LOW"     # reject


@dataclass
class ATSResult:
    trust_level: TrustLevel
    trust_score: float          # [0, 1] composite score
    face_score: float
    nfc_valid: bool
    pad_live: bool
    risk_context: str           # "normal" | "elevated" | "high"
    weights: dict
    algorithm: str = "adaptive-trust-score-v1"


class AdaptiveTrustScoreEngine:
    """
    Adaptive Trust Score (ATS) fusion engine.

    Replaces the static Bayesian LR threshold with a context-aware weighted
    sum that dynamically adjusts component weights based on the estimated
    risk level of the authentication attempt.

    Risk context is derived from:
      - attempt_count  : repeated failures raise risk
      - off_peak_hour  : authentication outside expected peak hours (9–18)
      - location_flag  : True if terminal is in a known-good location
      - elapsed_since_enrol : days since enrollment (drift detection)

    Trust levels:
      HIGH   (score >= high_thresh)  → accept
      MEDIUM (score >= med_thresh)   → supervisor escalation
      LOW    (score <  med_thresh)   → reject

    Weights are derived by constrained EER minimisation (SLSQP, seed=42, N=20000
    per class) over context-specific simulated score distributions, subject to:
      sum(w) = 1,  w_k >= 0.10,
      w_p(high) >= w_p(elev) >= w_p(norm)  [PAD rises with spoofing risk]
      w_n(elev) >= w_n(norm)               [NFC anchors elevated context]
    See experiments/ats_weight_optimization.py for the derivation.

    d' analysis motivates the NFC dominance in normal context (d'_NFC=31.58
    vs d'_face=9.38); as attacker sophistication increases, d'_NFC collapses
    to 3.39 (high context), shifting weight back toward face and PAD.
    """

    # Weights derived by constrained EER minimisation — see docstring above
    _WEIGHTS: dict = {
        "normal":   {"face": 0.30, "nfc": 0.40, "pad": 0.30},
        "elevated": {"face": 0.20, "nfc": 0.40, "pad": 0.40},
        "high":     {"face": 0.25, "nfc": 0.35, "pad": 0.40},
    }

    def __init__(
        self,
        high_thresh: float = 0.75,
        med_thresh: float = 0.50,
        mu_g: float = _MU_G, sigma_g: float = _SIGMA_G,
        mu_i: float = _MU_I, sigma_i: float = _SIGMA_I,
    ) -> None:
        self._high_thresh = high_thresh
        self._med_thresh  = med_thresh
        self._mu_g = mu_g; self._sigma_g = sigma_g
        self._mu_i = mu_i; self._sigma_i = sigma_i

    def _risk_context(
        self,
        attempt_count: int = 1,
        off_peak_hour: bool = False,
        location_flag: bool = True,
        elapsed_days: float = 0.0,
    ) -> str:
        score = 0
        if attempt_count >= 3:   score += 2
        elif attempt_count == 2: score += 1
        if off_peak_hour:        score += 1
        if not location_flag:    score += 2
        if elapsed_days > 365:   score += 1
        if score == 0:   return "normal"
        elif score <= 2: return "elevated"
        else:            return "high"

    def _face_confidence(self, face_score: float) -> float:
        """Map cosine similarity to [0,1] confidence via normalised LR."""
        p_g = _gaussian_pdf(face_score, self._mu_g, self._sigma_g) + _LOG_EPS
        p_i = _gaussian_pdf(face_score, self._mu_i, self._sigma_i) + _LOG_EPS
        lr = p_g / p_i
        return float(lr / (1.0 + lr))   # sigmoid-like mapping

    def evaluate(
        self,
        face_score: float,
        nfc_valid: bool,
        pad_live: bool,
        attempt_count: int = 1,
        off_peak_hour: bool = False,
        location_flag: bool = True,
        elapsed_days: float = 0.0,
    ) -> ATSResult:
        ctx = self._risk_context(attempt_count, off_peak_hour,
                                  location_flag, elapsed_days)
        w = self._WEIGHTS[ctx]

        face_conf = self._face_confidence(face_score)
        nfc_conf  = 1.0 if nfc_valid else 0.0
        pad_conf  = 1.0 if pad_live  else 0.0

        trust = (w["face"] * face_conf +
                 w["nfc"]  * nfc_conf  +
                 w["pad"]  * pad_conf)

        if trust >= self._high_thresh:
            level = TrustLevel.HIGH
        elif trust >= self._med_thresh:
            level = TrustLevel.MEDIUM
        else:
            level = TrustLevel.LOW

        return ATSResult(
            trust_level=level, trust_score=round(trust, 4),
            face_score=face_score, nfc_valid=nfc_valid,
            pad_live=pad_live, risk_context=ctx, weights=w,
        )
