import os
import pytest
import numpy as np


def _make_encryptor(key: str = "test-master-key-1234"):
    """Create an EmbeddingEncryptor with a deterministic test key."""
    os.environ["TRISECURE_MASTER_KEY"] = key
    from backend.crypto.encryptor import EmbeddingEncryptor
    enc = EmbeddingEncryptor()
    return enc


def test_encrypt_decrypt_roundtrip():
    enc = _make_encryptor()
    original = np.random.rand(512).astype(np.float32)

    enc_result = enc.encrypt(original)
    assert enc_result.success
    assert enc_result.ciphertext is not None

    dec_result = enc.decrypt(enc_result.ciphertext, enc_result.salt, enc_result.iv)
    assert dec_result.success
    np.testing.assert_array_almost_equal(dec_result.embedding, original, decimal=5)


def test_different_ivs_per_call():
    enc = _make_encryptor()
    emb = np.ones(512, dtype=np.float32)
    r1 = enc.encrypt(emb)
    r2 = enc.encrypt(emb)
    assert r1.iv != r2.iv  # Random IV per call


def test_wrong_key_fails_decryption():
    enc_a = _make_encryptor("key-alpha")
    enc_b = _make_encryptor("key-beta")
    emb = np.random.rand(256).astype(np.float32)

    enc_result = enc_a.encrypt(emb)
    dec_result = enc_b.decrypt(enc_result.ciphertext, enc_result.salt, enc_result.iv)
    # decryption should either fail or produce garbage (not equal to original)
    if dec_result.success:
        assert not np.allclose(dec_result.embedding, emb, atol=1e-3)
    else:
        assert not dec_result.success


def test_none_embedding_returns_failure():
    enc = _make_encryptor()
    result = enc.encrypt(None)
    assert not result.success
    assert result.error_message is not None


def test_no_master_key_raises(monkeypatch):
    monkeypatch.delenv("TRISECURE_MASTER_KEY", raising=False)
    from backend.crypto.encryptor import EmbeddingEncryptor
    with pytest.raises(ValueError, match="TRISECURE_MASTER_KEY"):
        EmbeddingEncryptor()
