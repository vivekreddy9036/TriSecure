"""Tests for domain models: Voter, Vote, Session."""

import time
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from models.voter import Voter
from models.vote import Vote
from models.session import Session


# ── Voter ──────────────────────────────────────────────────────────────────

def test_voter_defaults():
    v = Voter(name="Alice", nfc_uid="AABBCCDD")
    assert v.has_voted is False
    assert v.face_embedding is None
    assert v.id is not None


def test_voter_mark_as_voted():
    v = Voter(name="Alice", nfc_uid="AABBCCDD")
    v.mark_as_voted()
    assert v.has_voted is True
    assert not v.is_eligible_to_vote()


def test_voter_is_eligible_before_voting():
    v = Voter(name="Bob", nfc_uid="11223344")
    assert v.is_eligible_to_vote() is True


def test_voter_str():
    v = Voter(name="Carol", nfc_uid="DEADBEEF")
    assert "Carol" in str(v)
    assert "has_voted" in str(v)


# ── Vote ───────────────────────────────────────────────────────────────────

def test_vote_hash_computed_on_init():
    v = Vote(voter_id=uuid4(), candidate="Alice")
    assert len(v.current_hash) == 64
    assert v.previous_hash == "0" * 64


def test_vote_verify_integrity_valid():
    v = Vote(voter_id=uuid4(), candidate="Alice")
    assert v.verify_integrity() is True


def test_vote_verify_integrity_tampered():
    v = Vote(voter_id=uuid4(), candidate="Alice")
    v.candidate = "Bob"  # tamper without recalculating hash
    assert v.verify_integrity() is False


def test_vote_hmac_sign_and_verify():
    key = b"test-signing-key"
    v = Vote(voter_id=uuid4(), candidate="Alice")
    v.vote_hmac = v.compute_vote_hmac(key)
    assert v.verify_vote_hmac(key) is True


def test_vote_hmac_wrong_key_fails():
    v = Vote(voter_id=uuid4(), candidate="Alice")
    v.vote_hmac = v.compute_vote_hmac(b"correct-key")
    assert v.verify_vote_hmac(b"wrong-key") is False


def test_vote_hmac_empty_fails():
    v = Vote(voter_id=uuid4(), candidate="Alice")
    assert v.verify_vote_hmac(b"any-key") is False


def test_vote_chain_link_genesis():
    v = Vote(voter_id=uuid4(), candidate="Alice")
    assert v.verify_chain_link(None) is True


def test_vote_chain_link_chained():
    v1 = Vote(voter_id=uuid4(), candidate="Alice")
    v2 = Vote(voter_id=uuid4(), candidate="Bob", previous_hash=v1.current_hash)
    v2.current_hash = v2.calculate_hash()
    assert v2.verify_chain_link(v1) is True


def test_vote_chain_link_broken():
    v1 = Vote(voter_id=uuid4(), candidate="Alice")
    v2 = Vote(voter_id=uuid4(), candidate="Bob", previous_hash="wrong" * 8)
    assert v2.verify_chain_link(v1) is False


def test_vote_str():
    v = Vote(voter_id=uuid4(), candidate="Alice")
    assert "Alice" in str(v)


# ── Session ────────────────────────────────────────────────────────────────

def test_session_is_valid_fresh():
    s = Session(voter_id=uuid4())
    assert s.is_valid() is True


def test_session_is_expired():
    s = Session(
        voter_id=uuid4(),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    assert s.is_expired() is True
    assert s.is_valid() is False


def test_session_mark_as_used():
    s = Session(voter_id=uuid4())
    s.mark_as_used()
    assert s.used is True
    assert s.is_valid() is False


def test_session_deactivate():
    s = Session(voter_id=uuid4())
    s.deactivate()
    assert s.is_active is False
    assert s.is_valid() is False


def test_session_remaining_seconds_positive():
    s = Session(voter_id=uuid4())
    remaining = s.get_remaining_seconds()
    assert remaining > 0
    assert remaining <= 60


def test_session_remaining_seconds_expired():
    s = Session(
        voter_id=uuid4(),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10)
    )
    assert s.get_remaining_seconds() == 0


def test_session_str():
    s = Session(voter_id=uuid4())
    assert "VALID" in str(s) or "INVALID" in str(s)
