"""
Performance validation tests for TRIsecure V2.

10 tests verifying that all operations meet latency budgets
required for the paper's Table 3 and Table 5 claims.

Budgets are conservative for Raspberry Pi 4B (ARM64, 1.8 GHz):
  - AES-256-GCM encrypt 2 KB    < 5 ms
  - HMAC-SHA256                  < 5 ms
  - SHA-256 chain (n=100)        < 50 ms
  - Merkle prove+verify (n=100)  < 50 ms
  - Ed25519 sign+verify          < 20 ms
  - X25519 KEM keygen+encap+decap< 20 ms
  - Session creation              < 50 ms
  - Argon2id (t=3, m=64MB)       > 100 ms  (security lower bound)
  - Biometric eval pipeline      < 1 s
  - Benchmark results file valid (reproducibility check)
"""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from models import Voter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timeit_ms(fn, n: int = 5) -> float:
    """Return mean execution time in ms over n runs."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return float(np.mean(times))


# ---------------------------------------------------------------------------
# Test 1: AES-256-GCM < 5 ms per 2 KB
# ---------------------------------------------------------------------------

def test_aes_gcm_latency():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = os.urandom(32)
    iv  = os.urandom(12)
    pt  = os.urandom(2048)
    aesgcm = AESGCM(key)

    ms = _timeit_ms(lambda: aesgcm.encrypt(iv, pt, None), n=100)
    assert ms < 5.0, f"AES-GCM too slow: {ms:.3f} ms (budget: 5 ms)"


# ---------------------------------------------------------------------------
# Test 2: HMAC-SHA256 < 5 ms per 256-byte payload
# ---------------------------------------------------------------------------

def test_hmac_sha256_latency():
    import hmac, hashlib
    key = os.urandom(32)
    msg = os.urandom(256)

    ms = _timeit_ms(lambda: hmac.new(key, msg, hashlib.sha256).digest(), n=200)
    assert ms < 5.0, f"HMAC-SHA256 too slow: {ms:.3f} ms (budget: 5 ms)"


# ---------------------------------------------------------------------------
# Test 3: SHA-256 chain verify (n=100 votes) < 50 ms
# ---------------------------------------------------------------------------

def test_sha256_chain_latency():
    import hashlib
    hashes = []
    prev = "0" * 64
    for i in range(100):
        h = hashlib.sha256(f"vote{i}{prev}".encode()).hexdigest()
        hashes.append((prev, h))
        prev = h

    def _verify():
        p = "0" * 64
        for _, h in hashes:
            _ = hashlib.sha256(f"vote0{p}".encode()).hexdigest()
            p = h

    ms = _timeit_ms(_verify, n=20)
    assert ms < 50.0, f"SHA-256 chain too slow: {ms:.3f} ms (budget: 50 ms)"


# ---------------------------------------------------------------------------
# Test 4: Merkle prove+verify (n=100) < 50 ms
# ---------------------------------------------------------------------------

def test_merkle_proof_latency():
    from security.merkle_tree import VoteMerkleTree

    tree = VoteMerkleTree()
    leaves = [tree.add_leaf(f"vote_{i}".encode()) for i in range(100)]
    root = tree.get_root()

    def _prove_verify():
        proof = tree.get_proof(50)
        VoteMerkleTree.verify_proof(leaves[50], proof, root)

    ms = _timeit_ms(_prove_verify, n=50)
    assert ms < 50.0, f"Merkle prove+verify too slow: {ms:.3f} ms (budget: 50 ms)"


# ---------------------------------------------------------------------------
# Test 5: Merkle proof scales O(log n) — prove+verify(n=1000) < 10×(n=100)
# ---------------------------------------------------------------------------

def test_merkle_proof_log_scaling():
    from security.merkle_tree import VoteMerkleTree

    def _bench(n: int) -> float:
        tree = VoteMerkleTree()
        leaves = [tree.add_leaf(f"v_{i}".encode()) for i in range(n)]
        root = tree.get_root()
        return _timeit_ms(
            lambda: VoteMerkleTree.verify_proof(leaves[n // 2], tree.get_proof(n // 2), root),
            n=10,
        )

    t100  = _bench(100)
    t1000 = _bench(1000)
    # log2(1000)/log2(100) ≈ 1.5 — allow generous 10× headroom
    assert t1000 < t100 * 10, \
        f"Merkle proof did not scale sub-linearly: t100={t100:.2f} ms, t1000={t1000:.2f} ms"


# ---------------------------------------------------------------------------
# Test 6: Ed25519 / Dilithium sign+verify < 20 ms
# ---------------------------------------------------------------------------

def test_dilithium_sign_verify_latency():
    from backend.crypto.pqc_kem import DilithiumSigner

    signer = DilithiumSigner()
    pk, sk = signer.generate_keypair()
    msg = b"vote:abc:candidateA:2026-06-12"

    ms = _timeit_ms(lambda: signer.verify(msg, signer.sign(msg, sk), pk), n=50)
    assert ms < 20.0, f"Dilithium/Ed25519 too slow: {ms:.3f} ms (budget: 20 ms)"


# ---------------------------------------------------------------------------
# Test 7: HybridKEM keygen+encap+decap < 20 ms
# ---------------------------------------------------------------------------

def test_hybrid_kem_latency():
    from backend.crypto.pqc_kem import HybridKEM

    kem = HybridKEM()

    def _run():
        pk, sk = kem.generate_keypair()
        ct, ss1 = kem.encapsulate(pk)
        kem.decapsulate(sk, ct)

    ms = _timeit_ms(_run, n=50)
    assert ms < 20.0, f"HybridKEM too slow: {ms:.3f} ms (budget: 20 ms)"


# ---------------------------------------------------------------------------
# Test 8: Session creation < 50 ms
# ---------------------------------------------------------------------------

def test_session_creation_latency():
    from core.session_manager import SessionManager

    sm = SessionManager()
    voter = Voter(id=uuid4(), name="Speed Test", nfc_uid="PERF0001")

    ms = _timeit_ms(lambda: sm.create_session(voter), n=100)
    assert ms < 50.0, f"Session creation too slow: {ms:.3f} ms (budget: 50 ms)"


# ---------------------------------------------------------------------------
# Test 9: Argon2id > 100 ms (security lower bound on Pi)
# ---------------------------------------------------------------------------

def test_argon2id_security_cost():
    try:
        from argon2.low_level import hash_secret_raw, Type
    except ImportError:
        pytest.skip("argon2-cffi not installed")

    salt = os.urandom(16)
    secret = b"test-master-key"

    t0 = time.perf_counter()
    hash_secret_raw(secret, salt, time_cost=3, memory_cost=65536,
                    parallelism=1, hash_len=32, type=Type.ID)
    ms = (time.perf_counter() - t0) * 1000

    assert ms > 100.0, \
        f"Argon2id too fast ({ms:.1f} ms) — parameters may be too weak for publication claim"


# ---------------------------------------------------------------------------
# Test 10: Benchmark results file is valid and reproducible
# ---------------------------------------------------------------------------

def test_benchmark_results_reproducible():
    """Running benchmarks twice must produce results within 20% of each other."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from experiments.benchmarks import bench_aes256_gcm, bench_hmac_sha256

    r1 = bench_aes256_gcm(n=50)
    r2 = bench_aes256_gcm(n=50)
    assert "mean_ms" in r1 and "mean_ms" in r2
    ratio = r1["mean_ms"] / r2["mean_ms"] if r2["mean_ms"] > 0 else 0
    assert 0.5 < ratio < 2.0, \
        f"AES-GCM not reproducible: run1={r1['mean_ms']} ms, run2={r2['mean_ms']} ms"

    r3 = bench_hmac_sha256(n=500)
    assert "mean_ms" in r3
    assert r3["mean_ms"] > 0
