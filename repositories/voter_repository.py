"""
Voter Repository for voter persistence.

Abstracts SQLite database operations for voter management.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
import sqlite3

from models import Voter

logger = logging.getLogger(__name__)


class VoterRepositoryBase(ABC):
    """
    Abstract base class for voter repository implementations.
    
    Design allows for swapping SQLite with distributed backend.
    """
    
    @abstractmethod
    def save(self, voter: Voter) -> Voter:
        """Save or update voter."""
        pass
    
    @abstractmethod
    def find_by_id(self, voter_id: UUID) -> Optional[Voter]:
        """Find voter by UUID."""
        pass
    
    @abstractmethod
    def find_by_nfc_uid(self, nfc_uid: str) -> Optional[Voter]:
        """Find voter by NFC UID."""
        pass
    
    @abstractmethod
    def find_all(self) -> List[Voter]:
        """Get all voters."""
        pass
    
    @abstractmethod
    def delete(self, voter_id: UUID) -> bool:
        """Delete voter."""
        pass


class SQLiteVoterRepository(VoterRepositoryBase):
    """
    SQLite-based voter repository implementation.
    
    Schema:
        voters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            nfc_uid TEXT UNIQUE NOT NULL,
            face_embedding BLOB,
            has_voted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    
    Features:
    - ACID transactions
    - Indexed lookups
    - Encrypted blob support (future)
    - Easy migration to distributed backend
    """
    
    def __init__(self, db_path: str = "trisecure.db"):
        """
        Initialize SQLite voter repository.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._initialized = False
        
        try:
            self._init_db()
            logger.info(f"SQLiteVoterRepository initialized: {db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize voter repository: {e}")
            raise
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS voters (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    nfc_uid TEXT UNIQUE NOT NULL,
                    face_embedding BLOB,
                    has_voted INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Create index for NFC UID lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_voters_nfc_uid 
                ON voters(nfc_uid)
            """)
            
            conn.commit()
            self._initialized = True
    
    def save(self, voter: Voter) -> Voter:
        """
        Save or update voter.
        
        Args:
            voter: Voter object to persist
            
        Returns:
            Saved voter object
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO voters
                    (id, name, nfc_uid, face_embedding, has_voted, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(voter.id),
                    voter.name,
                    voter.nfc_uid,
                    voter.face_embedding,
                    int(voter.has_voted),
                    voter.created_at.isoformat(),
                    voter.updated_at.isoformat()
                ))
                
                conn.commit()
                logger.info(f"Voter saved: {voter.id}")
                return voter
        
        except sqlite3.IntegrityError as e:
            logger.error(f"Duplicate NFC UID: {e}")
            raise ValueError(f"NFC UID already registered: {e}")
        
        except Exception as e:
            logger.error(f"Failed to save voter: {e}")
            raise
    
    def find_by_id(self, voter_id: UUID) -> Optional[Voter]:
        """
        Find voter by UUID.
        
        Args:
            voter_id: UUID to search for
            
        Returns:
            Voter object or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, name, nfc_uid, face_embedding, has_voted, created_at, updated_at
                    FROM voters
                    WHERE id = ?
                """, (str(voter_id),))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                return self._row_to_voter(row)
        
        except Exception as e:
            logger.error(f"Failed to find voter by ID: {e}")
            return None
    
    def find_by_nfc_uid(self, nfc_uid: str) -> Optional[Voter]:
        """
        Find voter by NFC UID (indexed lookup).
        
        Args:
            nfc_uid: NFC card UID
            
        Returns:
            Voter object or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, name, nfc_uid, face_embedding, has_voted, created_at, updated_at
                    FROM voters
                    WHERE nfc_uid = ?
                """, (nfc_uid,))
                
                row = cursor.fetchone()
                if not row:
                    logger.debug(f"Voter not found for NFC UID: {nfc_uid}")
                    return None
                
                return self._row_to_voter(row)
        
        except Exception as e:
            logger.error(f"Failed to find voter by NFC UID: {e}")
            return None
    
    def find_all(self) -> List[Voter]:
        """
        Get all voters.
        
        Returns:
            List of Voter objects
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, name, nfc_uid, face_embedding, has_voted, created_at, updated_at
                    FROM voters
                    ORDER BY created_at DESC
                """)
                
                rows = cursor.fetchall()
                return [self._row_to_voter(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Failed to fetch all voters: {e}")
            return []
    
    def delete(self, voter_id: UUID) -> bool:
        """
        Delete voter by ID.
        
        Args:
            voter_id: UUID of voter to delete
            
        Returns:
            True if deleted, False if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM voters WHERE id = ?", (str(voter_id),))
                conn.commit()
                
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info(f"Voter deleted: {voter_id}")
                else:
                    logger.warning(f"Voter not found for deletion: {voter_id}")
                
                return deleted
        
        except Exception as e:
            logger.error(f"Failed to delete voter: {e}")
            return False
    
    @staticmethod
    def _row_to_voter(row) -> Voter:
        """Convert database row to Voter object."""
        from datetime import datetime
        
        voter_id, name, nfc_uid, face_embedding, has_voted, created_at_str, updated_at_str = row
        
        return Voter(
            id=UUID(voter_id),
            name=name,
            nfc_uid=nfc_uid,
            face_embedding=face_embedding,
            has_voted=bool(has_voted),
            created_at=datetime.fromisoformat(created_at_str),
            updated_at=datetime.fromisoformat(updated_at_str)
        )
