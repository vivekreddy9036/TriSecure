import pytest
from uuid import uuid4

from models.vote import Vote
from repositories.vote_repository import SQLiteVoteRepository


def test_vote_chain_append_and_verify(tmp_path):
    db_path = tmp_path / "tri_test.db"
    repo = SQLiteVoteRepository(str(db_path))

    v1 = Vote(voter_id=uuid4(), candidate="A")
    v2 = Vote(voter_id=uuid4(), candidate="B")

    repo.append_vote(v1)
    repo.append_vote(v2)

    votes = repo.get_all_votes()
    assert len(votes) == 2
    assert votes[0].previous_hash == "0" * 64
    assert votes[1].previous_hash == votes[0].current_hash
    assert repo.verify_chain() is True


def test_vote_chain_detects_tampering(tmp_path):
    db_path = tmp_path / "tri_tamper.db"
    repo = SQLiteVoteRepository(str(db_path))

    v1 = Vote(voter_id=uuid4(), candidate="A")
    v2 = Vote(voter_id=uuid4(), candidate="B")
    repo.append_vote(v1)
    repo.append_vote(v2)

    # Direct DB tamper simulation
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE votes SET candidate = ? WHERE sequence = 2", ("X",))
        conn.commit()

    assert repo.verify_chain() is False


def test_find_by_voter(tmp_path):
    db_path = tmp_path / "tri_byvoter.db"
    repo = SQLiteVoteRepository(str(db_path))
    voter_id = uuid4()
    vote = Vote(voter_id=voter_id, candidate="C")
    repo.append_vote(vote)

    found = repo.find_by_voter(voter_id)
    assert found is not None
    assert found.candidate == "C"
    assert found.voter_id == voter_id


def test_find_by_id(tmp_path):
    db_path = tmp_path / "tri_byid.db"
    repo = SQLiteVoteRepository(str(db_path))
    vote = Vote(voter_id=uuid4(), candidate="D")
    repo.append_vote(vote)

    found = repo.find_by_id(vote.vote_id)
    assert found is not None
    assert found.candidate == "D"


def test_empty_chain_verifies(tmp_path):
    db_path = tmp_path / "tri_empty.db"
    repo = SQLiteVoteRepository(str(db_path))
    assert repo.verify_chain() is True


def test_hmac_signing_detects_tampering(tmp_path):
    """When a signing_key is set, tampering invalidates the HMAC."""
    db_path = tmp_path / "tri_hmac.db"
    signing_key = b"test-vote-signing-key"
    repo = SQLiteVoteRepository(str(db_path), signing_key=signing_key)

    vote = Vote(voter_id=uuid4(), candidate="E")
    repo.append_vote(vote)

    # Tamper with candidate field
    import sqlite3
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("UPDATE votes SET candidate = 'X' WHERE sequence = 1")

    assert repo.verify_chain() is False
