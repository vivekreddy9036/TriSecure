"""
Vote Repository for vote persistence and blockchain-style integrity.

Maintains append-only vote log with hash chain + HMAC verification.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
import sqlite3

from models import Vote

logger = logging.getLogger(__name__)


class VoteRepositoryBase(ABC):
    """Abstract base class for vote repository implementations."""

    @abstractmethod
    def append_vote(self, vote: Vote) -> Vote:
        """Append vote to chain."""
        pass

    @abstractmethod
    def find_by_id(self, vote_id: UUID) -> Optional[Vote]:
        """Find vote by ID."""
        pass

    @abstractmethod
    def find_by_voter(self, voter_id: UUID) -> Optional[Vote]:
        """Find vote cast by specific voter."""
        pass

    @abstractmethod
    def get_all_votes(self) -> List[Vote]:
        """Get all votes in order."""
        pass

    @abstractmethod
    def verify_chain(self) -> bool:
        """Verify integrity of entire vote chain."""
        pass


class SQLiteVoteRepository(VoteRepositoryBase):
    """
    SQLite-based vote repository with blockchain-style hash chaining and HMAC signing.

    Schema:
        votes (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            vote_id TEXT NOT NULL UNIQUE,
            voter_id TEXT NOT NULL,
            candidate TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            current_hash TEXT NOT NULL,
            vote_hmac TEXT
        )
    """

    def __init__(self, db_path: str = "trisecure.db", signing_key: Optional[bytes] = None):
        """
        Initialize SQLite vote repository.

        Args:
            db_path: Path to SQLite database
            signing_key: Optional HMAC-SHA256 key for vote signing. When set,
                         each vote is signed on write and verified on chain check.
        """
        self.db_path = db_path
        self._signing_key = signing_key
        self._init_db()
        logger.info(f"SQLiteVoteRepository initialized: {db_path}")

    def _init_db(self) -> None:
        """Initialize vote schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    vote_id TEXT NOT NULL UNIQUE,
                    voter_id TEXT NOT NULL,
                    candidate TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    current_hash TEXT NOT NULL,
                    vote_hmac TEXT
                )
            """)

            # Migrate existing databases that lack the vote_hmac column
            try:
                cursor.execute("ALTER TABLE votes ADD COLUMN vote_hmac TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_votes_timestamp
                ON votes(timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_votes_voter
                ON votes(voter_id)
            """)

            conn.commit()

    def append_vote(self, vote: Vote) -> Vote:
        """
        Append vote to chain (one-way insert).

        Links new vote to previous hash and signs it when a signing_key is set.
        """
        try:
            last_vote = self._get_last_vote()
            if last_vote:
                vote.previous_hash = last_vote.current_hash
            else:
                vote.previous_hash = "0" * 64

            vote.current_hash = vote.calculate_hash()

            if self._signing_key:
                vote.vote_hmac = vote.compute_vote_hmac(self._signing_key)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO votes
                    (vote_id, voter_id, candidate, timestamp, previous_hash, current_hash, vote_hmac)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(vote.vote_id),
                    str(vote.voter_id),
                    vote.candidate,
                    vote.timestamp.isoformat(),
                    vote.previous_hash,
                    vote.current_hash,
                    vote.vote_hmac or None,
                ))

                conn.commit()
                logger.info(f"Vote appended to chain: {vote.vote_id}")
                return vote

        except Exception as e:
            logger.error(f"Failed to append vote: {e}")
            raise

    def find_by_id(self, vote_id: UUID) -> Optional[Vote]:
        """Find vote by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash, vote_hmac
                    FROM votes
                    WHERE vote_id = ?
                """, (str(vote_id),))

                row = cursor.fetchone()
                return self._row_to_vote(row) if row else None

        except Exception as e:
            logger.error(f"Failed to find vote: {e}")
            return None

    def find_by_voter(self, voter_id: UUID) -> Optional[Vote]:
        """Find vote cast by specific voter."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash, vote_hmac
                    FROM votes
                    WHERE voter_id = ?
                    LIMIT 1
                """, (str(voter_id),))

                row = cursor.fetchone()
                return self._row_to_vote(row) if row else None

        except Exception as e:
            logger.error(f"Failed to find vote by voter: {e}")
            return None

    def get_all_votes(self) -> List[Vote]:
        """Get all votes in chain order."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash, vote_hmac
                    FROM votes
                    ORDER BY sequence ASC
                """)

                rows = cursor.fetchall()
                return [self._row_to_vote(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get all votes: {e}")
            return []

    def verify_chain(self) -> bool:
        """
        Verify integrity of entire vote chain.

        Checks:
        1. Each vote's hash matches calculation
        2. Each vote's previous_hash matches previous vote's current_hash
        3. (When signing_key set) each vote's HMAC is valid
        """
        votes = self.get_all_votes()

        if not votes:
            logger.info("Vote chain empty - integrity verified")
            return True

        if votes[0].previous_hash != "0" * 64:
            logger.error("Genesis vote doesn't reference genesis hash")
            return False

        for i, vote in enumerate(votes):
            if not vote.verify_integrity():
                logger.error(f"Vote {i} hash mismatch: {vote.vote_id}")
                return False

            previous = votes[i - 1] if i > 0 else None
            if not vote.verify_chain_link(previous):
                logger.error(f"Vote {i} chain link broken: {vote.vote_id}")
                return False

            if self._signing_key and vote.vote_hmac:
                if not vote.verify_vote_hmac(self._signing_key):
                    logger.error(f"Vote {i} HMAC invalid: {vote.vote_id}")
                    return False

        logger.info(f"Vote chain verified: {len(votes)} votes")
        return True

    def _get_last_vote(self) -> Optional[Vote]:
        """Get most recent vote in chain."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash, vote_hmac
                    FROM votes
                    ORDER BY sequence DESC
                    LIMIT 1
                """)

                row = cursor.fetchone()
                return self._row_to_vote(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get last vote: {e}")
            return None

    @staticmethod
    def _row_to_vote(row) -> Vote:
        """Convert database row to Vote object."""
        from datetime import datetime

        vote_id, voter_id, candidate, timestamp_str, prev_hash, curr_hash, vote_hmac = row

        v = Vote(
            vote_id=UUID(vote_id),
            voter_id=UUID(voter_id),
            candidate=candidate,
            timestamp=datetime.fromisoformat(timestamp_str),
            previous_hash=prev_hash,
            current_hash=curr_hash,
        )
        v.vote_hmac = vote_hmac or ""
        return v
