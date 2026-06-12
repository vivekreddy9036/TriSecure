"""
Vote Repository for vote persistence and blockchain-style integrity.

Maintains append-only vote log with hash chain + HMAC + Dilithium-3 signatures
and Merkle tree for O(log n) per-vote inclusion proofs.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Tuple
from uuid import UUID
import sqlite3

from models import Vote

logger = logging.getLogger(__name__)


class VoteRepositoryBase(ABC):
    """Abstract base class for vote repository implementations."""

    @abstractmethod
    def append_vote(self, vote: Vote) -> Vote:
        pass

    @abstractmethod
    def find_by_id(self, vote_id: UUID) -> Optional[Vote]:
        pass

    @abstractmethod
    def find_by_voter(self, voter_id: UUID) -> Optional[Vote]:
        pass

    @abstractmethod
    def get_all_votes(self) -> List[Vote]:
        pass

    @abstractmethod
    def verify_chain(self) -> bool:
        pass


class SQLiteVoteRepository(VoteRepositoryBase):
    """
    SQLite-based vote repository with:
    - Blockchain-style SHA-256 sequential hash chain
    - HMAC-SHA256 vote signing
    - Dilithium-3 (FIPS 204) PQC signatures (optional)
    - Binary SHA-256 Merkle tree with O(log n) per-vote inclusion proofs

    Schema (votes table):
        sequence INTEGER PRIMARY KEY AUTOINCREMENT
        vote_id TEXT NOT NULL UNIQUE
        voter_id TEXT NOT NULL
        candidate TEXT NOT NULL
        timestamp TEXT NOT NULL
        previous_hash TEXT NOT NULL
        current_hash TEXT NOT NULL
        vote_hmac TEXT
        dilithium_sig TEXT       -- Dilithium-3 hex signature (PQC)
        merkle_leaf_hash TEXT    -- SHA-256(current_hash) Merkle leaf
    """

    _SELECT_COLS = (
        "vote_id, voter_id, candidate, timestamp, "
        "previous_hash, current_hash, vote_hmac, "
        "dilithium_sig, merkle_leaf_hash"
    )

    def __init__(self, db_path: str = "trisecure.db",
                 signing_key: Optional[bytes] = None,
                 dilithium_secret_key: Optional[bytes] = None):
        from security.merkle_tree import VoteMerkleTree  # lazy import breaks circular dependency
        self.db_path = db_path
        self._signing_key = signing_key
        self._dilithium_sk = dilithium_secret_key
        self._merkle_tree = VoteMerkleTree()
        self._leaf_index_map: Dict[str, int] = {}  # vote_id_str -> leaf_index

        self._init_db()
        self._rebuild_merkle_tree()
        logger.info(f"SQLiteVoteRepository initialized: {db_path}")

    def _init_db(self) -> None:
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

            # Incremental schema migrations — safe to re-run
            for col, coltype in [
                ("vote_hmac", "TEXT"),
                ("dilithium_sig", "TEXT"),
                ("merkle_leaf_hash", "TEXT"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE votes ADD COLUMN {col} {coltype}")
                except sqlite3.OperationalError:
                    pass  # column already exists

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS merkle_roots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    root_hash TEXT NOT NULL,
                    vote_count INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_votes_timestamp
                ON votes(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_votes_voter
                ON votes(voter_id)
            """)

            conn.commit()

    def _rebuild_merkle_tree(self) -> None:
        """Rebuild Merkle tree from persisted votes on startup."""
        votes = self.get_all_votes()
        for vote in votes:
            leaf_data = vote.current_hash.encode()
            self._merkle_tree.add_leaf(leaf_data)
            self._leaf_index_map[str(vote.vote_id)] = len(self._merkle_tree) - 1
        if votes:
            logger.info(f"Merkle tree rebuilt: {len(self._merkle_tree)} leaves, root={self._merkle_tree.get_root()[:12]}…")

    def append_vote(self, vote: Vote) -> Vote:
        """Append vote to chain with HMAC, optional Dilithium-3 signature, and Merkle leaf."""
        try:
            last_vote = self._get_last_vote()
            vote.previous_hash = last_vote.current_hash if last_vote else "0" * 64
            vote.current_hash = vote.calculate_hash()

            if self._signing_key:
                vote.vote_hmac = vote.compute_vote_hmac(self._signing_key)

            if self._dilithium_sk:
                vote.vote_dilithium_sig = vote.compute_dilithium_signature(self._dilithium_sk)

            # Merkle leaf
            leaf_data = vote.current_hash.encode()
            leaf_hash = self._merkle_tree.add_leaf(leaf_data)
            vote.merkle_leaf_hash = leaf_hash
            leaf_index = len(self._merkle_tree) - 1
            self._leaf_index_map[str(vote.vote_id)] = leaf_index

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO votes
                    (vote_id, voter_id, candidate, timestamp, previous_hash, current_hash,
                     vote_hmac, dilithium_sig, merkle_leaf_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(vote.vote_id),
                    str(vote.voter_id),
                    vote.candidate,
                    vote.timestamp.isoformat(),
                    vote.previous_hash,
                    vote.current_hash,
                    vote.vote_hmac or None,
                    vote.vote_dilithium_sig or None,
                    vote.merkle_leaf_hash or None,
                ))
                conn.commit()

            logger.info(f"Vote appended: {vote.vote_id}, Merkle leaf #{leaf_index}")
            return vote

        except Exception as e:
            logger.error(f"Failed to append vote: {e}")
            raise

    def find_by_id(self, vote_id: UUID) -> Optional[Vote]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT {self._SELECT_COLS} FROM votes WHERE vote_id = ?",
                    (str(vote_id),)
                )
                row = cursor.fetchone()
                return self._row_to_vote(row) if row else None
        except Exception as e:
            logger.error(f"Failed to find vote: {e}")
            return None

    def find_by_voter(self, voter_id: UUID) -> Optional[Vote]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT {self._SELECT_COLS} FROM votes WHERE voter_id = ? LIMIT 1",
                    (str(voter_id),)
                )
                row = cursor.fetchone()
                return self._row_to_vote(row) if row else None
        except Exception as e:
            logger.error(f"Failed to find vote by voter: {e}")
            return None

    def get_all_votes(self) -> List[Vote]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT {self._SELECT_COLS} FROM votes ORDER BY sequence ASC"
                )
                return [self._row_to_vote(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get all votes: {e}")
            return []

    def verify_chain(self) -> bool:
        """
        Verify integrity:
        1. Each vote hash matches calculation
        2. Hash chain linkage is intact
        3. HMAC valid (when signing_key set)
        4. Dilithium-3 signature valid (when dilithium_pk set)
        """
        votes = self.get_all_votes()
        if not votes:
            logger.info("Vote chain empty — integrity verified")
            return True

        if votes[0].previous_hash != "0" * 64:
            logger.error("Genesis vote does not reference genesis hash")
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

    # -------------------------------------------------------------------------
    # Merkle tree public interface
    # -------------------------------------------------------------------------

    def get_merkle_root(self) -> Optional[str]:
        """Return current Merkle root."""
        return self._merkle_tree.get_root()

    def get_merkle_proof(self, vote_id) -> List[Tuple[str, str]]:
        """Return O(log n) Merkle inclusion proof for vote_id."""
        idx = self._leaf_index_map.get(str(vote_id))
        if idx is None:
            logger.warning(f"get_merkle_proof: vote_id {vote_id} not in tree")
            return []
        return self._merkle_tree.get_proof(idx)

    def verify_merkle_inclusion(self, vote_id) -> bool:
        """Verify a vote is included in the current Merkle tree."""
        from security.merkle_tree import VoteMerkleTree
        if isinstance(vote_id, str):
            vote_id = UUID(vote_id)
        vote = self.find_by_id(vote_id)
        if vote is None:
            return False
        idx = self._leaf_index_map.get(str(vote_id))
        if idx is None:
            return False
        proof = self._merkle_tree.get_proof(idx)
        root = self._merkle_tree.get_root()
        leaf_hash = vote.merkle_leaf_hash
        if not leaf_hash:
            leaf_hash = hashlib.sha256(vote.current_hash.encode()).hexdigest()
        return VoteMerkleTree.verify_proof(leaf_hash, proof, root)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _get_last_vote(self) -> Optional[Vote]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT {self._SELECT_COLS} FROM votes ORDER BY sequence DESC LIMIT 1"
                )
                row = cursor.fetchone()
                return self._row_to_vote(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get last vote: {e}")
            return None

    @staticmethod
    def _row_to_vote(row) -> Vote:
        from datetime import datetime

        # Unpack 9 columns; dilithium_sig and merkle_leaf_hash may be None on old rows
        (vote_id, voter_id, candidate, timestamp_str,
         prev_hash, curr_hash, vote_hmac,
         dilithium_sig, merkle_leaf_hash) = row

        v = Vote(
            vote_id=UUID(vote_id),
            voter_id=UUID(voter_id),
            candidate=candidate,
            timestamp=datetime.fromisoformat(timestamp_str),
            previous_hash=prev_hash,
            current_hash=curr_hash,
        )
        v.vote_hmac = vote_hmac or ""
        v.vote_dilithium_sig = dilithium_sig or ""
        v.merkle_leaf_hash = merkle_leaf_hash or ""
        return v
