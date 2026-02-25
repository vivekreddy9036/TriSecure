"""
Audit Logger for comprehensive system audit trail.

Logs all significant events for security, compliance, and forensics.
"""

import logging
from typing import Optional, Any
from uuid import UUID
from datetime import datetime

from trisecure.models import AuditEvent, EventType, EventStatus

# Configure structured logging
logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Centralized audit logging for all system events.
    
    Responsibilities:
    - Log authentication events (success/failure)
    - Log voting events
    - Log security incidents
    - Log system errors
    - Provide structured, tamper-evident audit trail
    
    Architecture:
    - Delegates to repository for persistence
    - Uses Python logging for immediate visibility
    - Structured events with type safety
    """
    
    def __init__(self, repository: Optional[Any] = None):
        """
        Initialize AuditLogger.
        
        Args:
            repository: Optional audit repository for persistence
        """
        self.repository = repository
        logger.info("AuditLogger initialized")
    
    def log_event(
        self,
        event_type: EventType,
        status: EventStatus,
        message: str,
        voter_id: Optional[UUID] = None,
        details: Optional[dict] = None
    ) -> AuditEvent:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event (from EventType enum)
            status: Success/Failure/Warning
            message: Human-readable description
            voter_id: Associated voter (if applicable)
            details: Additional structured data
            
        Returns:
            Created AuditEvent object
        """
        event = AuditEvent(
            event_type=event_type,
            voter_id=voter_id,
            status=status,
            message=message,
            details=details or {}
        )
        
        # Log to Python logging immediately
        log_level = logging.INFO if status == EventStatus.SUCCESS else logging.WARNING
        logger.log(
            log_level,
            f"[AUDIT] {event_type.value} - {message}",
            extra={
                'event_id': str(event.event_id),
                'voter_id': str(voter_id) if voter_id else 'N/A',
                'status': status.value
            }
        )
        
        # Persist if repository available
        if self.repository:
            try:
                self.repository.save(event)
            except Exception as e:
                logger.error(f"Failed to persist audit event: {e}")
        
        return event
    
    # Convenience methods for common event types
    
    def log_nfc_read_success(self, nfc_uid: str) -> AuditEvent:
        """Log successful NFC card read."""
        return self.log_event(
            EventType.NFC_READ_SUCCESS,
            EventStatus.SUCCESS,
            f"NFC card read successfully: {nfc_uid}",
            details={'nfc_uid': nfc_uid}
        )
    
    def log_nfc_read_failure(self, reason: str) -> AuditEvent:
        """Log failed NFC read."""
        return self.log_event(
            EventType.NFC_READ_FAILED,
            EventStatus.FAILURE,
            f"NFC read failed: {reason}",
            details={'reason': reason}
        )
    
    def log_voter_verified(self, voter_id: UUID) -> AuditEvent:
        """Log successful voter verification."""
        return self.log_event(
            EventType.VOTER_VERIFIED,
            EventStatus.SUCCESS,
            "Voter verified successfully",
            voter_id=voter_id
        )
    
    def log_voter_not_found(self, nfc_uid: str) -> AuditEvent:
        """Log voter not found."""
        return self.log_event(
            EventType.VOTER_NOT_FOUND,
            EventStatus.FAILURE,
            f"Voter not found for NFC UID: {nfc_uid}",
            details={'nfc_uid': nfc_uid}
        )
    
    def log_voter_already_voted(self, voter_id: UUID) -> AuditEvent:
        """Log attempt to vote by someone who already voted."""
        return self.log_event(
            EventType.VOTER_ALREADY_VOTED,
            EventStatus.FAILURE,
            "Voter attempted to vote twice",
            voter_id=voter_id
        )
    
    def log_face_match_success(self, voter_id: UUID, confidence: float) -> AuditEvent:
        """Log successful face match."""
        return self.log_event(
            EventType.FACE_MATCH_SUCCESS,
            EventStatus.SUCCESS,
            f"Face matched with confidence: {confidence:.2f}",
            voter_id=voter_id,
            details={'confidence': confidence}
        )
    
    def log_face_match_failure(self, reason: str) -> AuditEvent:
        """Log failed face match."""
        return self.log_event(
            EventType.FACE_MATCH_FAILED,
            EventStatus.FAILURE,
            f"Face match failed: {reason}",
            details={'reason': reason}
        )
    
    def log_session_issued(self, voter_id: UUID, session_id: UUID) -> AuditEvent:
        """Log session issuance."""
        return self.log_event(
            EventType.SESSION_ISSUED,
            EventStatus.SUCCESS,
            "Authentication session issued",
            voter_id=voter_id,
            details={'session_id': str(session_id)}
        )
    
    def log_vote_cast(self, voter_id: UUID, candidate: str) -> AuditEvent:
        """Log vote cast."""
        return self.log_event(
            EventType.VOTE_CAST,
            EventStatus.SUCCESS,
            f"Vote cast for candidate: {candidate}",
            voter_id=voter_id,
            details={'candidate': candidate}
        )
    
    def log_system_error(self, error: str, details: Optional[dict] = None) -> AuditEvent:
        """Log system error."""
        return self.log_event(
            EventType.SYSTEM_ERROR,
            EventStatus.FAILURE,
            f"System error: {error}",
            details=details
        )
    
    def log_unauthorized_access(self, reason: str) -> AuditEvent:
        """Log unauthorized access attempt."""
        return self.log_event(
            EventType.UNAUTHORIZED_ACCESS,
            EventStatus.FAILURE,
            f"Unauthorized access: {reason}",
            details={'reason': reason}
        )
    
    def log_hardware_error(self, device: str, error: str) -> AuditEvent:
        """Log hardware error."""
        return self.log_event(
            EventType.HARDWARE_ERROR,
            EventStatus.FAILURE,
            f"Hardware error on {device}: {error}",
            details={'device': device, 'error': error}
        )
