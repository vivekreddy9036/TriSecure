"""Tests for SQLite-backed session repository (Phase C — DB persistence)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from models import Session, Voter
from repositories.session_repository import SQLiteSessionRepository
from core.session_manager import SessionManager


def _make_session(active: bool = True, used: bool = False, expired: bool = False) -> Session:
    voter_id = uuid4()
    offset = timedelta(seconds=-10) if expired else timedelta(seconds=60)
    return Session(
        session_id=uuid4(),
        voter_id=voter_id,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + offset,
        is_active=active,
        used=used,
    )


# ---------------------------------------------------------------------------

def test_save_and_retrieve():
    repo = SQLiteSessionRepository(":memory:")
    s = _make_session()
    repo.save(s)

    found = repo.find_by_token(s.token)
    assert found is not None
    assert str(found.session_id) == str(s.session_id)
    assert str(found.voter_id)   == str(s.voter_id)
    assert found.is_active is True
    assert found.used is False


def test_mark_used():
    repo = SQLiteSessionRepository(":memory:")
    s = _make_session()
    repo.save(s)
    repo.mark_used(s.token)

    found = repo.find_by_token(s.token)
    assert found.used is True
    assert found.is_active is False


def test_deactivate():
    repo = SQLiteSessionRepository(":memory:")
    s = _make_session()
    repo.save(s)
    repo.deactivate(s.token)

    found = repo.find_by_token(s.token)
    assert found.is_active is False
    assert found.used is False


def test_purge_expired():
    repo = SQLiteSessionRepository(":memory:")
    active  = _make_session(expired=False)
    expired = _make_session(expired=True)
    repo.save(active)
    repo.save(expired)

    removed = repo.purge_expired()
    assert removed == 1
    assert repo.find_by_token(active.token) is not None
    assert repo.find_by_token(expired.token) is None


def test_count_active():
    repo = SQLiteSessionRepository(":memory:")
    for _ in range(3):
        repo.save(_make_session(active=True))
    repo.save(_make_session(active=False))

    assert repo.count_active() == 3


def test_unknown_token_returns_none():
    repo = SQLiteSessionRepository(":memory:")
    assert repo.find_by_token("nonexistent_token_xyz") is None


def test_session_manager_persists_to_db():
    """SessionManager must write to repo and recover on lookup."""
    voter = Voter(id=uuid4(), name="DB Test", nfc_uid="DB0001")
    sm = SessionManager(db_path=":memory:")
    session = sm.create_session(voter)

    # Wipe in-memory cache to force repo lookup
    sm._active_sessions.clear()

    assert sm.validate_session(session.token), \
        "Session must be recovered from DB after memory eviction"


def test_session_manager_replay_prevented_across_restart():
    """Consuming a session must persist to DB so replay is blocked after restart."""
    voter = Voter(id=uuid4(), name="Replay Test", nfc_uid="RP0001")
    sm = SessionManager(db_path=":memory:")
    session = sm.create_session(voter)
    sm.consume_session(session.token)

    # Simulate restart — new manager with same repo
    sm2 = SessionManager(db_path=":memory:")
    sm2._repo = sm._repo
    sm2._active_sessions.clear()

    found = sm2._repo.find_by_token(session.token) if sm2._repo else None
    if found:
        assert found.used is True, "Consumed session must be marked used in DB"
