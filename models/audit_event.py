"""
Domain model for AuditEvent entity.

This module defines the AuditEvent model for comprehensive system audit logging.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    """Types of auditable events in the system."""
    
    # Voter registration events
    VOTER_REGISTERED = "VOTER_REGISTERED"
    VOTER_NFC_REGISTERED = "VOTER_NFC_REGISTERED"
    VOTER_FACE_REGISTERED = "VOTER_FACE_REGISTERED"
    
    # Authentication events
    NFC_READ_SUCCESS = "NFC_READ_SUCCESS"
    NFC_READ_FAILED = "NFC_READ_FAILED"
    VOTER_VERIFIED = "VOTER_VERIFIED"
    VOTER_NOT_FOUND = "VOTER_NOT_FOUND"
    VOTER_ALREADY_VOTED = "VOTER_ALREADY_VOTED"
    FACE_CAPTURE_SUCCESS = "FACE_CAPTURE_SUCCESS"
    FACE_CAPTURE_FAILED = "FACE_CAPTURE_FAILED"
    FACE_MATCH_SUCCESS = "FACE_MATCH_SUCCESS"
    FACE_MATCH_FAILED = "FACE_MATCH_FAILED"
    SESSION_ISSUED = "SESSION_ISSUED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    
    # Voting events
    VOTE_CAST = "VOTE_CAST"
    VOTE_RECORDED = "VOTE_RECORDED"
    
    # Security events
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    CONFIG_LOADED = "CONFIG_LOADED"
    HARDWARE_ERROR = "HARDWARE_ERROR"


class EventStatus(str, Enum):
    """Status of audited event."""
    
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    WARNING = "WARNING"


@dataclass
class AuditEvent:
    """
    Represents an auditability event in the system.
    
    Attributes:
        event_id: Unique identifier (UUID) for this event
        event_type: Type of event from EventType enum
        voter_id: Reference to associated voter (if applicable)
        timestamp: When event occurred
        status: Success/Failure/Warning status
        message: Human-readable description
        details: Additional structured data
    """
    
    event_id: UUID = field(default_factory=uuid4)
    event_type: EventType = EventType.SYSTEM_ERROR
    voter_id: Optional[UUID] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    status: EventStatus = EventStatus.SUCCESS
    message: str = ""
    details: Optional[dict] = field(default_factory=dict)
    
    def is_success(self) -> bool:
        """Check if event completed successfully."""
        return self.status == EventStatus.SUCCESS
    
    def is_failure(self) -> bool:
        """Check if event failed."""
        return self.status == EventStatus.FAILURE
    
    def __str__(self) -> str:
        voter_str = f" voter={self.voter_id}" if self.voter_id else ""
        return f"AuditEvent({self.event_type.value}, status={self.status.value}{voter_str})"
    
    def __repr__(self) -> str:
        return self.__str__()
