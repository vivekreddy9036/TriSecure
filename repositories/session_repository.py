"""
SQLite-backed session repository for TRIsecure V2.

Persists authentication sessions across restarts, enabling:
  - Forensic audit of session lifecycle
  - Replay detection after reboot
  - Compliance with ISO/IEC 19795 audit requirements

Schema (sessions table):
    token_hash   TEXT PRIMARY KEY   -- SHA-256 of raw token (never store plaintext)
    session_id   TEXT NOT NULL
    voter_id     TEXT NOT NULL
    issued_at    TEXT NOT NULL      -- ISO-8601 UTC
    expires_at   TEXT NOT NULL
    is_active    INTEGER NOT NULL   -- 0/1
    used         INTEGER NOT NULL   -- 0/1
"""

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from models import Session, Voter

logger = logging.getLogger(__name__)

_DEFAULT_DB = "data/sessions.db"


class SQLiteSessionRepository:
    """
    Persistent session store backed by SQLite.

    Thread-safe via check_same_thread=False + WAL mode.
    Used by SessionManager to persist sessions beyond process lifetime.
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._in_memory = (db_path == ":memory:")
        if not self._in_memory:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # For :memory: keep one persistent connection so the schema survives
        self._mem_conn: Optional[sqlite3.Connection] = None
        if self._in_memory:
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.execute("PRAGMA journal_mode=WAL")
            self._mem_conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info(f"SQLiteSessionRepository initialised: {db_path}")

    @contextmanager
    def _connect(self):
        if self._in_memory and self._mem_conn:
            yield self._mem_conn
        else:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash  TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    voter_id    TEXT NOT NULL,
                    issued_at   TEXT NOT NULL,
                    expires_at  TEXT NOT NULL,
                    is_active   INTEGER NOT NULL DEFAULT 1,
                    used        INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_voter ON sessions(voter_id)"
            )
            conn.commit()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _dt_to_str(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _str_to_dt(s: str) -> datetime:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save(self, session: Session) -> None:
        """Persist a new session."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                    (token_hash, session_id, voter_id, issued_at, expires_at, is_active, used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._hash_token(session.token),
                    str(session.session_id),
                    str(session.voter_id),
                    self._dt_to_str(session.issued_at),
                    self._dt_to_str(session.expires_at),
                    int(session.is_active),
                    int(session.used),
                ),
            )
            conn.commit()
        logger.debug(f"Session persisted: {session.session_id}")

    def mark_used(self, token: str) -> None:
        """Mark session as consumed (replay prevention)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET used=1, is_active=0 WHERE token_hash=?",
                (self._hash_token(token),),
            )
            conn.commit()

    def deactivate(self, token: str) -> None:
        """Deactivate session without marking as used."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET is_active=0 WHERE token_hash=?",
                (self._hash_token(token),),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def find_by_token(self, token: str) -> Optional[Session]:
        """Retrieve session by raw token. Returns None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash=?",
                (self._hash_token(token),),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row, token)

    def count_active(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE is_active=1"
            ).fetchone()
        return int(row[0])

    def purge_expired(self) -> int:
        """Delete sessions older than their expires_at. Returns count removed."""
        now_str = self._dt_to_str(datetime.now(timezone.utc))
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?", (now_str,)
            )
            conn.commit()
        removed = cur.rowcount
        if removed:
            logger.info(f"Purged {removed} expired sessions from DB")
        return removed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _row_to_session(self, row: sqlite3.Row, raw_token: str) -> Session:
        s = Session(
            session_id=UUID(row["session_id"]),
            voter_id=UUID(row["voter_id"]),
            token=raw_token,
            issued_at=self._str_to_dt(row["issued_at"]),
            expires_at=self._str_to_dt(row["expires_at"]),
            is_active=bool(row["is_active"]),
            used=bool(row["used"]),
        )
        return s
