"""
Comparative analysis: TRIsecure V2 vs. five existing e-voting / biometric auth systems.

All competitor values sourced from published papers (cited in paper/references.bib).
Figures saved to experiments/figures/ at 300 DPI.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

FIGURES_DIR = Path(__file__).parent / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# System definitions — values from published literature
# ---------------------------------------------------------------------------
# Sources:
#   Bello 2021       — Bello et al., "Biometric-based Secure Electronic Voting", IEEE Access 2021
#   Sanchez 2020     — Sánchez-Reillo et al., "Biometric Verification in Constrained Env.", 2020
#   Ayed 2017        — Ayed, "A Conceptual Secure Blockchain-based Electronic Voting System", IJAIS 2017
#   FIDO2            — FIDO Alliance, WebAuthn Level 2 spec; NIST SP 800-63B platform biometric rates
#   ArcFace+PIN      — Deng et al., "ArcFace: Additive Angular Margin Loss", CVPR 2019 (LFW EER)

SYSTEMS = {
    "TRIsecure V2\n(Ours)": {
        "EER (%)":           1.55,
        "FAR (%)":           1.00,
        "FRR (%)":           2.30,
        "Latency (ms)":      110.7,
        "MFA factors":       3,
        "PAD / Liveness":    True,
        "Formal verif.":     True,
        "PQC-ready":         True,
        "Vote receipt":      True,
        "Edge deployment":   True,
        "Open source":       True,
    },
    "Bello et al.\n2021": {
        "EER (%)":           2.50,
        "FAR (%)":           2.10,
        "FRR (%)":           2.90,
        "Latency (ms)":      950.0,
        "MFA factors":       2,
        "PAD / Liveness":    False,
        "Formal verif.":     False,
        "PQC-ready":         False,
        "Vote receipt":      False,
        "Edge deployment":   False,
        "Open source":       False,
    },
    "Sánchez-Reillo\net al. 2020": {
        "EER (%)":           3.20,
        "FAR (%)":           2.80,
        "FRR (%)":           3.60,
        "Latency (ms)":      480.0,
        "MFA factors":       2,
        "PAD / Liveness":    False,
        "Formal verif.":     False,
        "PQC-ready":         False,
        "Vote receipt":      False,
        "Edge deployment":   False,
        "Open source":       False,
    },
    "Ayed 2017\n(Ethereum)": {
        "EER (%)":           float("nan"),   # PIN-based, no biometric EER
        "FAR (%)":           float("nan"),
        "FRR (%)":           float("nan"),
        "Latency (ms)":      2100.0,         # blockchain tx confirmation
        "MFA factors":       1,
        "PAD / Liveness":    False,
        "Formal verif.":     False,
        "PQC-ready":         False,
        "Vote receipt":      True,           # blockchain receipt
        "Edge deployment":   False,
        "Open source":       True,
    },
    "FIDO2 /\nWebAuthn": {
        "EER (%)":           3.50,           # NIST SP 800-63B platform biometric
        "FAR (%)":           3.00,
        "FRR (%)":           4.00,
        "Latency (ms)":      190.0,
        "MFA factors":       2,
        "PAD / Liveness":    False,          # device-dependent, not guaranteed
        "Formal verif.":     False,
        "PQC-ready":         False,
        "Vote receipt":      False,
        "Edge deployment":   False,          # server-side, mobile authenticator
        "Open source":       False,
    },
    "ArcFace + PIN\n(Deng 2019)": {
        "EER (%)":           0.76,           # ArcFace LFW benchmark (server GPU)
        "FAR (%)":           0.60,
        "FRR (%)":           0.90,
        "Latency (ms)":      45.0,           # GPU server inference
        "MFA factors":       2,
        "PAD / Liveness":    False,
        "Formal verif.":     False,
        "PQC-ready":         False,
        "Vote receipt":      False,
        "Edge deployment":   False,          # requires GPU server
        "Open source":       True,
    },
}

BOOL_FEATURES = [
    "PAD / Liveness",
    "Formal verif.",
    "PQC-ready",
    "Vote receipt",
    "Edge deployment",
    "Open source",
]

NUMERIC_FEATURES = [
    "EER (%)",
    "FAR (%)",
    "FRR (%)",
    "Latency (ms)",
    "MFA factors",
]


def build_results() -> dict:
    return {
        "systems": list(SYSTEMS.keys()),
        "data": {
            sys_name: {
                k: (v if not isinstance(v, float) or not np.isnan(v) else None)
                for k, v in metrics.items()
            }
            for sys_name, metrics in SYSTEMS.items()
        },
        "source_notes": {
            "Bello 2021": "IEEE Access 2021, doi:10.1109/ACCESS.2021.XXXXXXX",
            "Sanchez 2020": "IET Biometrics 2020",
            "Ayed 2017": "IJAIS 2017 vol.12 no.6",
            "FIDO2": "FIDO Alliance WebAuthn L2; NIST SP 800-63B",
            "ArcFace+PIN": "CVPR 2019, LFW benchmark",
        },
    }


def plot_feature_heatmap():
    systems = list(SYSTEMS.keys())
    n_sys = len(systems)

    bool_values = np.array(
        [[int(SYSTEMS[s][f]) for f in BOOL_FEATURES] for s in systems],
        dtype=float,
    )

    fig, ax = plt.subplots(figsize=(10, 4.2))
    im = ax.imshow(bool_values.T, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)

    ax.set_xticks(range(n_sys))
    ax.set_xticklabels(systems, fontsize=9)
    ax.set_yticks(range(len(BOOL_FEATURES)))
    ax.set_yticklabels(BOOL_FEATURES, fontsize=9)

    for i, s in enumerate(systems):
        for j, feat in enumerate(BOOL_FEATURES):
            val = SYSTEMS[s][feat]
            text = "✓" if val else "✗"
            color = "black"
            ax.text(i, j, text, ha="center", va="center", fontsize=13, color=color, fontweight="bold")

    ax.set_title("Feature Comparison: TRIsecure V2 vs. Existing Systems", fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    yes_patch = mpatches.Patch(color="#4dac26", label="Supported")
    no_patch = mpatches.Patch(color="#d01c8b", label="Not supported")
    ax.legend(handles=[yes_patch, no_patch], loc="lower right", fontsize=8, framealpha=0.7)

    plt.tight_layout()
    out = FIGURES_DIR / "comparison_table.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_numeric_comparison():
    systems = list(SYSTEMS.keys())
    sys_labels = [s.replace("\n", " ") for s in systems]

    eer_vals = [SYSTEMS[s]["EER (%)"] for s in systems]
    lat_vals = [SYSTEMS[s]["Latency (ms)"] for s in systems]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    colors = ["#1a9850" if "Ours" in s else "#4393c3" for s in systems]

    # EER bar chart
    valid_eer = [(i, v) for i, v in enumerate(eer_vals) if not np.isnan(v)]
    idxs, vals = zip(*valid_eer) if valid_eer else ([], [])
    bars1 = ax1.bar(
        [sys_labels[i] for i in idxs], vals,
        color=[colors[i] for i in idxs], edgecolor="white", linewidth=0.8
    )
    ax1.set_ylabel("Equal Error Rate (%)", fontsize=10)
    ax1.set_title("EER Comparison", fontsize=11, fontweight="bold")
    ax1.set_ylim(0, max(vals) * 1.3 if vals else 5)
    ax1.tick_params(axis="x", labelsize=7.5)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars1, vals):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                 f"{val:.2f}%", ha="center", va="bottom", fontsize=8)

    # Latency bar chart
    bars2 = ax2.bar(sys_labels, lat_vals, color=colors, edgecolor="white", linewidth=0.8)
    ax2.set_ylabel("Authentication Latency (ms)", fontsize=10)
    ax2.set_title("Auth Latency Comparison", fontsize=11, fontweight="bold")
    ax2.set_ylim(0, max(lat_vals) * 1.25)
    ax2.tick_params(axis="x", labelsize=7.5)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars2, lat_vals):
        lbl = f"{val:.0f}" if not np.isnan(val) else "N/A"
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
                 lbl, ha="center", va="bottom", fontsize=8)

    ours = mpatches.Patch(color="#1a9850", label="TRIsecure V2 (Ours)")
    other = mpatches.Patch(color="#4393c3", label="Prior work")
    for ax in (ax1, ax2):
        ax.legend(handles=[ours, other], fontsize=8, framealpha=0.7)

    plt.tight_layout()
    out = FIGURES_DIR / "comparison_bar.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


def main():
    print("=== Comparison Table ===")
    results = build_results()
    out_json = Path(__file__).parent / "comparison_results.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved: {out_json}")

    print("\nGenerating figures...")
    plot_feature_heatmap()
    plot_numeric_comparison()

    print("\nSummary:")
    for sys_name, metrics in SYSTEMS.items():
        label = sys_name.replace("\n", " ")
        eer = metrics["EER (%)"]
        lat = metrics["Latency (ms)"]
        eer_str = f"{eer:.2f}%" if not np.isnan(eer) else "N/A"
        print(f"  {label:<30} EER={eer_str:<8} Latency={lat:.0f}ms")

    print("\nDone.")


if __name__ == "__main__":
    main()
