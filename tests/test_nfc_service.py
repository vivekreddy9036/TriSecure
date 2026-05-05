"""NFC service tests — all run in simulation mode (no hardware required)."""

import pytest
from unittest.mock import patch


def _make_nfc():
    from hardware.nfc.nfc_service import NFCService
    svc = NFCService()
    # Force simulation mode without attempting hardware init
    svc._initialized = False
    return svc


def test_initialize_returns_false_without_hardware():
    """When board library is absent, initialize() returns False gracefully."""
    with patch.dict("sys.modules", {"board": None, "busio": None,
                                     "digitalio": None, "adafruit_pn532": None,
                                     "adafruit_pn532.spi": None}):
        from hardware.nfc.nfc_service import NFCService
        svc = NFCService()
        result = svc.initialize()
    assert result is False


def test_read_card_blocking_simulation_returns_uid():
    svc = _make_nfc()
    uid = svc.read_card_blocking(max_wait=1.0)
    assert isinstance(uid, str)
    assert len(uid) > 0


def test_write_voter_id_simulation_succeeds():
    svc = _make_nfc()
    result = svc.write_voter_id("12345678-1234-1234-1234-123456789012")
    assert result.success is True


def test_aes_payload_roundtrip():
    """NFCPayloadCrypto encrypt→decrypt must recover the original UUID."""
    import os
    from hardware.nfc.nfc_service import NFCPayloadCrypto

    secret = b"test-nfc-secret"
    crypto = NFCPayloadCrypto(secret)
    plaintext = b"12345678-1234-1234-1234-123456789012"  # 36 bytes

    encrypted = crypto.encrypt(plaintext)
    decrypted = crypto.decrypt(encrypted)

    assert decrypted[:36] == plaintext


def test_read_card_returns_nfc_read_result():
    svc = _make_nfc()
    result = svc.read_card()
    assert result.success is True
    assert result.uid is not None
