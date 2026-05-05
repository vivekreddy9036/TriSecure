import pytest
from uuid import uuid4

from models.audit_event import EventType, EventStatus
from core.audit_logger import AuditLogger


def test_log_nfc_read_success_creates_event(audit_logger, audit_repo):
    audit_logger.log_nfc_read_success("AABBCCDD")
    events = audit_repo.find_by_type(EventType.NFC_READ_SUCCESS)
    assert len(events) == 1
    assert events[0].is_success()


def test_log_vote_cast_persists_to_repo(audit_logger, audit_repo):
    voter_id = uuid4()
    audit_logger.log_vote_cast(voter_id, "Candidate A")
    events = audit_repo.find_by_voter(voter_id)
    assert any(e.event_type == EventType.VOTE_CAST for e in events)


def test_log_face_match_failure_status_is_failure(audit_logger, audit_repo):
    audit_logger.log_face_match_failure("confidence 0.30 below threshold")
    events = audit_repo.find_by_type(EventType.FACE_MATCH_FAILED)
    assert len(events) == 1
    assert events[0].is_failure()


def test_log_without_repository_does_not_crash():
    logger = AuditLogger(repository=None)
    # Should not raise even without a repo
    logger.log_nfc_read_success("DEADBEEF")
