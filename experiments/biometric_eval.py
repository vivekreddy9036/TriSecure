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

def _try_plot(genuine: np.ndarray, impostor: np.ndarray, roc: dict, eer: float,
              eer_threshold: float = 0.539) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
        from scipy.stats import gaussian_kde  # type: ignore

        _FIGURES_DIR.mkdir(parents=True, exist_ok=True)

        # Publication style
        plt.rcParams.update({
            "font.family":      "DejaVu Sans",
            "font.size":        11,
            "axes.titlesize":   12,
            "axes.labelsize":   11,
            "xtick.labelsize":  10,
            "ytick.labelsize":  10,
            "legend.fontsize":  10,
            "figure.dpi":       300,
            "axes.spines.top":  False,
            "axes.spines.right":False,
        })

        far = np.array(roc["FAR"])
        frr = np.array(roc["FRR"])
        tar = np.array(roc["TAR"])

        # AUC (trapezoidal)
        auc = float(np.trapz(tar[::-1], far[::-1]))

        # EER index on dense curve
        eer_idx = int(np.argmin(np.abs(far - frr)))

        # ── ROC ──────────────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.plot(far * 100, tar * 100, lw=2, color="#1f77b4",
                label=f"ArcFace (AUC={auc:.4f})")
        ax.plot([0, 100], [100, 0], color="gray", lw=0.8, ls="--",   # EER line
                alpha=0.5, label=f"EER = {eer*100:.2f}%")
        # Mark EER operating point
        ax.scatter([far[eer_idx]*100], [tar[eer_idx]*100],
                   color="#d62728", zorder=5, s=60,
                   label=f"EER point ({far[eer_idx]*100:.2f}%, {tar[eer_idx]*100:.2f}%)")
        # Mark TAR@1%FAR
        idx_1pct = int(np.argmin(np.abs(far - 0.01)))
        ax.scatter([far[idx_1pct]*100], [tar[idx_1pct]*100],
                   color="#2ca02c", marker="^", zorder=5, s=60,
                   label=f"TAR@1%FAR = {tar[idx_1pct]*100:.1f}%")
        ax.set_xlim(-1, 101);  ax.set_ylim(-1, 101)
        ax.set_xlabel("False Accept Rate — FAR (%)")
        ax.set_ylabel("True Accept Rate — TAR (%)")
        ax.set_title("ROC Curve — TRIsecure V2")
        ax.legend(loc="lower right", framealpha=0.9)
        ax.grid(True, alpha=0.25, linestyle=":")
        fig.tight_layout()
        fig.savefig(_FIGURES_DIR / "roc_curve.png", dpi=300, bbox_inches="tight")
        plt.close(fig)

        # ── DET ──────────────────────────────────────────────────────────────
        eps = 1e-4
        far_pos = np.clip(far,  eps, 1.0)
        frr_pos = np.clip(frr,  eps, 1.0)

        fig, ax = plt.subplots(figsize=(5, 5))
        ax.plot(far_pos * 100, frr_pos * 100, lw=2, color="#1f77b4",
                label="ArcFace (sim)")
        # EER diagonal reference
        ref = np.logspace(-2, 2, 200)
        ax.plot(ref, ref, color="gray", lw=0.8, ls="--", alpha=0.5, label="EER line")
        ax.scatter([far[eer_idx]*100], [frr[eer_idx]*100],
                   color="#d62728", zorder=5, s=60,
                   label=f"EER = {eer*100:.2f}%")
        ax.set_xscale("log");  ax.set_yscale("log")
        ax.set_xlim(1e-2, 1e2);  ax.set_ylim(1e-2, 1e2)
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:g}"))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:g}"))
        ax.set_xlabel("False Accept Rate — FAR (%)")
        ax.set_ylabel("False Reject Rate — FRR (%)")
        ax.set_title("DET Curve — TRIsecure V2")
        ax.legend(loc="upper right", framealpha=0.9)
        ax.grid(True, which="both", alpha=0.2, linestyle=":")
        fig.tight_layout()
        fig.savefig(_FIGURES_DIR / "det_curve.png", dpi=300, bbox_inches="tight")
        plt.close(fig)

        # ── Score distributions ──────────────────────────────────────────────
        x_range = np.linspace(0.0, 1.0, 400)
        kde_gen = gaussian_kde(genuine,  bw_method=0.15)
        kde_imp = gaussian_kde(impostor, bw_method=0.15)

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.fill_between(x_range, kde_gen(x_range),  alpha=0.35, color="#1f77b4", label="Genuine")
        ax.fill_between(x_range, kde_imp(x_range),  alpha=0.35, color="#ff7f0e", label="Impostor")
        ax.plot(x_range, kde_gen(x_range),  lw=1.5, color="#1f77b4")
        ax.plot(x_range, kde_imp(x_range),  lw=1.5, color="#ff7f0e")
        # EER threshold line
        ax.axvline(eer_threshold, color="#d62728", lw=1.5, ls="--",
                   label=f"EER threshold = {eer_threshold:.3f}")
        ax.set_xlabel("Cosine similarity score")
        ax.set_ylabel("Density")
        ax.set_title("Genuine / Impostor Score Distributions — ArcFace")
        ax.set_xlim(0.0, 1.0)
        ax.legend(framealpha=0.9)
        ax.grid(True, alpha=0.25, linestyle=":")
        fig.tight_layout()
        fig.savefig(_FIGURES_DIR / "score_distributions.png", dpi=300, bbox_inches="tight")
        plt.close(fig)

        # ── Combined 2×2 panel for paper submission ──────────────────────────
        fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))

        # Panel 1: ROC
        axes[0].plot(far * 100, tar * 100, lw=2, color="#1f77b4",
                     label=f"AUC={auc:.4f}")
        axes[0].plot([0,100],[100,0], "gray", lw=0.8, ls="--", alpha=0.5)
        axes[0].scatter([far[eer_idx]*100],[tar[eer_idx]*100],
                        color="#d62728", zorder=5, s=50,
                        label=f"EER={eer*100:.2f}%")
        axes[0].set_xlim(-1,101); axes[0].set_ylim(-1,101)
        axes[0].set_xlabel("FAR (%)"); axes[0].set_ylabel("TAR (%)")
        axes[0].set_title("(a) ROC Curve")
        axes[0].legend(loc="lower right", fontsize=9)
        axes[0].grid(True, alpha=0.25, ls=":")

        # Panel 2: DET
        axes[1].plot(far_pos*100, frr_pos*100, lw=2, color="#1f77b4")
        axes[1].plot(ref, ref, "gray", lw=0.8, ls="--", alpha=0.5)
        axes[1].scatter([far[eer_idx]*100],[frr[eer_idx]*100],
                        color="#d62728", zorder=5, s=50,
                        label=f"EER={eer*100:.2f}%")
        axes[1].set_xscale("log"); axes[1].set_yscale("log")
        axes[1].set_xlim(1e-2,1e2); axes[1].set_ylim(1e-2,1e2)
        axes[1].xaxis.set_major_formatter(ticker.FuncFormatter(lambda x,_: f"{x:g}"))
        axes[1].yaxis.set_major_formatter(ticker.FuncFormatter(lambda x,_: f"{x:g}"))
        axes[1].set_xlabel("FAR (%)"); axes[1].set_ylabel("FRR (%)")
        axes[1].set_title("(b) DET Curve")
        axes[1].legend(fontsize=9)
        axes[1].grid(True, which="both", alpha=0.2, ls=":")

        # Panel 3: Score distributions
        axes[2].fill_between(x_range, kde_gen(x_range),  alpha=0.35, color="#1f77b4", label="Genuine")
        axes[2].fill_between(x_range, kde_imp(x_range),  alpha=0.35, color="#ff7f0e", label="Impostor")
        axes[2].plot(x_range, kde_gen(x_range),  lw=1.5, color="#1f77b4")
        axes[2].plot(x_range, kde_imp(x_range),  lw=1.5, color="#ff7f0e")
        axes[2].axvline(eer_threshold, color="#d62728", lw=1.5, ls="--",
                        label=f"τ={eer_threshold:.3f}")
        axes[2].set_xlabel("Cosine similarity"); axes[2].set_ylabel("Density")
        axes[2].set_title("(c) Score Distributions")
        axes[2].set_xlim(0.0, 1.0)
        axes[2].legend(fontsize=9)
        axes[2].grid(True, alpha=0.25, ls=":")

        fig.suptitle("TRIsecure V2 — Biometric Evaluation (ArcFace, Simulation Mode)",
                     fontsize=13, y=1.01)
        fig.tight_layout()
        fig.savefig(_FIGURES_DIR / "biometric_eval_panel.png", dpi=300, bbox_inches="tight")
        plt.close(fig)

        print(f"  Figures saved → {_FIGURES_DIR}/")
    except ImportError as e:
        print(f"  matplotlib/scipy not available — skipping figures ({e})")
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

    _try_plot(genuine, impostor, roc, eer, eer_threshold)

    print("=" * 70 + "\n")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_biometric_evaluation()
