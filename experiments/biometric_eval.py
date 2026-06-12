"""
Biometric evaluation pipeline for TRIsecure V2.

Generates all paper tables and figures required for Q2 submission:
  - Table 4: FAR/FRR threshold sweep (≥10 operating points)
  - EER, TAR@0.1%FAR, TAR@1%FAR per ISO/IEC 19795
  - PAD metrics: APCER, BPCER, ACER per ISO/IEC 30107-3
  - ROC curve  (FAR vs TAR)
  - DET curve  (FAR vs FRR, log scale)

Score distributions use LFW-derived ArcFace priors (simulation mode):
  Genuine  ~ N(mu=0.72, sigma=0.08)
  Impostor ~ N(mu=0.28, sigma=0.12)
Label clearly as SIMULATION in all outputs — reviewer honest.

Run standalone::

    python experiments/biometric_eval.py
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.analysis import mean_ci, compute_eer, compute_tar_at_far

logger = logging.getLogger(__name__)

_RESULTS_DIR = Path("experiments")
_FIGURES_DIR = Path("experiments/figures")

# LFW-derived ArcFace priors (from biometric_fusion.py)
_MU_G, _SIGMA_G = 0.72, 0.08
_MU_I, _SIGMA_I = 0.28, 0.12

N_GENUINE   = 1000
N_IMPOSTOR  = 1000
N_BONA_FIDE = 500   # PAD live samples
N_ATTACK    = 400   # PAD spoof samples (200 print + 200 replay)


# ---------------------------------------------------------------------------
# Score generation
# ---------------------------------------------------------------------------

def generate_score_distributions(
    rng: np.random.Generator,
) -> Tuple[np.ndarray, np.ndarray]:
    genuine   = rng.normal(_MU_G, _SIGMA_G, N_GENUINE).clip(0.0, 1.0)
    impostor  = rng.normal(_MU_I, _SIGMA_I, N_IMPOSTOR).clip(0.0, 1.0)
    return genuine, impostor


# ---------------------------------------------------------------------------
# FAR / FRR / TAR sweep
# ---------------------------------------------------------------------------

def threshold_sweep(
    genuine: np.ndarray,
    impostor: np.ndarray,
    thresholds: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    far = np.array([float(np.mean(impostor >= t)) for t in thresholds])
    frr = np.array([float(np.mean(genuine  <  t)) for t in thresholds])
    tar = 1.0 - frr
    return far, frr, tar


def build_threshold_table(
    genuine: np.ndarray,
    impostor: np.ndarray,
    n_points: int = 15,
) -> List[dict]:
    thresholds = np.linspace(0.1, 0.9, n_points)
    far, frr, tar = threshold_sweep(genuine, impostor, thresholds)
    rows = []
    for i, t in enumerate(thresholds):
        rows.append({
            "threshold":  round(float(t),   3),
            "FAR":        round(float(far[i]), 4),
            "FRR":        round(float(frr[i]), 4),
            "TAR":        round(float(tar[i]), 4),
        })
    return rows


# ---------------------------------------------------------------------------
# PAD metrics (ISO/IEC 30107-3)
# ---------------------------------------------------------------------------

def simulate_pad_evaluation(rng: np.random.Generator) -> dict:
    """
    Simulate PAD evaluation with parameterised error rates.

    SilentFace MiniFASNetV2 reported rates on CelebA-Spoof (paper):
      Live  accuracy ~98.5%  → BPCER ≈ 1.5%
      Print APCER   ~4.2%
      Replay APCER  ~7.8%
    We use these as ground-truth parameters for the simulation.
    """
    bpcer_rate   = 0.015   # 1.5% bona fide misclassified as attack
    apcer_print  = 0.042   # 4.2% print attacks pass as live
    apcer_replay = 0.078   # 7.8% replay attacks pass as live

    # Bona fide: 1 = live (correct), 0 = rejected (error)
    bf_decisions = rng.random(N_BONA_FIDE) > bpcer_rate   # True = correctly live
    # Print attacks: 1 = passed (attack success / error), 0 = blocked (correct)
    print_decisions  = rng.random(N_ATTACK // 2) < apcer_print
    replay_decisions = rng.random(N_ATTACK // 2) < apcer_replay

    bpcer = float(np.mean(~bf_decisions))
    apcer_p = float(np.mean(print_decisions))
    apcer_r = float(np.mean(replay_decisions))
    apcer   = float(np.mean(np.concatenate([print_decisions, replay_decisions])))
    acer    = (apcer + bpcer) / 2.0

    return {
        "N_bona_fide":           N_BONA_FIDE,
        "N_attack_print":        N_ATTACK // 2,
        "N_attack_replay":       N_ATTACK // 2,
        "BPCER":                 round(bpcer,   4),
        "APCER_print":           round(apcer_p, 4),
        "APCER_replay":          round(apcer_r, 4),
        "APCER_combined":        round(apcer,   4),
        "ACER":                  round(acer,    4),
        "spoof_success_rate_print":  round(apcer_p, 4),
        "spoof_success_rate_replay": round(apcer_r, 4),
        "note": "Simulated using SilentFace MiniFASNetV2 CelebA-Spoof reported rates",
    }


# ---------------------------------------------------------------------------
# ROC / DET data export
# ---------------------------------------------------------------------------

def roc_det_data(
    genuine: np.ndarray,
    impostor: np.ndarray,
    n_points: int = 200,
) -> dict:
    thresholds = np.linspace(0.0, 1.0, n_points)
    far, frr, tar = threshold_sweep(genuine, impostor, thresholds)
    return {
        "thresholds": thresholds.tolist(),
        "FAR":        far.tolist(),
        "FRR":        frr.tolist(),
        "TAR":        tar.tolist(),
    }


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _try_plot(genuine: np.ndarray, impostor: np.ndarray, roc: dict, eer: float) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _FIGURES_DIR.mkdir(parents=True, exist_ok=True)
        far  = np.array(roc["FAR"])
        frr  = np.array(roc["FRR"])
        tar  = np.array(roc["TAR"])

        # --- ROC ---
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.plot(far * 100, tar * 100, lw=2, label=f"ArcFace sim (EER={eer*100:.2f}%)")
        ax.plot([0, 100], [0, 100], "k--", lw=0.8, alpha=0.4)
        ax.set_xlabel("FAR (%)")
        ax.set_ylabel("TAR (%)")
        ax.set_title("ROC Curve — TRIsecure V2 (Simulation)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(_FIGURES_DIR / "roc_curve.png", dpi=150)
        plt.close(fig)

        # --- DET ---
        eps = 1e-6
        far_pos = np.clip(far, eps, 1.0)
        frr_pos = np.clip(frr, eps, 1.0)
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.plot(far_pos * 100, frr_pos * 100, lw=2)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("FAR (%)")
        ax.set_ylabel("FRR (%)")
        ax.set_title("DET Curve — TRIsecure V2 (Simulation)")
        ax.grid(True, which="both", alpha=0.3)
        fig.tight_layout()
        fig.savefig(_FIGURES_DIR / "det_curve.png", dpi=150)
        plt.close(fig)

        # --- Score distribution ---
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(genuine,  bins=50, alpha=0.6, label="Genuine",  density=True)
        ax.hist(impostor, bins=50, alpha=0.6, label="Impostor", density=True)
        ax.set_xlabel("Cosine similarity score")
        ax.set_ylabel("Density")
        ax.set_title("Score Distributions — ArcFace (Simulation)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(_FIGURES_DIR / "score_distributions.png", dpi=150)
        plt.close(fig)

        print(f"  Figures saved → {_FIGURES_DIR}/")
    except ImportError:
        print("  matplotlib not available — skipping figures")
    except Exception as exc:
        print(f"  Figure generation failed: {exc}")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_biometric_evaluation(seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)

    print("\n" + "=" * 70)
    print("  TRIsecure V2 — Biometric Evaluation (ISO/IEC 19795 + 30107-3)")
    print("  Mode: SIMULATION (LFW-derived ArcFace priors)")
    print("=" * 70)

    # Score generation
    genuine, impostor = generate_score_distributions(rng)
    print(f"\n  Genuine  scores: N={len(genuine)}, "
          f"mean={genuine.mean():.4f}, std={genuine.std():.4f}")
    print(f"  Impostor scores: N={len(impostor)}, "
          f"mean={impostor.mean():.4f}, std={impostor.std():.4f}")

    # Threshold sweep table
    sweep_table = build_threshold_table(genuine, impostor)
    print(f"\n  Threshold sweep ({len(sweep_table)} points):")
    print(f"  {'Threshold':>10}  {'FAR':>8}  {'FRR':>8}  {'TAR':>8}")
    for row in sweep_table:
        print(f"  {row['threshold']:>10.3f}  {row['FAR']:>8.4f}  "
              f"{row['FRR']:>8.4f}  {row['TAR']:>8.4f}")

    # EER
    thresholds_dense = np.linspace(0.0, 1.0, 1000)
    far_d, frr_d, tar_d = threshold_sweep(genuine, impostor, thresholds_dense)
    eer, eer_idx = compute_eer(far_d, frr_d)
    eer_threshold = float(thresholds_dense[eer_idx])
    tar_01far = compute_tar_at_far(far_d, tar_d, 0.001)
    tar_1far  = compute_tar_at_far(far_d, tar_d, 0.01)

    print(f"\n  EER:             {eer*100:.3f}%  (threshold={eer_threshold:.3f})")
    print(f"  TAR @ 0.1% FAR:  {tar_01far*100:.2f}%")
    print(f"  TAR @ 1.0% FAR:  {tar_1far*100:.2f}%")

    # PAD metrics
    pad = simulate_pad_evaluation(rng)
    print(f"\n  PAD evaluation (ISO/IEC 30107-3):")
    print(f"  BPCER:          {pad['BPCER']*100:.2f}%")
    print(f"  APCER (print):  {pad['APCER_print']*100:.2f}%")
    print(f"  APCER (replay): {pad['APCER_replay']*100:.2f}%")
    print(f"  APCER combined: {pad['APCER_combined']*100:.2f}%")
    print(f"  ACER:           {pad['ACER']*100:.2f}%")

    # ROC/DET data
    roc = roc_det_data(genuine, impostor)

    # Assemble results
    results = {
        "evaluation_mode": "simulation",
        "prior_source": "LFW ArcFace buffalo_sc",
        "n_genuine":  N_GENUINE,
        "n_impostor": N_IMPOSTOR,
        "genuine_stats": {
            "mean": round(float(genuine.mean()), 4),
            "std":  round(float(genuine.std()),  4),
        },
        "impostor_stats": {
            "mean": round(float(impostor.mean()), 4),
            "std":  round(float(impostor.std()),  4),
        },
        "eer":           round(eer, 4),
        "eer_threshold": round(eer_threshold, 4),
        "tar_at_01pct_far": round(tar_01far, 4),
        "tar_at_1pct_far":  round(tar_1far,  4),
        "threshold_sweep":  sweep_table,
        "pad_metrics":      pad,
        "roc_det":          roc,
    }

    out_path = _RESULTS_DIR / "biometric_eval_results.json"
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved → {out_path}")

    _try_plot(genuine, impostor, roc, eer)

    print("=" * 70 + "\n")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_biometric_evaluation()
