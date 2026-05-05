"""Extended repository tests — encryption paths and audit coverage."""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from models.voter import Voter
from models.vote import Vote
from models.audit_event import AuditEvent, EventType, EventStatus
from repositories.voter_repository import SQLiteVoterRepository
from repositories.audit_repository import SQLiteAuditRepository


# ── VoterRepository — encrypted path ──────────────────────────────────────

@pytest.fixture
def encrypted_voter_repo(tmp_path):
    from backend.crypto.encryptor import EmbeddingEncryptor
    import os
    os.environ["TRISECURE_MASTER_KEY"] = "test-master-key-for-encryption"
    encryptor = EmbeddingEncryptor()
    return SQLiteVoterRepository(str(tmp_path / "enc_test.db"), encryptor=encryptor)


def test_voter_save_and_retrieve_with_encryption(encrypted_voter_repo):
    import numpy as np
    embedding = np.random.randn(512).astype(np.float32)
    voter = Voter(name="Alice", nfc_uid="ENCTEST01")
    voter.face_embedding = embedding.tobytes()
    encrypted_voter_repo.save(voter)

    found = encrypted_voter_repo.find_by_id(voter.id)
    assert found is not None
    assert found.name == "Alice"


def test_voter_delete(tmp_path):
    repo = SQLiteVoterRepository(str(tmp_path / "del_test.db"))
    voter = Voter(name="DeleteMe", nfc_uid="DELUID001")
    repo.save(voter)
    assert repo.find_by_id(voter.id) is not None

    deleted = repo.delete(voter.id)
    assert deleted is True
    assert repo.find_by_id(voter.id) is None


def test_voter_delete_nonexistent(tmp_path):
    repo = SQLiteVoterRepository(str(tmp_path / "del2_test.db"))
    assert repo.delete(uuid4()) is False


def test_voter_save_updates_existing(tmp_path):
    repo = SQLiteVoterRepository(str(tmp_path / "upd_test.db"))
    voter = Voter(name="Original", nfc_uid="UPDUID001")
    repo.save(voter)

    voter.name = "Updated"
    repo.save(voter)

    found = repo.find_by_id(voter.id)
    assert found.name == "Updated"


# ── AuditRepository extended ───────────────────────────────────────────────

@pytest.fixture
def audit_repo(tmp_path):
    return SQLiteAuditRepository(str(tmp_path / "audit_ext.db"))


def test_audit_save_and_find_by_id(audit_repo):
    event = AuditEvent(
        event_type=EventType.VOTE_CAST,
        status=EventStatus.SUCCESS,
        voter_id=uuid4(),
        message="Vote cast",
    )
    audit_repo.save(event)
    found = audit_repo.find_by_id(event.event_id)
    assert found is not None
    assert found.event_type == EventType.VOTE_CAST


def test_audit_find_by_voter(audit_repo):
    voter_id = uuid4()
    for msg in ("Event 1", "Event 2"):
        event = AuditEvent(
            event_type=EventType.NFC_READ_SUCCESS,
            status=EventStatus.SUCCESS,
            voter_id=voter_id,
            message=msg,
        )
        audit_repo.save(event)

    events = audit_repo.find_by_voter(voter_id)
    assert len(events) == 2


def test_audit_find_by_type(audit_repo):
    for _ in range(3):
        audit_repo.save(AuditEvent(
            event_type=EventType.FACE_MATCH_FAILED,
            status=EventStatus.FAILURE,
            message="failure",
        ))
    audit_repo.save(AuditEvent(
        event_type=EventType.VOTE_CAST,
        status=EventStatus.SUCCESS,
        message="vote",
    ))

    failures = audit_repo.find_by_type(EventType.FACE_MATCH_FAILED)
    assert len(failures) == 3


def test_audit_get_all(audit_repo):
    for i in range(5):
        audit_repo.save(AuditEvent(
            event_type=EventType.NFC_READ_SUCCESS,
            status=EventStatus.SUCCESS,
            message=f"Event {i}",
        ))
    assert len(audit_repo.get_all()) >= 5


# ── VoteRepository — HMAC signing path ────────────────────────────────────

def test_vote_repo_hmac_signing_and_verification(tmp_path):
    from repositories.vote_repository import SQLiteVoteRepository

    key = b"strong-signing-key-32-bytes-long!"
    repo = SQLiteVoteRepository(str(tmp_path / "hmac_test.db"), signing_key=key)

    v1 = Vote(voter_id=uuid4(), candidate="Alice")
    v2 = Vote(voter_id=uuid4(), candidate="Bob")
    repo.append_vote(v1)
    repo.append_vote(v2)

    assert repo.verify_chain() is True


def test_vote_repo_find_nonexistent(tmp_path):
    from repositories.vote_repository import SQLiteVoteRepository
    repo = SQLiteVoteRepository(str(tmp_path / "ne_test.db"))
    assert repo.find_by_id(uuid4()) is None
    assert repo.find_by_voter(uuid4()) is None
