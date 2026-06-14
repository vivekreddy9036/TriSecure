"""
Literature gap matrix: prior e-voting / biometric auth systems vs. capability dimensions.

Replaces the text-heavy related-work summary with a single visual table.
Saved to experiments/figures/gap_matrix.png at 300 DPI.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

FIGURES_DIR = Path(__file__).parent / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

# Rows: systems (oldest first, ours last)
SYSTEMS = [
    "Fujioka et al.\n(1992)",
    "Adida Helios\n(2008)",
    "Ayed\n(2017)",
    "Hardwick et al.\n(2018)",
    "Bello et al.\n(2021)",
    "Sánchez-Reillo\n(2020)",
    "FIDO2/WebAuthn\n(2019)",
    "TRIsecure V2\n(Ours)",
]

# Columns: capability dimensions
DIMS = [
    "Biometric\nAuth",
    "Liveness\nDetection\n(PAD)",
    "Formal\nVerification",
    "Post-Quantum\nCrypto",
    "End-to-End\nVerifiability",
    "Edge\nDeployment\n(<$100)",
    "Open\nSource",
]

# 0 = absent, 1 = partial, 2 = full
# fmt: off
MATRIX = np.array([
    # Bio  PAD   FV  PQC  E2EV  Edge  OSS
    [  0,   0,   0,   0,   1,   0,   0 ],  # Fujioka 1992
    [  0,   0,   0,   0,   2,   1,   1 ],  # Helios 2008
    [  0,   0,   0,   0,   1,   0,   0 ],  # Ayed 2017
    [  0,   0,   0,   0,   1,   0,   0 ],  # Hardwick 2018
    [  2,   0,   0,   0,   0,   1,   0 ],  # Bello 2021
    [  2,   0,   0,   0,   0,   2,   0 ],  # Sanchez 2020
    [  1,   0,   0,   0,   0,   1,   1 ],  # FIDO2
    [  2,   2,   2,   2,   2,   2,   1 ],  # TRIsecure V2
])
# fmt: on

COLORS = {0: "#e74c3c", 1: "#f39c12", 2: "#27ae60"}
LABELS = {0: "✗", 1: "~", 2: "✓"}

fig, ax = plt.subplots(figsize=(12, 5.5))
ax.set_xlim(-0.5, len(DIMS) - 0.5)
ax.set_ylim(-0.5, len(SYSTEMS) - 0.5)

for i, system in enumerate(SYSTEMS):
    for j, dim in enumerate(DIMS):
        val = MATRIX[i, j]
        color = COLORS[val]
        label = LABELS[val]
        # Highlight TRIsecure row
        alpha = 1.0 if i == len(SYSTEMS) - 1 else 0.82
        lw    = 2.0 if i == len(SYSTEMS) - 1 else 0.5
        rect = plt.Rectangle((j - 0.45, i - 0.45), 0.9, 0.9,
                              color=color, alpha=alpha,
                              linewidth=lw, edgecolor="white")
        ax.add_patch(rect)
        ax.text(j, i, label, ha="center", va="center",
                fontsize=13, fontweight="bold", color="white")

# Axes
ax.set_xticks(range(len(DIMS)))
ax.set_xticklabels(DIMS, fontsize=8, ha="center")
ax.set_yticks(range(len(SYSTEMS)))
ax.set_yticklabels(SYSTEMS, fontsize=9)
ax.xaxis.tick_top()
ax.xaxis.set_label_position("top")
ax.tick_params(axis="both", length=0)

# Highlight TRIsecure row border
for j in range(len(DIMS)):
    rect = plt.Rectangle((j - 0.45, len(SYSTEMS) - 1 - 0.45), 0.9, 0.9,
                          fill=False, edgecolor="#2c3e50", linewidth=2.5)
    ax.add_patch(rect)

# Legend
patches = [
    mpatches.Patch(color="#27ae60", label="Full support (✓)"),
    mpatches.Patch(color="#f39c12", label="Partial support (~)"),
    mpatches.Patch(color="#e74c3c", label="Not supported (✗)"),
]
ax.legend(handles=patches, loc="lower right", fontsize=8,
          bbox_to_anchor=(1.0, -0.12), ncol=3)

ax.set_title("Capability Gap Matrix: Prior Work vs. TRIsecure V2",
             fontsize=11, fontweight="bold", pad=40)

plt.tight_layout()
out = FIGURES_DIR / "gap_matrix.png"
plt.savefig(out, dpi=300, bbox_inches="tight")
plt.close()
print(f"Saved {out}")
