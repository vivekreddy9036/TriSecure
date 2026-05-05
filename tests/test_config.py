import os
import pytest
from config import Config, DeploymentMode


def test_default_config_values():
    cfg = Config()
    assert cfg.MODE == DeploymentMode.DEVELOPMENT
    assert cfg.DATABASE_PATH == "data/trisecure.db"
    assert cfg.SESSION_DURATION_SECONDS == 60
    assert cfg.CANDIDATES == ["Candidate A", "Candidate B", "Candidate C"]
    assert cfg.VOTE_SIGNING_KEY == ""
    assert cfg.AUDIT_HMAC_KEY == ""


def test_env_override_mode(monkeypatch):
    monkeypatch.setenv("TRISECURE_MODE", "production")
    cfg = Config()
    assert cfg.is_production()


def test_validate_production_missing_keys(monkeypatch):
    monkeypatch.setenv("TRISECURE_MODE", "production")
    monkeypatch.delenv("TRISECURE_MASTER_KEY", raising=False)
    monkeypatch.delenv("TRISECURE_VOTE_SIGNING_KEY", raising=False)
    monkeypatch.delenv("TRISECURE_NFC_SECRET", raising=False)
    monkeypatch.delenv("TRISECURE_AUDIT_HMAC_KEY", raising=False)
    cfg = Config()
    errors = cfg.validate_production()
    assert len(errors) > 0
    assert any("TRISECURE_MASTER_KEY" in e for e in errors)


def test_validate_production_with_keys(monkeypatch):
    monkeypatch.setenv("TRISECURE_MODE", "production")
    monkeypatch.setenv("TRISECURE_MASTER_KEY", "test-key")
    monkeypatch.setenv("TRISECURE_VOTE_SIGNING_KEY", "vote-key")
    monkeypatch.setenv("TRISECURE_NFC_SECRET", "nfc-key")
    monkeypatch.setenv("TRISECURE_AUDIT_HMAC_KEY", "audit-key")
    cfg = Config()
    assert cfg.validate_production() == []


def test_development_skips_validation():
    cfg = Config()  # default is DEVELOPMENT
    assert cfg.validate_production() == []
