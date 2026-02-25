"""
Vote Repository for vote persistence and blockchain-style integrity.

Maintains append-only vote log with hash chain verification.
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
    SQLite-based vote repository with blockchain-style hash chaining.
    
    Schema:
        votes (
            vote_id TEXT PRIMARY KEY,
            voter_id TEXT NOT NULL,
            candidate TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            current_hash TEXT NOT NULL,
            sequence INTEGER AUTOINCREMENT
        )
    
    Features:
    - Append-only log
    - Hash chain verification
    - Tamper-proof vote integrity
    - Candidate anonymity (stores only candidate ID)
    - Indexed by timestamp for audit
    """
    
    def __init__(self, db_path: str = "trisecure.db"):
        """
        Initialize SQLite vote repository.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
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
                    current_hash TEXT NOT NULL
                )
            """)
            
            # Verify chain integrity index
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
        
        Automatically links new vote to previous hash.
        
        Args:
            vote: Vote object to append
            
        Returns:
            Appended vote object
        """
        try:
            # Get previous vote to set previous_hash
            last_vote = self._get_last_vote()
            if last_vote:
                vote.previous_hash = last_vote.current_hash
            else:
                vote.previous_hash = "0" * 64  # Genesis
            
            # Recalculate hash with correct previous_hash
            vote.current_hash = vote.calculate_hash()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO votes
                    (vote_id, voter_id, candidate, timestamp, previous_hash, current_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(vote.vote_id),
                    str(vote.voter_id),
                    vote.candidate,
                    vote.timestamp.isoformat(),
                    vote.previous_hash,
                    vote.current_hash
                ))
                
                conn.commit()
                logger.info(f"Vote appended to chain: {vote.vote_id}")
                return vote
        
        except Exception as e:
            logger.error(f"Failed to append vote: {e}")
            raise
    
    def find_by_id(self, vote_id: UUID) -> Optional[Vote]:
        """
        Find vote by ID.
        
        Args:
            vote_id: Vote UUID
            
        Returns:
            Vote object or None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash
                    FROM votes
                    WHERE vote_id = ?
                """, (str(vote_id),))
                
                row = cursor.fetchone()
                return self._row_to_vote(row) if row else None
        
        except Exception as e:
            logger.error(f"Failed to find vote: {e}")
            return None
    
    def find_by_voter(self, voter_id: UUID) -> Optional[Vote]:
        """
        Find vote cast by specific voter.
        
        Args:
            voter_id: Voter UUID
            
        Returns:
            Vote object or None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash
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
        """
        Get all votes in chain order.
        
        Returns:
            List of Vote objects in order
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash
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
        
        Returns:
            True if chain is valid, False if tampered
        """
        votes = self.get_all_votes()
        
        if not votes:
            logger.info("Vote chain empty - integrity verified")
            return True
        
        # Check first vote references genesis
        if votes[0].previous_hash != "0" * 64:
            logger.error("Genesis vote doesn't reference genesis hash")
            return False
        
        # Verify each vote
        for i, vote in enumerate(votes):
            # Verify vote's own hash
            if not vote.verify_integrity():
                logger.error(f"Vote {i} hash mismatch: {vote.vote_id}")
                return False
            
            # Verify chain link
            previous = votes[i-1] if i > 0 else None
            if not vote.verify_chain_link(previous):
                logger.error(f"Vote {i} chain link broken: {vote.vote_id}")
                return False
        
        logger.info(f"Vote chain verified: {len(votes)} votes")
        return True
    
    def _get_last_vote(self) -> Optional[Vote]:
        """Get most recent vote in chain."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT vote_id, voter_id, candidate, timestamp, previous_hash, current_hash
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
        
        vote_id, voter_id, candidate, timestamp_str, prev_hash, curr_hash = row
        
        return Vote(
            vote_id=UUID(vote_id),
            voter_id=UUID(voter_id),
            candidate=candidate,
            timestamp=datetime.fromisoformat(timestamp_str),
            previous_hash=prev_hash,
            current_hash=curr_hash
        )
