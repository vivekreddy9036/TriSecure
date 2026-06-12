"""
Performance benchmarks for TRIsecure V2 cryptographic and biometric operations.

Run standalone::

    python experiments/benchmarks.py

Results are printed to stdout and saved to experiments/results_baseline.json.
All timings in milliseconds, N iterations per operation.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

# Make project root importable when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.analysis import mean_ci

logger = logging.getLogger(__name__)
_RESULTS_PATH = Path("experiments/results_baseline.json")


def _timer_ms(fn, n: int) -> List[float]:
    """Run fn() n times; return list of per-call durations in ms."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def bench_pbkdf2(n: int = 100) -> dict:
    """PBKDF2-HMAC-SHA256 (100 000 iterations) key derivation."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = os.urandom(16)
    key_material = b"benchmark-master-key"

    def _run():
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
        kdf.derive(key_material)

    times = _timer_ms(_run, n)
    m, lo, hi = mean_ci(np.array(times))
    return {"operation": "PBKDF2-HMAC-SHA256 (100k)", "n": n,
            "mean_ms": round(m, 3), "ci_low_ms": round(lo, 3), "ci_high_ms": round(hi, 3)}


def bench_argon2id(n: int = 20) -> dict:
    """Argon2id (t=3, m=65536, p=1) key derivation."""
    try:
        from argon2.low_level import hash_secret_raw, Type  # type: ignore
    except ImportError:
        return {"operation": "Argon2id", "error": "argon2-cffi not installed"}

    salt = os.urandom(16)
    secret = b"benchmark-master-key"

    def _run():
        hash_secret_raw(secret, salt, time_cost=3, memory_cost=65536,
                        parallelism=1, hash_len=32, type=Type.ID)

    times = _timer_ms(_run, n)
    m, lo, hi = mean_ci(np.array(times))
    return {"operation": "Argon2id (t=3, m=64MB)", "n": n,
            "mean_ms": round(m, 3), "ci_low_ms": round(lo, 3), "ci_high_ms": round(hi, 3)}


def bench_aes256_gcm(n: int = 1000) -> dict:
    """AES-256-GCM encrypt 2 KB payload (typical embedding size)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = os.urandom(32)
    iv = os.urandom(12)
    plaintext = os.urandom(2048)
    aesgcm = AESGCM(key)

    def _run():
        aesgcm.encrypt(iv, plaintext, None)

    times = _timer_ms(_run, n)
    m, lo, hi = mean_ci(np.array(times))
    return {"operation": "AES-256-GCM encrypt (2 KB)", "n": n,
            "mean_ms": round(m, 4), "ci_low_ms": round(lo, 4), "ci_high_ms": round(hi, 4)}


def bench_hmac_sha256(n: int = 10000) -> dict:
    """HMAC-SHA256 over 256-byte vote payload."""
    import hmac, hashlib
    key = os.urandom(32)
    msg = os.urandom(256)

    def _run():
        hmac.new(key, msg, hashlib.sha256).hexdigest()

    times = _timer_ms(_run, n)
    m, lo, hi = mean_ci(np.array(times))
    return {"operation": "HMAC-SHA256 (256 B)", "n": n,
            "mean_ms": round(m, 4), "ci_low_ms": round(lo, 4), "ci_high_ms": round(hi, 4)}


def bench_sha256_chain(n_votes: List[int] = None) -> List[dict]:
    """SHA-256 sequential chain verify at different chain lengths."""
    import hashlib

    if n_votes is None:
        n_votes = [10, 100, 1000, 10000]

    results = []
    for n in n_votes:
        hashes = []
        prev = "0" * 64
        for i in range(n):
            h = hashlib.sha256(f"candidate{i}{i}{prev}".encode()).hexdigest()
            hashes.append((prev, h))
            prev = h

        def _verify():
            p = "0" * 64
            for _, h in hashes:
                _ = hashlib.sha256(f"candidate0{0}{p}".encode()).hexdigest()
                p = h

        reps = max(3, 1000 // n)
        times = _timer_ms(_verify, reps)
        m, lo, hi = mean_ci(np.array(times))
        results.append({"operation": f"SHA-256 chain verify (n={n})", "n_votes": n, "reps": reps,
                         "mean_ms": round(m, 3), "ci_low_ms": round(lo, 3), "ci_high_ms": round(hi, 3)})
    return results


def bench_merkle_proof(n_votes: List[int] = None) -> List[dict]:
    """Merkle inclusion proof generation + verification at different tree sizes."""
    if n_votes is None:
        n_votes = [10, 100, 1000, 10000]

    from security.merkle_tree import VoteMerkleTree

    results = []
    for n in n_votes:
        tree = VoteMerkleTree()
        leaves = []
        for i in range(n):
            lh = tree.add_leaf(f"vote_{i}".encode())
            leaves.append(lh)
        root = tree.get_root()

        def _prove_verify():
            proof = tree.get_proof(n // 2)
            VoteMerkleTree.verify_proof(leaves[n // 2], proof, root)

        reps = max(3, 5000 // n)
        times = _timer_ms(_prove_verify, reps)
        m, lo, hi = mean_ci(np.array(times))
        results.append({"operation": f"Merkle prove+verify (n={n})", "n_votes": n, "reps": reps,
                         "mean_ms": round(m, 4), "ci_low_ms": round(lo, 4), "ci_high_ms": round(hi, 4)})
    return results


def bench_dilithium3(n: int = 200) -> dict:
    """Dilithium-3 or Ed25519 (fallback) sign + verify."""
    from backend.crypto.pqc_kem import DilithiumSigner
    signer = DilithiumSigner()
    pk, sk = signer.generate_keypair()
    msg = b"vote:abc123:candidate_a:2026-06-12T00:00:00Z"
    sig = signer.sign(msg, sk)
    info = signer.algorithm_info()

    def _run():
        s = signer.sign(msg, sk)
        signer.verify(msg, s, pk)

    times = _timer_ms(_run, n)
    m, lo, hi = mean_ci(np.array(times))
    return {"operation": f"{info['algorithm']} sign+verify", "n": n,
            "mean_ms": round(m, 3), "ci_low_ms": round(lo, 3), "ci_high_ms": round(hi, 3),
            "sig_size_bytes": info["sig_size_bytes"]}


def bench_kyber768(n: int = 200) -> dict:
    """HybridKEM (Kyber-768+X25519 or X25519 fallback) keygen + encap + decap."""
    from backend.crypto.pqc_kem import HybridKEM
    kem = HybridKEM()
    sizes = kem.key_sizes()

    def _run():
        pk, sk = kem.generate_keypair()
        ct, ss1 = kem.encapsulate(pk)
        ss2 = kem.decapsulate(sk, ct)

    times = _timer_ms(_run, n)
    m, lo, hi = mean_ci(np.array(times))
    return {"operation": f"HybridKEM ({sizes['backend']}) keygen+encap+decap", "n": n,
            "mean_ms": round(m, 3), "ci_low_ms": round(lo, 3), "ci_high_ms": round(hi, 3),
            "ct_size_bytes": sizes["ciphertext"]}


def run_all_benchmarks() -> dict:
    """Run every benchmark and return consolidated results dict."""
    print("\n" + "=" * 70)
    print("  TRIsecure V2 — Performance Benchmarks")
    print("=" * 70)

    results: Dict = {}

    def _run(label, fn):
        print(f"  [{label}] ...", end=" ", flush=True)
        try:
            r = fn()
            results[label] = r
            if isinstance(r, list):
                for row in r:
                    if "error" in row:
                        print(f"\n    {row.get('operation', label)}: SKIP ({row['error']})", end="")
                    else:
                        print(f"\n    {row['operation']}: {row['mean_ms']:.3f} ms (95% CI [{row['ci_low_ms']:.3f}, {row['ci_high_ms']:.3f}])", end="")
            elif "error" in r:
                print(f"SKIP ({r['error']})", end="")
            else:
                print(f"{r['mean_ms']:.3f} ms (95% CI [{r['ci_low_ms']:.3f}, {r['ci_high_ms']:.3f}])", end="")
            print()
        except Exception as exc:
            results[label] = {"error": str(exc)}
            print(f"ERROR: {exc}")

    _run("pbkdf2", bench_pbkdf2)
    _run("argon2id", bench_argon2id)
    _run("aes_gcm", bench_aes256_gcm)
    _run("hmac_sha256", bench_hmac_sha256)
    _run("sha256_chain", bench_sha256_chain)
    _run("merkle_proof", bench_merkle_proof)
    _run("dilithium3", bench_dilithium3)
    _run("kyber768", bench_kyber768)

    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved → {_RESULTS_PATH}")
    print("=" * 70 + "\n")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_all_benchmarks()
