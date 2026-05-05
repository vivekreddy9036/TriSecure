import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.voter import Voter
from models.vote import Vote
from models.audit_event import AuditEvent, EventType, EventStatus
from models.session import Session
from repositories.voter_repository import SQLiteVoterRepository
from repositories.vote_repository import SQLiteVoteRepository
from repositories.audit_repository import SQLiteAuditRepository
from core.session_manager import SessionManager
from core.audit_logger import AuditLogger


@pytest.fixture
def tmp_db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def voter_repo(tmp_db_path):
    return SQLiteVoterRepository(tmp_db_path)


@pytest.fixture
def vote_repo(tmp_db_path):
    return SQLiteVoteRepository(tmp_db_path)


@pytest.fixture
def audit_repo(tmp_db_path):
    return SQLiteAuditRepository(tmp_db_path)


@pytest.fixture
def sample_voter():
    return Voter(id=uuid4(), name="Alice Test", nfc_uid="AABBCCDD1122")


@pytest.fixture
def sample_vote(sample_voter):
    return Vote(voter_id=sample_voter.id, candidate="Candidate A")


@pytest.fixture
def session_manager():
    return SessionManager(duration_seconds=60)


@pytest.fixture
def audit_logger(audit_repo):
    return AuditLogger(repository=audit_repo)
