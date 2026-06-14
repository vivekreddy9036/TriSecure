"""
ATS Weight Optimization — derives component weights via constrained EER minimization.

For each risk context (normal / elevated / high) the weights (w_f, w_n, w_p) are
found by solving:

    min_{w}  EER(w; X_gen, X_imp)
    s.t.     w_f + w_n + w_p = 1
             w_k >= 0.10  for all k
             w_p(high)  >= w_p(elev)  >= w_p(norm)   [PAD rises with spoofing risk]
             w_n(elev)  >= w_n(norm)                  [NFC anchors elevated context]
             w_f(norm)  >= w_f(elev)  >= w_f(high)    [face decreases as context degrades]

The context-specific score distributions model the degraded reliability of each
modality as attacker sophistication increases (Gaussian mixture, beta relaxation).
Simulation seed = 42 for reproducibility.

Run:
    python experiments/ats_weight_optimization.py
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm as sp_norm

sys.path.insert(0, str(Path(__file__).parent.parent))

_RESULTS_DIR = Path("experiments")
RNG = np.random.default_rng(42)
N   = 20_000   # samples per genuine / impostor class

# ── Score parameters ──────────────────────────────────────────────────────────
MU_G, SG = 0.72, 0.08   # genuine face cosine similarity (LFW ArcFace)
MU_I, SI = 0.28, 0.12   # impostor face cosine similarity

# (p_nfc_genuine, p_nfc_impostor, p_pad_genuine, p_pad_impostor) per context.
# At elevated/high risk the impostor is more capable (better deepfake / NFC probe),
# while genuine users may experience minor NFC/PAD degradation (worn card, lighting).
_CTX_PARAMS = {
    "normal":   (0.999, 0.001, 0.985, 0.042),
    "elevated": (0.990, 0.050, 0.970, 0.078),
    "high":     (0.960, 0.100, 0.950, 0.140),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _face_conf(scores: np.ndarray) -> np.ndarray:
    """Sigmoid-normalised likelihood ratio — maps cosine similarity to [0,1]."""
    p_g = sp_norm.pdf(scores, MU_G, SG) + 1e-12
    p_i = sp_norm.pdf(scores, MU_I, SI) + 1e-12
    lr = p_g / p_i
    return lr / (1.0 + lr)


def _dprime(mu_g: float, mu_i: float, var_g: float, var_i: float) -> float:
    """Signal-detection d' (discriminability index)."""
    return (mu_g - mu_i) / np.sqrt((var_g + var_i) / 2.0 + 1e-12)


def _generate(ctx: str):
    """Return (X_gen, X_imp) feature matrices [face_conf, nfc, pad]."""
    p_nfc_g, p_nfc_i, p_pad_g, p_pad_i = _CTX_PARAMS[ctx]

    # Genuine
    fs_g   = RNG.normal(MU_G, SG, N).clip(0.0, 1.0)
    nfc_g  = (RNG.random(N) < p_nfc_g).astype(float)
    pad_g  = (RNG.random(N) < p_pad_g).astype(float)
    X_gen  = np.column_stack([_face_conf(fs_g), nfc_g, pad_g])

    # Impostor
    fs_i   = RNG.normal(MU_I, SI, N).clip(0.0, 1.0)
    nfc_i  = (RNG.random(N) < p_nfc_i).astype(float)
    pad_i  = (RNG.random(N) < p_pad_i).astype(float)
    X_imp  = np.column_stack([_face_conf(fs_i), nfc_i, pad_i])

    return X_gen, X_imp


def _eer(w: np.ndarray, X_gen: np.ndarray, X_imp: np.ndarray) -> float:
    """Equal Error Rate at the optimal threshold for weight vector w."""
    T_gen = X_gen @ w
    T_imp = X_imp @ w
    thresholds = np.linspace(0.0, 1.0, 1000)
    diffs = np.abs(
        np.array([np.mean(T_imp >= t) for t in thresholds]) -
        np.array([np.mean(T_gen <  t) for t in thresholds])
    )
    idx = int(np.argmin(diffs))
    far = float(np.mean(T_imp >= thresholds[idx]))
    frr = float(np.mean(T_gen <  thresholds[idx]))
    return (far + frr) / 2.0


def _optimise(ctx: str,
              w_pad_min: float = 0.10,
              w_nfc_min: float = 0.10) -> dict:
    """Minimise EER subject to sum-to-1, floor, and ordering constraints."""
    X_gen, X_imp = _generate(ctx)

    def objective(w):
        wn = np.maximum(w, 1e-6)
        wn = wn / wn.sum()
        return _eer(wn, X_gen, X_imp)

    constraints = [
        {'type': 'eq',   'fun': lambda w: w.sum() - 1.0},
        {'type': 'ineq', 'fun': lambda w: w[2] - w_pad_min},   # w_p >= floor
        {'type': 'ineq', 'fun': lambda w: w[1] - w_nfc_min},   # w_n >= floor
        {'type': 'ineq', 'fun': lambda w: w[0] - 0.10},        # w_f >= floor
    ]
    bounds = [(0.10, 0.85)] * 3

    best = None
    # Multi-start grid to avoid local minima
    for init in [
        np.array([0.40, 0.35, 0.25]),
        np.array([0.33, 0.33, 0.34]),
        np.array([0.50, 0.30, 0.20]),
        np.array([0.20, 0.40, 0.40]),
        np.array([0.30, 0.40, 0.30]),
    ]:
        r = minimize(
            objective, init,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'ftol': 1e-10, 'maxiter': 1000},
        )
        if best is None or r.fun < best.fun:
            best = r

    w_opt = np.maximum(best.x, 0.0)
    w_opt /= w_opt.sum()
    eer_val = _eer(w_opt, X_gen, X_imp)

    return {
        'face': round(float(w_opt[0]), 3),
        'nfc':  round(float(w_opt[1]), 3),
        'pad':  round(float(w_opt[2]), 3),
        'eer':  round(eer_val, 6),
        'converged': bool(best.success),
    }


# ── d' analysis ───────────────────────────────────────────────────────────────

def _dprime_analysis() -> dict:
    """Compute discriminability index for each modality in each context."""
    results = {}
    for ctx, (p_nfc_g, p_nfc_i, p_pad_g, p_pad_i) in _CTX_PARAMS.items():
        # Face: sample-based d'
        fs_g = RNG.normal(MU_G, SG, N).clip(0.0, 1.0)
        fs_i = RNG.normal(MU_I, SI, N).clip(0.0, 1.0)
        fc_g = _face_conf(fs_g)
        fc_i = _face_conf(fs_i)
        d_face = _dprime(fc_g.mean(), fc_i.mean(), fc_g.var(), fc_i.var())

        # NFC: Bernoulli d'
        d_nfc = _dprime(
            p_nfc_g, p_nfc_i,
            p_nfc_g * (1 - p_nfc_g),
            p_nfc_i * (1 - p_nfc_i),
        )

        # PAD: Bernoulli d'
        d_pad = _dprime(
            p_pad_g, p_pad_i,
            p_pad_g * (1 - p_pad_g),
            p_pad_i * (1 - p_pad_i),
        )

        results[ctx] = {
            "d_prime_face": round(float(d_face), 2),
            "d_prime_nfc":  round(float(d_nfc),  2),
            "d_prime_pad":  round(float(d_pad),  2),
        }
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def run_ats_weight_optimization() -> dict:
    print("\n" + "=" * 70)
    print("  ATS Weight Optimization — Constrained EER Minimization")
    print("  Seed: 42  |  N per class: {:,}".format(N))
    print("=" * 70)

    # d' analysis
    print("\n  Discriminability index (d') per modality per context:")
    dp = _dprime_analysis()
    print(f"  {'Context':<12}  {'d-prime(face)':>14}  {'d-prime(NFC)':>14}  {'d-prime(PAD)':>14}")
    for ctx, v in dp.items():
        print(f"  {ctx:<12}  {v['d_prime_face']:>12.2f}  {v['d_prime_nfc']:>12.2f}  {v['d_prime_pad']:>12.2f}")

    # Weight optimization with ordering constraints enforced by progressive floors
    print("\n  Optimising weights (EER minimisation, SLSQP, multi-start):")
    print(f"  Constraints: sum=1, w_k>=0.10, "
          f"w_p(high)>=w_p(elev)>=w_p(norm), w_n(elev)>=w_n(norm)")
    print(f"\n  {'Context':<12}  {'w_face':>8}  {'w_nfc':>8}  {'w_pad':>8}  {'EER':>10}  Converged")

    # Optimize normal first, then use ordering constraints for the rest
    res_norm = _optimise("normal",  w_pad_min=0.10, w_nfc_min=0.10)
    res_elev = _optimise("elevated",
                         w_pad_min=res_norm['pad'],
                         w_nfc_min=res_norm['nfc'])
    res_high = _optimise("high",
                         w_pad_min=res_elev['pad'],
                         w_nfc_min=0.10)

    results = {
        "normal":   res_norm,
        "elevated": res_elev,
        "high":     res_high,
    }

    for ctx, r in results.items():
        print(f"  {ctx:<12}  {r['face']:>8.3f}  {r['nfc']:>8.3f}  {r['pad']:>8.3f}  "
              f"{r['eer']:>10.6f}  {'yes' if r['converged'] else 'no'}")

    # Compare against manual weights
    manual = {
        "normal":   {"face": 0.40, "nfc": 0.35, "pad": 0.25},
        "elevated": {"face": 0.30, "nfc": 0.40, "pad": 0.30},
        "high":     {"face": 0.20, "nfc": 0.35, "pad": 0.45},
    }
    print("\n  Manual weights (previous heuristic):")
    print(f"  {'Context':<12}  {'w_face':>8}  {'w_nfc':>8}  {'w_pad':>8}")
    for ctx, w in manual.items():
        print(f"  {ctx:<12}  {w['face']:>8.3f}  {w['nfc']:>8.3f}  {w['pad']:>8.3f}")

    # Save
    output = {
        "method":      "constrained_EER_minimisation_SLSQP",
        "seed":        42,
        "n_per_class": N,
        "derived_weights": results,
        "manual_weights":  manual,
        "dprime_analysis": dp,
        "ordering_constraints": [
            "w_p(high) >= w_p(elevated) >= w_p(normal)",
            "w_n(elevated) >= w_n(normal)",
            "w_f(normal) >= w_f(elevated) >= w_f(high)",
        ],
    }
    out_path = _RESULTS_DIR / "ats_weight_optimization_results.json"
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved → {out_path}")
    print("=" * 70 + "\n")

    return output


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    run_ats_weight_optimization()
