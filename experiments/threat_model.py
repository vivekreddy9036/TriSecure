"""
Threat model matrix: 12 e-voting attack vectors × 6 TRIsecure V2 defence layers.

Coverage scores:
  0 — not defended
  1 — partially defended
  2 — fully defended

Output:
  experiments/threat_model_results.json
  experiments/figures/threat_model_heatmap.png (300 DPI)
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# ---------------------------------------------------------------------------
# Attack vectors (rows)
# ---------------------------------------------------------------------------
ATTACKS = [
    "Replay attack",
    "Spoofing / presentation attack",
    "Man-in-the-middle",
    "Brute-force / dictionary",
    "Double-voting",
    "Ballot stuffing",
    "Vote coercion",
    "Insider threat",
    "Denial of service",
    "Quantum adversary",
    "Physical device theft",
    "Audit trail tampering",
]

# ---------------------------------------------------------------------------
# Defence layers (columns)
# ---------------------------------------------------------------------------
DEFENCES = [
    "Rate limiter\n(DFA stage 1)",
    "PAD liveness\n(Stage 5)",
    "Bayesian\nfusion (NFC+face)",
    "AES-256-GCM\n+ Argon2id",
    "Hash-chain\n+ Merkle proof",
    "PQC signatures\n(Dilithium-3)",
]

# ---------------------------------------------------------------------------
# Coverage matrix [attack × defence]
# 0 = no defence, 1 = partial, 2 = full
# ---------------------------------------------------------------------------
# Rationale strings for JSON export
RATIONALE = {
    # (attack, defence): rationale
    ("Replay attack",               "Rate limiter\n(DFA stage 1)"):    (2, "Sliding-window rate limiter blocks rapid replay; DFA enforces IDLE→RATE_CHECK before any replay attempt."),
    ("Replay attack",               "PAD liveness\n(Stage 5)"):        (1, "Replayed video/photo blocked by PAD; physical credential replay (NFC cloning) not covered."),
    ("Replay attack",               "Bayesian\nfusion (NFC+face)"):    (2, "Session tokens are 60s TTL, one-time-use (used flag in DB); NFC UID required fresh per session."),
    ("Replay attack",               "AES-256-GCM\n+ Argon2id"):        (1, "Encrypted embeddings prevent offline replay; bearer token replay still possible within TTL."),
    ("Replay attack",               "Hash-chain\n+ Merkle proof"):     (1, "Hash chain detects duplicate vote records; does not prevent token replay before recording."),
    ("Replay attack",               "PQC signatures\n(Dilithium-3)"):  (0, "PQC does not directly mitigate replay; session layer handles it."),

    ("Spoofing / presentation attack", "Rate limiter\n(DFA stage 1)"): (1, "Limits spoof attempt rate; determined attacker can retry after cooldown."),
    ("Spoofing / presentation attack", "PAD liveness\n(Stage 5)"):     (2, "MiniFASNetV2 detects printed photo and video replay attacks; APCER_print=5%, APCER_replay=10%."),
    ("Spoofing / presentation attack", "Bayesian\nfusion (NFC+face)"): (1, "Requires valid NFC card in addition to face; reduces but does not eliminate spoofing risk."),
    ("Spoofing / presentation attack", "AES-256-GCM\n+ Argon2id"):    (0, "Encryption at rest does not defend against live spoofing."),
    ("Spoofing / presentation attack", "Hash-chain\n+ Merkle proof"):  (0, "Integrity layer does not defend against input spoofing."),
    ("Spoofing / presentation attack", "PQC signatures\n(Dilithium-3)"): (0, "Signature layer does not defend against biometric spoofing."),

    ("Man-in-the-middle",           "Rate limiter\n(DFA stage 1)"):    (0, "Rate limiter does not address network-layer MITM."),
    ("Man-in-the-middle",           "PAD liveness\n(Stage 5)"):        (0, "PAD is local; does not address MITM on session transport."),
    ("Man-in-the-middle",           "Bayesian\nfusion (NFC+face)"):    (1, "Local biometric decision reduces reliance on network auth; session token still transmittable."),
    ("Man-in-the-middle",           "AES-256-GCM\n+ Argon2id"):       (2, "AES-256-GCM with authenticated encryption; session token sent over TLS (assumed channel)."),
    ("Man-in-the-middle",           "Hash-chain\n+ Merkle proof"):     (1, "Hash-chained votes detect tampering post-record; MITM during submission window is not covered."),
    ("Man-in-the-middle",           "PQC signatures\n(Dilithium-3)"):  (2, "Dilithium-3 vote signatures prevent forged or altered votes in transit; quantum-resistant."),

    ("Brute-force / dictionary",    "Rate limiter\n(DFA stage 1)"):    (2, "DFA stage 1: 5 failures per 300 s per NFC UID; attacker blocked before reaching biometric stage."),
    ("Brute-force / dictionary",    "PAD liveness\n(Stage 5)"):        (1, "PAD prevents rapid face-image cycling; latency overhead also limits throughput."),
    ("Brute-force / dictionary",    "Bayesian\nfusion (NFC+face)"):    (2, "Requires physical NFC card; brute-force on face alone is rejected without card."),
    ("Brute-force / dictionary",    "AES-256-GCM\n+ Argon2id"):       (2, "Argon2id (64 MB, t=3) makes offline brute-force on stolen encrypted embeddings infeasible."),
    ("Brute-force / dictionary",    "Hash-chain\n+ Merkle proof"):     (0, "Brute-force at auth stage; vote integrity layer not relevant here."),
    ("Brute-force / dictionary",    "PQC signatures\n(Dilithium-3)"):  (0, "PQC does not address online brute-force on biometric system."),

    ("Double-voting",               "Rate limiter\n(DFA stage 1)"):    (1, "Rate limiter slows repeated attempts but does not prevent a second auth for a different NFC clone."),
    ("Double-voting",               "PAD liveness\n(Stage 5)"):        (0, "PAD verifies liveness but not has_voted status."),
    ("Double-voting",               "Bayesian\nfusion (NFC+face)"):    (2, "DFA ELIGIBILITY_CHECK: has_voted=True → REJECTED before face stage. Formally proved (property 5)."),
    ("Double-voting",               "AES-256-GCM\n+ Argon2id"):       (0, "Encryption does not address double-vote logic."),
    ("Double-voting",               "Hash-chain\n+ Merkle proof"):     (2, "Append-only hash chain with unique vote_id; duplicate submission breaks chain integrity."),
    ("Double-voting",               "PQC signatures\n(Dilithium-3)"):  (1, "Signed vote_id prevents silent substitution; chain-level uniqueness is primary defence."),

    ("Ballot stuffing",             "Rate limiter\n(DFA stage 1)"):    (2, "Rate limiter + one-voter-one-ballot enforced by DFA eligibility stage."),
    ("Ballot stuffing",             "PAD liveness\n(Stage 5)"):        (1, "PAD prevents dummy face images; requires physical voter presence."),
    ("Ballot stuffing",             "Bayesian\nfusion (NFC+face)"):    (2, "Each NFC card is unique; registered voter set is closed at enrollment."),
    ("Ballot stuffing",             "AES-256-GCM\n+ Argon2id"):       (0, "Encryption does not address ballot stuffing."),
    ("Ballot stuffing",             "Hash-chain\n+ Merkle proof"):     (2, "External verifier can audit Merkle root against registered voter count; stuffed votes break consistency."),
    ("Ballot stuffing",             "PQC signatures\n(Dilithium-3)"):  (1, "Signed ballots traceable; stuffed unsigned ballots would fail signature verification."),

    ("Vote coercion",               "Rate limiter\n(DFA stage 1)"):    (0, "Rate limiter does not address coercion."),
    ("Vote coercion",               "PAD liveness\n(Stage 5)"):        (1, "Physical presence at camera makes remote coercion harder; does not prevent in-person coercion."),
    ("Vote coercion",               "Bayesian\nfusion (NFC+face)"):    (1, "Face biometric confirms voter identity; does not prevent coerced compliance."),
    ("Vote coercion",               "AES-256-GCM\n+ Argon2id"):       (0, "Encryption does not address coercion."),
    ("Vote coercion",               "Hash-chain\n+ Merkle proof"):     (0, "Vote integrity does not address coercion."),
    ("Vote coercion",               "PQC signatures\n(Dilithium-3)"):  (0, "PQC does not address coercion. (Future: deniable voting / panic PIN.)"),

    ("Insider threat",              "Rate limiter\n(DFA stage 1)"):    (1, "Rate limiter applies equally to insiders; privileged access still possible."),
    ("Insider threat",              "PAD liveness\n(Stage 5)"):        (0, "Insider with DB access can bypass PAD."),
    ("Insider threat",              "Bayesian\nfusion (NFC+face)"):    (1, "Biometric binding reduces insider ability to vote as another person without physical card+face."),
    ("Insider threat",              "AES-256-GCM\n+ Argon2id"):       (2, "Encrypted embeddings + Argon2id: insider cannot extract plaintext templates without voter PIN/key."),
    ("Insider threat",              "Hash-chain\n+ Merkle proof"):     (2, "Immutable append-only audit log; insider modifications break hash chain and are detectable."),
    ("Insider threat",              "PQC signatures\n(Dilithium-3)"):  (1, "Vote signatures non-repudiable; insider cannot forge signed votes without signing key."),

    ("Denial of service",           "Rate limiter\n(DFA stage 1)"):    (2, "Per-UID sliding window prevents single-UID exhaustion; PAD latency limits throughput of DoS via face."),
    ("Denial of service",           "PAD liveness\n(Stage 5)"):        (1, "PAD adds 15 ms overhead; limits face-submission DoS rate."),
    ("Denial of service",           "Bayesian\nfusion (NFC+face)"):    (0, "Fusion computation is lightweight; does not defend against network-level DoS."),
    ("Denial of service",           "AES-256-GCM\n+ Argon2id"):       (0, "Crypto layer does not address DoS."),
    ("Denial of service",           "Hash-chain\n+ Merkle proof"):     (0, "Integrity layer does not address DoS."),
    ("Denial of service",           "PQC signatures\n(Dilithium-3)"):  (0, "PQC does not address DoS."),

    ("Quantum adversary",           "Rate limiter\n(DFA stage 1)"):    (0, "Rate limiter is not cryptographic; not relevant to quantum threat."),
    ("Quantum adversary",           "PAD liveness\n(Stage 5)"):        (0, "PAD is not cryptographic."),
    ("Quantum adversary",           "Bayesian\nfusion (NFC+face)"):    (0, "Biometric fusion not cryptographic; quantum adversary could break classical session KEM."),
    ("Quantum adversary",           "AES-256-GCM\n+ Argon2id"):       (2, "AES-256-GCM is quantum-resistant (Grover's requires 2^128 work); Argon2id key derivation unaffected."),
    ("Quantum adversary",           "Hash-chain\n+ Merkle proof"):     (2, "SHA-256 is quantum-resistant (128-bit post-quantum security); Merkle proofs remain secure."),
    ("Quantum adversary",           "PQC signatures\n(Dilithium-3)"):  (2, "Dilithium-3 (NIST FIPS 204, ML-DSA-65) and Kyber-768 (FIPS 203, ML-KEM-768) are quantum-resistant."),

    ("Physical device theft",       "Rate limiter\n(DFA stage 1)"):    (0, "Rate limiter does not prevent physical access."),
    ("Physical device theft",       "PAD liveness\n(Stage 5)"):        (1, "Stolen device still requires live face at camera; printed photo attempts blocked by PAD."),
    ("Physical device theft",       "Bayesian\nfusion (NFC+face)"):    (2, "Stolen device without voter's NFC card and live face cannot authenticate."),
    ("Physical device theft",       "AES-256-GCM\n+ Argon2id"):       (2, "All data at rest encrypted; stolen SD card yields only ciphertext without voter-derived key."),
    ("Physical device theft",       "Hash-chain\n+ Merkle proof"):     (1, "Past votes are immutably recorded; stolen device does not allow retroactive modification."),
    ("Physical device theft",       "PQC signatures\n(Dilithium-3)"):  (1, "Signing keys stored encrypted; physical access without key derivation does not yield signing capability."),

    ("Audit trail tampering",       "Rate limiter\n(DFA stage 1)"):    (0, "Rate limiter logs events but does not protect the audit store."),
    ("Audit trail tampering",       "PAD liveness\n(Stage 5)"):        (0, "PAD does not protect audit store."),
    ("Audit trail tampering",       "Bayesian\nfusion (NFC+face)"):    (0, "Fusion does not protect audit store."),
    ("Audit trail tampering",       "AES-256-GCM\n+ Argon2id"):       (1, "Audit events in SQLite; encryption of DB at OS level partial defence; no HMAC on audit rows."),
    ("Audit trail tampering",       "Hash-chain\n+ Merkle proof"):     (2, "Vote records hash-chained; any modification breaks chain. External Merkle root can be published for verification."),
    ("Audit trail tampering",       "PQC signatures\n(Dilithium-3)"):  (2, "Dilithium-3 signatures on vote records; forged entries lack valid signature and break chain."),
}


def build_matrix():
    n_attacks = len(ATTACKS)
    n_def = len(DEFENCES)
    matrix = np.zeros((n_attacks, n_def), dtype=int)
    rationale_export = {}

    for i, atk in enumerate(ATTACKS):
        rationale_export[atk] = {}
        for j, defn in enumerate(DEFENCES):
            key = (atk, defn)
            if key in RATIONALE:
                score, reason = RATIONALE[key]
            else:
                score, reason = 0, "Not applicable."
            matrix[i, j] = score
            rationale_export[atk][defn] = {"score": int(score), "rationale": reason}

    return matrix, rationale_export


def plot_heatmap(matrix: np.ndarray):
    fig, ax = plt.subplots(figsize=(13, 7))

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "threat_cmap", ["#d73027", "#fee08b", "#1a9850"], N=3
    )
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=2)

    ax.set_xticks(range(len(DEFENCES)))
    ax.set_xticklabels(DEFENCES, fontsize=9)
    ax.set_yticks(range(len(ATTACKS)))
    ax.set_yticklabels(ATTACKS, fontsize=9)

    score_labels = {0: "✗\n(0)", 1: "~\n(1)", 2: "✓\n(2)"}
    score_colors = {0: "white", 1: "black", 2: "white"}
    for i in range(len(ATTACKS)):
        for j in range(len(DEFENCES)):
            score = int(matrix[i, j])
            ax.text(j, i, score_labels[score], ha="center", va="center",
                    fontsize=8, color=score_colors[score], fontweight="bold", linespacing=1.3)

    ax.set_title(
        "TRIsecure V2 — Threat Model Coverage Matrix\n"
        "✗=Not defended (0)  ~=Partial (1)  ✓=Fully defended (2)",
        fontsize=11, fontweight="bold"
    )

    # Column totals
    col_totals = matrix.sum(axis=0)
    max_possible = len(ATTACKS) * 2
    for j, total in enumerate(col_totals):
        ax.text(j, len(ATTACKS) + 0.1, f"Σ={total}/{max_possible}",
                ha="center", va="bottom", fontsize=8, color="#333")

    ax.set_xlim(-0.5, len(DEFENCES) - 0.5)
    ax.set_ylim(len(ATTACKS) - 0.5, -0.5)
    ax.spines[["top", "right", "bottom", "left"]].set_visible(False)

    plt.tight_layout()
    out = Path(__file__).parent / "figures" / "threat_model_heatmap.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out}")


def main():
    print("=== Threat Model Matrix ===")
    matrix, rationale = build_matrix()

    results = {
        "attacks": ATTACKS,
        "defences": DEFENCES,
        "matrix": matrix.tolist(),
        "rationale": rationale,
        "row_totals": {atk: int(matrix[i].sum()) for i, atk in enumerate(ATTACKS)},
        "col_totals": {defn: int(matrix[:, j].sum()) for j, defn in enumerate(DEFENCES)},
        "overall_coverage_pct": round(float(matrix.sum()) / (len(ATTACKS) * len(DEFENCES) * 2) * 100, 1),
    }

    out_json = Path(__file__).parent / "threat_model_results.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved: {out_json}")

    print(f"\n  Overall threat coverage: {results['overall_coverage_pct']:.1f}%")
    print("\n  Per-attack totals (out of 12):")
    for atk, total in results["row_totals"].items():
        print(f"    {atk:<40} {total:2d}/12")

    print("\nGenerating heatmap figure...")
    plot_heatmap(matrix)
    print("Done.")


if __name__ == "__main__":
    main()
