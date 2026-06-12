"""Tests for HybridKEM and DilithiumSigner (classical fallback path)."""
import pytest
from backend.crypto.pqc_kem import HybridKEM, DilithiumSigner


# --------------------------------------------------------------------------
# HybridKEM
# --------------------------------------------------------------------------

def test_kem_key_agreement_matches():
    kem = HybridKEM()
    pk, sk = kem.generate_keypair()
    ct, ss1 = kem.encapsulate(pk)
    ss2 = kem.decapsulate(sk, ct)
    assert ss1 == ss2
    assert len(ss1) == 32


def test_kem_different_ciphertexts():
    kem = HybridKEM()
    pk, _ = kem.generate_keypair()
    _, ct1 = kem.encapsulate(pk)[::-1]  # shared secret, not ct — swap for test
    ct_a = kem.encapsulate(pk)[0]
    ct_b = kem.encapsulate(pk)[0]
    assert ct_a != ct_b  # ephemeral keypair should differ each time


def test_kem_wrong_sk_gives_different_secret():
    kem = HybridKEM()
    pk, sk1 = kem.generate_keypair()
    _, sk2 = kem.generate_keypair()
    ct, ss1 = kem.encapsulate(pk)
    ss_wrong = kem.decapsulate(sk2, ct)
    assert ss1 != ss_wrong


def test_kem_key_sizes_dict():
    sizes = HybridKEM.key_sizes()
    assert "backend" in sizes
    assert sizes["shared_secret"] == 32


# --------------------------------------------------------------------------
# DilithiumSigner (Ed25519 fallback)
# --------------------------------------------------------------------------

def test_signer_sign_verify():
    s = DilithiumSigner()
    pk, sk = s.generate_keypair()
    msg = b"trisecure:vote:alice:candidate_a"
    sig = s.sign(msg, sk)
    assert s.verify(msg, sig, pk)


def test_signer_tampered_message_rejected():
    s = DilithiumSigner()
    pk, sk = s.generate_keypair()
    msg = b"original"
    sig = s.sign(msg, sk)
    assert not s.verify(b"tampered", sig, pk)


def test_signer_wrong_key_rejected():
    s = DilithiumSigner()
    pk1, sk1 = s.generate_keypair()
    pk2, _ = s.generate_keypair()
    sig = s.sign(b"vote", sk1)
    assert not s.verify(b"vote", sig, pk2)


def test_signer_algorithm_info():
    info = DilithiumSigner.algorithm_info()
    assert "algorithm" in info
    assert info["sig_size_bytes"] > 0
