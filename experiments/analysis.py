"""Statistical analysis utilities for biometric and performance evaluation."""

import math
from typing import Tuple

import numpy as np


def mean_ci(data: np.ndarray, alpha: float = 0.05) -> Tuple[float, float, float]:
    """
    Return (mean, ci_low, ci_high) for a 1-D array using Student's t-distribution.

    alpha=0.05 → 95% confidence interval.
    """
    n = len(data)
    m = float(np.mean(data))
    se = float(np.std(data, ddof=1)) / math.sqrt(n)
    try:
        from scipy import stats  # type: ignore
        t_crit = stats.t.ppf(1 - alpha / 2, df=n - 1)
    except ImportError:
        # Normal approximation when scipy unavailable
        t_crit = 1.96  # ~95% CI
    margin = t_crit * se
    return m, m - margin, m + margin


def welch_t_test(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """
    Welch's unequal-variance t-test.

    Returns (t_statistic, p_value).
    """
    try:
        from scipy import stats  # type: ignore
        t_stat, p_value = stats.ttest_ind(a, b, equal_var=False)
        return float(t_stat), float(p_value)
    except ImportError:
        # Manual Welch's t-test
        n1, n2 = len(a), len(b)
        m1, m2 = np.mean(a), np.mean(b)
        v1, v2 = np.var(a, ddof=1), np.var(b, ddof=1)
        t_stat = float((m1 - m2) / math.sqrt(v1 / n1 + v2 / n2))
        # Welch–Satterthwaite df
        df = (v1 / n1 + v2 / n2) ** 2 / (
            (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
        )
        # p-value approximation via normal CDF for large df
        p_value = 2 * (1 - _normal_cdf(abs(t_stat)))
        return t_stat, p_value


def compute_eer(far: np.ndarray, frr: np.ndarray) -> Tuple[float, int]:
    """
    Compute Equal Error Rate and the index where FAR ≈ FRR.

    Returns (eer_value, eer_index).
    """
    diff = np.abs(far - frr)
    idx = int(np.argmin(diff))
    eer = float((far[idx] + frr[idx]) / 2)
    return eer, idx


def compute_tar_at_far(far: np.ndarray, tar: np.ndarray, target_far: float) -> float:
    """
    Return TAR at the closest FAR value to target_far.

    Useful for TAR@0.1%FAR (target_far=0.001) per ISO/IEC 19795.
    """
    idx = int(np.argmin(np.abs(far - target_far)))
    return float(tar[idx])


def _normal_cdf(z: float) -> float:
    """Approximation of standard normal CDF using math.erfc."""
    return 0.5 * math.erfc(-z / math.sqrt(2))
