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
            face_embedding BLOB,         -- legacy plaintext, NULL for new rows
            face_enc_blob BLOB,          -- AES-256-GCM ciphertext
            face_enc_salt BLOB,          -- PBKDF2 salt
            face_enc_iv BLOB,            -- GCM IV
            has_voted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """

    def __init__(self, db_path: str = "trisecure.db", encryptor=None):
        """
        Initialize SQLite voter repository.

        Args:
            db_path: Path to SQLite database file
            encryptor: Optional EmbeddingEncryptor instance for at-rest encryption
        """
        self.db_path = db_path
        self._encryptor = encryptor
        self._initialized = False

        try:
            self._init_db()
            logger.info(f"SQLiteVoterRepository initialized: {db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize voter repository: {e}")
            raise

    def _init_db(self) -> None:
        """Initialize database schema with encryption columns."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS voters (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    nfc_uid TEXT UNIQUE NOT NULL,
                    face_embedding BLOB,
                    face_enc_blob BLOB,
                    face_enc_salt BLOB,
                    face_enc_iv BLOB,
                    has_voted INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Migrate existing databases that lack the encryption columns
            for col in ("face_enc_blob", "face_enc_salt", "face_enc_iv"):
                try:
                    cursor.execute(f"ALTER TABLE voters ADD COLUMN {col} BLOB")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_voters_nfc_uid
                ON voters(nfc_uid)
            """)

            conn.commit()
            self._initialized = True

    def save(self, voter: Voter) -> Voter:
        """
        Save or update voter.

        When an encryptor is configured and face_embedding is present, stores
        the embedding encrypted in face_enc_* columns and sets face_embedding
        to NULL. Without an encryptor, falls back to legacy plaintext storage.
        """
        enc_blob = enc_salt = enc_iv = None
        raw_embedding = voter.face_embedding

        if self._encryptor and voter.face_embedding:
            try:
                import numpy as np
                arr = np.frombuffer(voter.face_embedding, dtype=np.float32)
                result = self._encryptor.encrypt(arr)
                if result.success:
                    enc_blob = result.ciphertext
                    enc_salt = result.salt
                    enc_iv = result.iv
                    raw_embedding = None  # don't store plaintext
            except Exception as e:
                logger.error(f"Embedding encryption failed, storing plaintext: {e}")

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Guard against NFC UID being claimed by a different voter
                cursor.execute(
                    "SELECT id FROM voters WHERE nfc_uid = ? AND id != ?",
                    (voter.nfc_uid, str(voter.id))
                )
                if cursor.fetchone():
                    raise sqlite3.IntegrityError(f"UNIQUE constraint failed: voters.nfc_uid")

                cursor.execute("""
                    INSERT OR REPLACE INTO voters
                    (id, name, nfc_uid, face_embedding, face_enc_blob, face_enc_salt, face_enc_iv,
                     has_voted, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(voter.id),
                    voter.name,
                    voter.nfc_uid,
                    raw_embedding,
                    enc_blob,
                    enc_salt,
                    enc_iv,
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
        """Find voter by UUID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, name, nfc_uid, face_embedding, face_enc_blob, face_enc_salt,
                           face_enc_iv, has_voted, created_at, updated_at
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
        """Find voter by NFC UID (indexed lookup)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, name, nfc_uid, face_embedding, face_enc_blob, face_enc_salt,
                           face_enc_iv, has_voted, created_at, updated_at
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
        """Get all voters."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, name, nfc_uid, face_embedding, face_enc_blob, face_enc_salt,
                           face_enc_iv, has_voted, created_at, updated_at
                    FROM voters
                    ORDER BY created_at DESC
                """)

                rows = cursor.fetchall()
                return [self._row_to_voter(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to fetch all voters: {e}")
            return []

    def delete(self, voter_id: UUID) -> bool:
        """Delete voter by ID."""
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

    def _row_to_voter(self, row) -> Voter:
        """Convert database row to Voter object, decrypting embedding if needed."""
        from datetime import datetime

        (voter_id, name, nfc_uid, face_embedding, enc_blob, enc_salt, enc_iv,
         has_voted, created_at_str, updated_at_str) = row

        # Decrypt if encrypted columns are present
        if enc_blob and enc_salt and enc_iv and self._encryptor:
            try:
                result = self._encryptor.decrypt(enc_blob, enc_salt, enc_iv)
                if result.success:
                    face_embedding = result.embedding.tobytes()
            except Exception as e:
                logger.error(f"Embedding decryption failed for voter {voter_id}: {e}")
                face_embedding = None

        return Voter(
            id=UUID(voter_id),
            name=name,
            nfc_uid=nfc_uid,
            face_embedding=face_embedding,
            has_voted=bool(has_voted),
            created_at=datetime.fromisoformat(created_at_str),
            updated_at=datetime.fromisoformat(updated_at_str)
        )
