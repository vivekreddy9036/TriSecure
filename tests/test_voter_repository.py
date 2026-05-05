import pytest
from uuid import uuid4

from models.voter import Voter
from repositories.voter_repository import SQLiteVoterRepository


def test_save_and_find_by_id(voter_repo, sample_voter):
    voter_repo.save(sample_voter)
    found = voter_repo.find_by_id(sample_voter.id)
    assert found is not None
    assert found.name == sample_voter.name
    assert found.nfc_uid == sample_voter.nfc_uid


def test_find_by_nfc_uid(voter_repo, sample_voter):
    voter_repo.save(sample_voter)
    found = voter_repo.find_by_nfc_uid(sample_voter.nfc_uid)
    assert found is not None
    assert found.id == sample_voter.id


def test_find_all(voter_repo):
    v1 = Voter(name="Alice", nfc_uid="UID001")
    v2 = Voter(name="Bob", nfc_uid="UID002")
    voter_repo.save(v1)
    voter_repo.save(v2)
    all_voters = voter_repo.find_all()
    assert len(all_voters) == 2


def test_duplicate_nfc_uid_raises(voter_repo):
    v1 = Voter(name="Alice", nfc_uid="SAMEUID")
    v2 = Voter(name="Bob", nfc_uid="SAMEUID")
    voter_repo.save(v1)
    with pytest.raises(ValueError, match="NFC UID already registered"):
        voter_repo.save(v2)


def test_has_voted_persists(voter_repo, sample_voter):
    voter_repo.save(sample_voter)
    sample_voter.mark_as_voted()
    voter_repo.save(sample_voter)
    found = voter_repo.find_by_id(sample_voter.id)
    assert found.has_voted is True


def test_find_by_id_nonexistent(voter_repo):
    assert voter_repo.find_by_id(uuid4()) is None


def test_find_by_nfc_uid_nonexistent(voter_repo):
    assert voter_repo.find_by_nfc_uid("NOTEXIST") is None
