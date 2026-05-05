"""Authentication pipeline tests."""

import pytest
from uuid import uuid4

from models.voter import Voter
from core.auth_pipeline import AuthenticationPipeline
from core.session_manager import SessionManager
from core.audit_logger import AuditLogger


def _make_pipeline(voter_repo, audit_repo=None):
    from repositories.audit_repository import SQLiteAuditRepository
    session_mgr = SessionManager(duration_seconds=60)
    audit = AuditLogger(repository=audit_repo)
    return AuthenticationPipeline(
        voter_repository=voter_repo,
        session_manager=session_mgr,
        audit_logger=audit,
        face_match_threshold=0.0,  # always pass face check in tests
    )


def test_full_auth_success(voter_repo):
    voter = Voter(name="Alice", nfc_uid="AABBCCDD")
    voter_repo.save(voter)

    pipeline = _make_pipeline(voter_repo)
    # face_verifier always returns 1.0 so face check passes
    result = pipeline.authenticate(
        nfc_uid="AABBCCDD",
        face_embedding=b"dummy",
        face_verifier=lambda s, c: 1.0,
    )
    assert result.success is True
    assert result.session is not None


def test_voter_not_found(voter_repo):
    pipeline = _make_pipeline(voter_repo)
    result = pipeline.authenticate(nfc_uid="UNKNOWN_UID")
    assert result.success is False
    assert result.error_stage == "voter_lookup"


def test_already_voted_blocked(voter_repo):
    voter = Voter(name="Bob", nfc_uid="BBBBBBBB")
    voter.mark_as_voted()
    voter_repo.save(voter)

    pipeline = _make_pipeline(voter_repo)
    result = pipeline.authenticate(nfc_uid="BBBBBBBB")
    assert result.success is False
    assert result.error_stage == "vote_eligibility"


def test_rate_limit_blocks_after_5_failures(voter_repo):
    pipeline = _make_pipeline(voter_repo)
    # 5 failures with unknown NFC UID
    for _ in range(5):
        pipeline.authenticate(nfc_uid="RATELIMITED")

    # 6th attempt should be blocked
    result = pipeline.authenticate(nfc_uid="RATELIMITED")
    assert result.success is False
    assert result.error_stage == "rate_limit"


def test_empty_nfc_uid_fails(voter_repo):
    pipeline = _make_pipeline(voter_repo)
    result = pipeline.authenticate(nfc_uid="")
    assert result.success is False
    assert result.error_stage in ("nfc_verification", "rate_limit")
