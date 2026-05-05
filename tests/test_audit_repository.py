import pytest
from uuid import uuid4

from models.audit_event import AuditEvent, EventType, EventStatus


def test_save_and_find_by_id(audit_repo):
    event = AuditEvent(
        event_type=EventType.NFC_READ_SUCCESS,
        status=EventStatus.SUCCESS,
        message="NFC card read",
    )
    audit_repo.save(event)
    found = audit_repo.find_by_id(event.event_id)
    assert found is not None
    assert found.event_type == EventType.NFC_READ_SUCCESS


def test_find_by_voter(audit_repo):
    voter_id = uuid4()
    e1 = AuditEvent(event_type=EventType.VOTE_CAST, voter_id=voter_id,
                    status=EventStatus.SUCCESS, message="Voted")
    e2 = AuditEvent(event_type=EventType.FACE_MATCH_SUCCESS, voter_id=voter_id,
                    status=EventStatus.SUCCESS, message="Face OK")
    audit_repo.save(e1)
    audit_repo.save(e2)
    events = audit_repo.find_by_voter(voter_id)
    assert len(events) == 2


def test_find_by_type(audit_repo):
    e1 = AuditEvent(event_type=EventType.SYSTEM_ERROR, status=EventStatus.FAILURE, message="err")
    e2 = AuditEvent(event_type=EventType.NFC_READ_FAILED, status=EventStatus.FAILURE, message="nfc fail")
    audit_repo.save(e1)
    audit_repo.save(e2)
    errors = audit_repo.find_by_type(EventType.SYSTEM_ERROR)
    assert len(errors) == 1
    assert errors[0].event_type == EventType.SYSTEM_ERROR


def test_get_all_returns_all_events(audit_repo):
    for i in range(5):
        e = AuditEvent(event_type=EventType.CONFIG_LOADED, status=EventStatus.SUCCESS,
                       message=f"event {i}")
        audit_repo.save(e)
    all_events = audit_repo.get_all()
    assert len(all_events) == 5


def test_find_by_id_not_found(audit_repo):
    assert audit_repo.find_by_id(uuid4()) is None
