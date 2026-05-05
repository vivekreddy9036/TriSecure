from datetime import datetime, timedelta, timezone
from uuid import uuid4

from core.session_manager import SessionManager
from models.voter import Voter


def test_session_lifecycle_and_one_time_use():
    manager = SessionManager(duration_seconds=60)
    voter = Voter(id=uuid4(), name="Alice", nfc_uid="ABCD")

    session = manager.create_session(voter)

    assert manager.validate_session(session.token) is True

    consumed = manager.consume_session(session.token)
    assert consumed is not None
    assert manager.validate_session(session.token) is False


def test_cleanup_expired_sessions():
    manager = SessionManager(duration_seconds=60)
    voter = Voter(id=uuid4(), name="Bob", nfc_uid="EFGH")

    session = manager.create_session(voter)
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    cleaned = manager.cleanup_expired_sessions()
    assert cleaned == 1
    assert manager.get_session(session.token) is None


def test_hashed_key_not_raw_token():
    """The raw token must never appear as a dict key in _active_sessions."""
    manager = SessionManager(duration_seconds=60)
    voter = Voter(id=uuid4(), name="Charlie", nfc_uid="XXYY")
    session = manager.create_session(voter)

    raw_token = session.token
    assert raw_token not in manager._active_sessions, (
        "Raw token stored as key — hashing not applied"
    )
    # But the session should still be retrievable via the raw token
    assert manager.validate_session(raw_token) is True


def test_deactivate_session():
    manager = SessionManager(duration_seconds=60)
    voter = Voter(id=uuid4(), name="Dave", nfc_uid="ZZZZ")
    session = manager.create_session(voter)

    assert manager.validate_session(session.token) is True
    manager.deactivate_session(session.token)
    assert manager.validate_session(session.token) is False
