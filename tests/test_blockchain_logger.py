"""Tests for BlockchainLogger and vote integrity layer."""

import pytest
from uuid import uuid4

from models.vote import Vote
from repositories.vote_repository import SQLiteVoteRepository
from security.blockchain_logger import BlockchainLogger, BlockchainRecord


@pytest.fixture
def vote_repo(tmp_path):
    return SQLiteVoteRepository(str(tmp_path / "bl_test.db"))


@pytest.fixture
def blockchain(vote_repo):
    return BlockchainLogger(vote_repo)


def test_log_vote_returns_vote_with_hash(blockchain):
    vote = Vote(voter_id=uuid4(), candidate="Alice")
    logged = blockchain.log_vote(vote)
    assert logged.current_hash != ""
    assert len(logged.current_hash) == 64


def test_log_multiple_votes_chains(blockchain):
    v1 = blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Alice"))
    v2 = blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Bob"))
    assert v2.previous_hash == v1.current_hash


def test_verify_blockchain_integrity_empty(blockchain):
    assert blockchain.verify_blockchain_integrity() is True


def test_verify_blockchain_integrity_valid(blockchain):
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Alice"))
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Bob"))
    assert blockchain.verify_blockchain_integrity() is True


def test_blockchain_statistics_empty(blockchain):
    stats = blockchain.get_blockchain_statistics()
    assert stats["total_votes"] == 0
    assert stats["chain_valid"] is True
    assert stats["votes_per_candidate"] == {}
    assert stats["first_vote"] is None
    assert stats["last_vote"] is None


def test_blockchain_statistics_with_votes(blockchain):
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Alice"))
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Alice"))
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Bob"))

    stats = blockchain.get_blockchain_statistics()
    assert stats["total_votes"] == 3
    assert stats["votes_per_candidate"]["Alice"] == 2
    assert stats["votes_per_candidate"]["Bob"] == 1
    assert stats["chain_valid"] is True
    assert stats["chain_height"] == 3


def test_get_blockchain_record(blockchain):
    vote = blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Alice"))
    record = blockchain.get_blockchain_record(vote)
    assert isinstance(record, BlockchainRecord)
    assert record.block_hash == vote.current_hash
    assert record.previous_hash == vote.previous_hash
    assert "Alice" in record.data


def test_export_to_blockchain_format(blockchain):
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Alice"))
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Bob"))
    records = blockchain.export_to_blockchain_format()
    assert len(records) == 2
    assert all(isinstance(r, BlockchainRecord) for r in records)


def test_integrity_fails_after_tamper(blockchain, vote_repo, tmp_path):
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Alice"))
    blockchain.log_vote(Vote(voter_id=uuid4(), candidate="Bob"))

    import sqlite3
    db_path = str(tmp_path / "bl_test.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE votes SET candidate = 'TAMPERED' WHERE sequence = 1")

    assert blockchain.verify_blockchain_integrity() is False
