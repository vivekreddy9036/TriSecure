"""
Audit Event Repository for audit trail persistence.

Maintains immutable audit log with optional HMAC integrity protection.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
import sqlite3

from models import AuditEvent, EventType, EventStatus

logger = logging.getLogger(__name__)


class AuditRepositoryBase(ABC):
    """Abstract base class for audit repository implementations."""

    @abstractmethod
    def save(self, event: AuditEvent) -> AuditEvent:
        """Save audit event."""
        pass

    @abstractmethod
    def find_by_id(self, event_id: UUID) -> Optional[AuditEvent]:
        """Find event by ID."""
        pass

    @abstractmethod
    def find_by_voter(self, voter_id: UUID) -> List[AuditEvent]:
        """Find all events for a voter."""
        pass

    @abstractmethod
    def find_by_type(self, event_type: EventType) -> List[AuditEvent]:
        """Find all events of a type."""
        pass

    @abstractmethod
    def get_all(self) -> List[AuditEvent]:
        """Get all events."""
        pass


class SQLiteAuditRepository(AuditRepositoryBase):
    """
    SQLite-based audit trail repository with optional HMAC integrity.

    Schema:
        audit_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            voter_id TEXT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT (JSON),
            hmac TEXT
        )
    """

    def __init__(self, db_path: str = "trisecure.db", audit_key: Optional[bytes] = None):
        """
        Initialize audit repository.

        Args:
            db_path: Path to SQLite database
            audit_key: Optional HMAC-SHA256 key. When set, every saved event is
                       signed and verify_all() can detect tampered rows.
        """
        self.db_path = db_path
        self._audit_key = audit_key
        self._init_db()
        logger.info(f"SQLiteAuditRepository initialized: {db_path}")

    def _init_db(self) -> None:
        """Initialize audit event schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    voter_id TEXT,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    hmac TEXT
                )
            """)

            # Migrate existing databases lacking the hmac column
            try:
                cursor.execute("ALTER TABLE audit_events ADD COLUMN hmac TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_events(timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_voter
                ON audit_events(voter_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_type
                ON audit_events(event_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_status
                ON audit_events(status)
            """)

            conn.commit()

    def save(self, event: AuditEvent) -> AuditEvent:
        """
        Save audit event (append-only).

        Signs the event with the audit key when one is configured.
        """
        if self._audit_key:
            event.hmac = event.compute_hmac(self._audit_key)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                details_json = json.dumps(event.details or {})

                cursor.execute("""
                    INSERT INTO audit_events
                    (event_id, event_type, voter_id, timestamp, status, message, details, hmac)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(event.event_id),
                    event.event_type.value,
                    str(event.voter_id) if event.voter_id else None,
                    event.timestamp.isoformat(),
                    event.status.value,
                    event.message,
                    details_json,
                    event.hmac,
                ))

                conn.commit()
                logger.debug(f"Audit event saved: {event.event_type.value}")
                return event

        except Exception as e:
            logger.error(f"Failed to save audit event: {e}")
            # Don't raise — audit failures must not crash the voting system
            return event

    def find_by_id(self, event_id: UUID) -> Optional[AuditEvent]:
        """Find audit event by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT event_id, event_type, voter_id, timestamp, status, message, details, hmac
                    FROM audit_events
                    WHERE event_id = ?
                """, (str(event_id),))

                row = cursor.fetchone()
                return self._row_to_event(row) if row else None

        except Exception as e:
            logger.error(f"Failed to find audit event: {e}")
            return None

    def find_by_voter(self, voter_id: UUID) -> List[AuditEvent]:
        """Find all audit events for a voter."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT event_id, event_type, voter_id, timestamp, status, message, details, hmac
                    FROM audit_events
                    WHERE voter_id = ?
                    ORDER BY timestamp DESC
                """, (str(voter_id),))

                rows = cursor.fetchall()
                return [self._row_to_event(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to find audit events for voter: {e}")
            return []

    def find_by_type(self, event_type: EventType) -> List[AuditEvent]:
        """Find all events of specific type."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT event_id, event_type, voter_id, timestamp, status, message, details, hmac
                    FROM audit_events
                    WHERE event_type = ?
                    ORDER BY timestamp DESC
                """, (event_type.value,))

                rows = cursor.fetchall()
                return [self._row_to_event(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to find audit events by type: {e}")
            return []

    def get_all(self) -> List[AuditEvent]:
        """Get all audit events in chronological order."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT event_id, event_type, voter_id, timestamp, status, message, details, hmac
                    FROM audit_events
                    ORDER BY timestamp DESC
                """)

                rows = cursor.fetchall()
                return [self._row_to_event(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get all audit events: {e}")
            return []

    def get_recent(self, limit: int = 100) -> List[AuditEvent]:
        """Get most recent audit events."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT event_id, event_type, voter_id, timestamp, status, message, details, hmac
                    FROM audit_events
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))

                rows = cursor.fetchall()
                return [self._row_to_event(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return []

    def verify_all(self) -> List[str]:
        """
        Verify HMAC integrity of all events.

        Returns:
            List of event_id strings that failed HMAC verification.
            Empty list means all events are intact.
            Requires audit_key to be set; without a key, returns [].
        """
        if not self._audit_key:
            return []

        tampered = []
        for event in self.get_all():
            if not event.verify_hmac(self._audit_key):
                tampered.append(str(event.event_id))
                logger.warning(f"Tampered audit event detected: {event.event_id}")

        return tampered

    @staticmethod
    def _row_to_event(row) -> AuditEvent:
        """Convert database row to AuditEvent object."""
        from datetime import datetime

        event_id, event_type_str, voter_id, timestamp_str, status_str, message, details_json, hmac_val = row

        details = {}
        if details_json:
            try:
                details = json.loads(details_json)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse details JSON for event {event_id}")

        event = AuditEvent(
            event_id=UUID(event_id),
            event_type=EventType(event_type_str),
            voter_id=UUID(voter_id) if voter_id else None,
            timestamp=datetime.fromisoformat(timestamp_str),
            status=EventStatus(status_str),
            message=message,
            details=details,
        )
        event.hmac = hmac_val
        return event
