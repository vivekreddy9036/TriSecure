"""
Adversarial / security test suite for TRIsecure V2.

10 tests covering:
  1.  Spoof presentation rejected (PAD)
  2.  Consumed session token rejected (replay)
  3.  Expired session rejected
  4.  Hash chain tamper detection
  5.  Merkle proof tampering rejected
  6.  NFC clone / invalid UID rejected
  7.  Double-vote prevention
  8.  Rate-limit lockout after 5 failures
  9.  Face score below threshold rejected
  10. Audit trail completeness across all pipeline stages
"""

import hashlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from core.auth_pipeline import AuthenticationPipeline
from core.session_manager import SessionManager
from hardware.camera.pad_detector import PADDetector, PADResult
from models import Voter, Session
from security.merkle_tree import VoteMerkleTree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_voter(has_voted: bool = False) -> Voter:
    v = Voter(id=uuid4(), name="Test Voter", nfc_uid="DEADBEEF01")
    v.face_embedding = b"\x00" * 64
    v.has_voted = has_voted
    return v


def _make_repo(voter: Voter):
    repo = MagicMock()
    repo.find_by_nfc_uid.return_value = voter
    repo.find_by_id.return_value = voter
    return repo


def _make_pipeline(voter: Voter, pad_detector=None, biometric_fusion=None):
    return AuthenticationPipeline(
        voter_repository=_make_repo(voter),
        face_match_threshold=0.5,
        pad_detector=pad_detector,
        biometric_fusion=biometric_fusion,
    )


# ---------------------------------------------------------------------------
# Test 1: Spoof presentation rejected by PAD
# ---------------------------------------------------------------------------

def test_spoof_presentation_rejected():
    """PAD detector must reject a non-live face image."""
    voter = _make_voter()
    pad = MagicMock(spec=PADDetector)
    pad.detect.return_value = PADResult(
        is_live=False, confidence=0.12,
        attack_type="print", latency_ms=5.0
    )
    pipe = _make_pipeline(voter, pad_detector=pad)

    face_img = np.zeros((80, 80, 3), dtype=np.uint8)
    result = pipe.authenticate(
        nfc_uid="DEADBEEF01",
        face_embedding=b"\x00" * 64,
        face_verifier=lambda s, c: 0.95,
        face_image=face_img,
    )

    assert not result.success
    assert result.error_stage == "presentation_attack"
    pad.detect.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: Replay — consumed session token rejected
# ---------------------------------------------------------------------------

def test_consumed_session_rejected():
    """A one-time session token cannot be used twice."""
    voter = _make_voter()
    sm = SessionManager()
    session = sm.create_session(voter)
    token = session.token

    assert sm.validate_session(token)
    sm.consume_session(token)
    assert not sm.validate_session(token)


# ---------------------------------------------------------------------------
# Test 3: Expired session rejected
# ---------------------------------------------------------------------------

def test_expired_session_rejected():
    """Sessions past their expiry window must be invalid."""
    voter = _make_voter()
    sm = SessionManager(duration_seconds=1)
    session = sm.create_session(voter)
    token = session.token

    assert sm.validate_session(token)

    # Force-expire by backdating expires_at
    hashed = SessionManager._token_key(token)
    sm._active_sessions[hashed].expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=5)
    )

    assert not sm.validate_session(token)


# ---------------------------------------------------------------------------
# Test 4: Hash chain tamper detection
# ---------------------------------------------------------------------------

def test_hash_chain_tamper_detected(tmp_path):
    """Modifying any vote hash must break chain verification."""
    import sqlite3
    from repositories.vote_repository import SQLiteVoteRepository
    from models import Vote

    db = str(tmp_path / "tamper_test.db")
    repo = SQLiteVoteRepository(db)
    for i in range(5):
        repo.append_vote(Vote(voter_id=uuid4(), candidate=f"Candidate_{i}",
                              timestamp=datetime.now(timezone.utc)))

    assert repo.verify_chain(), "Intact chain must verify"

    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE votes SET current_hash = 'deadbeefdeadbeef' WHERE sequence = 3"
        )
        conn.commit()

    assert not repo.verify_chain(), "Tampered chain must fail verification"


# ---------------------------------------------------------------------------
# Test 5: Merkle proof tampering rejected
# ---------------------------------------------------------------------------

def test_merkle_proof_tamper_rejected():
    """A manipulated Merkle proof must not verify against the real root."""
    tree = VoteMerkleTree()
    leaves = [tree.add_leaf(f"vote_{i}".encode()) for i in range(8)]
    root = tree.get_root()

    proof = tree.get_proof(3)
    # Flip one byte in the first proof sibling (tuples: (hash_hex, position))
    corrupted = list(proof)
    if corrupted:
        orig_hash, pos = corrupted[0]
        bad_hash = bytes([b ^ 0xFF for b in bytes.fromhex(orig_hash)]).hex()
        corrupted[0] = (bad_hash, pos)

    assert not VoteMerkleTree.verify_proof(leaves[3], corrupted, root), \
        "Corrupted proof must be rejected"


# ---------------------------------------------------------------------------
# Test 6: NFC clone / invalid UID rejected
# ---------------------------------------------------------------------------

def test_nfc_clone_rejected():
    """An NFC UID not in the voter registry must be rejected."""
    repo = MagicMock()
    repo.find_by_nfc_uid.return_value = None   # unknown UID

    pipe = AuthenticationPipeline(voter_repository=repo)
    result = pipe.authenticate(nfc_uid="CLONED_UID_999")

    assert not result.success
    assert result.error_stage == "voter_lookup"


def test_empty_nfc_uid_rejected():
    """An empty NFC UID must be caught at Stage 1."""
    repo = MagicMock()
    pipe = AuthenticationPipeline(voter_repository=repo)
    result = pipe.authenticate(nfc_uid="")

    assert not result.success
    assert result.error_stage == "nfc_verification"


# ---------------------------------------------------------------------------
# Test 7: Double-vote prevention
# ---------------------------------------------------------------------------

def test_double_vote_prevented():
    """Voter flagged has_voted=True must be rejected at eligibility check."""
    voter = _make_voter(has_voted=True)
    pipe = _make_pipeline(voter)

    result = pipe.authenticate(
        nfc_uid="DEADBEEF01",
        face_embedding=b"\x00" * 64,
        face_verifier=lambda s, c: 0.95,
    )

    assert not result.success
    assert result.error_stage == "vote_eligibility"


# ---------------------------------------------------------------------------
# Test 8: Rate-limit lockout after 5 consecutive failures
# ---------------------------------------------------------------------------

def test_rate_limit_lockout():
    """After 5 failures within the window the pipeline must block."""
    repo = MagicMock()
    repo.find_by_nfc_uid.return_value = None   # always fail voter lookup

    pipe = AuthenticationPipeline(voter_repository=repo)
    uid = "RATE_TEST_UID"

    for _ in range(5):
        pipe.authenticate(nfc_uid=uid)

    result = pipe.authenticate(nfc_uid=uid)
    assert not result.success
    assert result.error_stage == "rate_limit"


# ---------------------------------------------------------------------------
# Test 9: Face score below threshold rejected
# ---------------------------------------------------------------------------

def test_low_face_score_rejected():
    """A face similarity below the configured threshold must fail auth."""
    voter = _make_voter()
    pipe = _make_pipeline(voter)

    result = pipe.authenticate(
        nfc_uid="DEADBEEF01",
        face_embedding=b"\xFF" * 64,   # different from stored b"\x00"*64
        face_verifier=lambda s, c: 0.20,  # well below 0.5 threshold
    )

    assert not result.success
    assert result.error_stage == "face_verification"


# ---------------------------------------------------------------------------
# Test 10: Audit trail completeness
# ---------------------------------------------------------------------------

def test_audit_trail_completeness():
    """All key pipeline stages must be logged to the audit system."""
    voter = _make_voter()
    audit = MagicMock()
    repo = _make_repo(voter)

    pipe = AuthenticationPipeline(
        voter_repository=repo,
        audit_logger=audit,
        face_match_threshold=0.5,
    )
    pipe.authenticate(
        nfc_uid="DEADBEEF01",
        face_embedding=b"\x00" * 64,
        face_verifier=lambda s, c: 0.95,
    )

    # NFC success, voter verified, face match, session issued must all be logged
    audit.log_nfc_read_success.assert_called_once()
    audit.log_voter_verified.assert_called_once()
    audit.log_face_match_success.assert_called_once()
    audit.log_session_issued.assert_called_once()
