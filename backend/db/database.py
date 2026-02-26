"""
Biometric Database Module.

Handles secure storage and retrieval of encrypted face embeddings
in SQLite database.

This module is part of the backend layer and contains:
- BiometricDatabase: CRUD operations for face templates
- BiometricRecord: Data model for stored embeddings

Design:
- SQLite for lightweight, embedded storage
- BLOB storage for encrypted embeddings
- No ML logic (clean architecture)
- Thread-safe database access
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class BiometricRecord:
    """
    Data model for biometric record.
    
    Attributes:
        user_id: Unique identifier for the user
        encrypted_embedding: AES-encrypted embedding bytes
        salt: Encryption salt (for key derivation)
        iv: Initialization vector for AES
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    """
    user_id: str
    encrypted_embedding: bytes
    salt: bytes = field(default_factory=bytes)
    iv: bytes = field(default_factory=bytes)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class BiometricDatabase:
    """
    SQLite database for biometric template storage.
    
    Responsibilities:
    - Store encrypted face embeddings
    - Retrieve templates for verification
    - Delete biometric data
    - Manage database lifecycle
    
    Security:
    - Only stores encrypted embeddings (never raw)
    - Stores encryption metadata (salt, IV) separately
    - No ML operations (clean separation)
    
    Schema:
        biometric_templates (
            user_id TEXT PRIMARY KEY,
            encrypted_embedding BLOB NOT NULL,
            salt BLOB NOT NULL,
            iv BLOB NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    
    Usage:
        db = BiometricDatabase("biometrics.db")
        db.initialize()
        
        # Store encrypted embedding
        db.store_embedding(user_id, encrypted_bytes, salt, iv)
        
        # Retrieve for verification
        record = db.get_embedding(user_id)
        if record:
            encrypted = record.encrypted_embedding
    """
    
    def __init__(self, db_path: str = "biometrics.db"):
        """
        Initialize biometric database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._lock = Lock()
        self._initialized = False
        
        logger.debug(f"BiometricDatabase created: {db_path}")
    
    def initialize(self) -> bool:
        """
        Initialize database and create schema.
        
        Returns:
            True if initialization successful
            
        Raises:
            RuntimeError: If database cannot be created
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Create biometric templates table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS biometric_templates (
                        user_id TEXT PRIMARY KEY,
                        encrypted_embedding BLOB NOT NULL,
                        salt BLOB NOT NULL,
                        iv BLOB NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                
                # Create index for fast lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_biometric_user_id
                    ON biometric_templates(user_id)
                """)
                
                conn.commit()
            
            self._initialized = True
            logger.info(f"BiometricDatabase initialized: {self.db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise RuntimeError(f"Database initialization failed: {e}")
    
    @contextmanager
    def _get_connection(self):
        """
        Get thread-safe database connection.
        
        Yields:
            sqlite3.Connection: Database connection
        """
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def store_embedding(
        self,
        user_id: str,
        encrypted_embedding: bytes,
        salt: bytes,
        iv: bytes
    ) -> bool:
        """
        Store encrypted face embedding for user.
        
        Args:
            user_id: Unique user identifier
            encrypted_embedding: AES-encrypted embedding bytes
            salt: Encryption salt
            iv: AES initialization vector
            
        Returns:
            True if storage successful
            
        Raises:
            ValueError: If user_id is empty
            RuntimeError: If database operation fails
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")
        
        if not encrypted_embedding:
            raise ValueError("encrypted_embedding cannot be empty")
        
        now = datetime.utcnow().isoformat()
        
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Insert or replace (upsert)
                    cursor.execute("""
                        INSERT OR REPLACE INTO biometric_templates
                        (user_id, encrypted_embedding, salt, iv, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 
                            COALESCE((SELECT created_at FROM biometric_templates WHERE user_id = ?), ?),
                            ?)
                    """, (
                        user_id,
                        encrypted_embedding,
                        salt,
                        iv,
                        user_id,
                        now,
                        now
                    ))
                    
                    conn.commit()
                    
                logger.info(f"Embedding stored for user: {user_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to store embedding: {e}")
                raise RuntimeError(f"Failed to store embedding: {e}")
    
    def get_embedding(self, user_id: str) -> Optional[BiometricRecord]:
        """
        Retrieve encrypted embedding for user.
        
        Args:
            user_id: User identifier
            
        Returns:
            BiometricRecord or None if not found
        """
        if not user_id:
            return None
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT user_id, encrypted_embedding, salt, iv, created_at, updated_at
                    FROM biometric_templates
                    WHERE user_id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                
                if not row:
                    logger.debug(f"No embedding found for user: {user_id}")
                    return None
                
                return BiometricRecord(
                    user_id=row["user_id"],
                    encrypted_embedding=row["encrypted_embedding"],
                    salt=row["salt"],
                    iv=row["iv"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"])
                )
                
        except Exception as e:
            logger.error(f"Failed to retrieve embedding: {e}")
            return None
    
    def has_embedding(self, user_id: str) -> bool:
        """
        Check if user has stored embedding.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if embedding exists
        """
        if not user_id:
            return False
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT 1 FROM biometric_templates WHERE user_id = ?
                """, (user_id,))
                
                return cursor.fetchone() is not None
                
        except Exception as e:
            logger.error(f"Failed to check embedding: {e}")
            return False
    
    def delete_embedding(self, user_id: str) -> bool:
        """
        Delete user's biometric data.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if deletion successful
        """
        if not user_id:
            return False
        
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        DELETE FROM biometric_templates WHERE user_id = ?
                    """, (user_id,))
                    
                    deleted = cursor.rowcount > 0
                    conn.commit()
                    
                if deleted:
                    logger.info(f"Embedding deleted for user: {user_id}")
                
                return deleted
                
            except Exception as e:
                logger.error(f"Failed to delete embedding: {e}")
                return False
    
    def get_all_user_ids(self) -> List[str]:
        """
        Get all user IDs with stored embeddings.
        
        Returns:
            List of user IDs
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT user_id FROM biometric_templates ORDER BY user_id
                """)
                
                return [row["user_id"] for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to get user IDs: {e}")
            return []
    
    def count_embeddings(self) -> int:
        """
        Count total stored embeddings.
        
        Returns:
            Number of stored embeddings
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT COUNT(*) as count FROM biometric_templates")
                row = cursor.fetchone()
                
                return row["count"] if row else 0
                
        except Exception as e:
            logger.error(f"Failed to count embeddings: {e}")
            return 0
    
    def close(self) -> None:
        """Close database (cleanup)."""
        logger.info("BiometricDatabase closed")
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
