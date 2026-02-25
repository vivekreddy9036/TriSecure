"""
Authentication Pipeline for multi-factor voter verification.

Implements the strict authentication flow with NFC, face recognition,
and session token generation.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Callable
from uuid import UUID

from models import Voter, Session, EventType, EventStatus
from core.session_manager import SessionManager
from core.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


@dataclass
class AuthenticationResult:
    """Result of authentication pipeline execution."""
    
    success: bool
    message: str
    session: Optional[Session] = None
    error_stage: Optional[str] = None


class AuthenticationPipeline:
    """
    Multi-stage authentication pipeline for voter verification.
    
    Flow:
    1. Read and validate NFC card
    2. Verify voter exists in database
    3. Check voter hasn't already voted
    4. Capture and verify face biometric
    5. Issue temporary session token (60s validity)
    
    Responsibilities:
    - Orchestrate multi-factor authentication
    - Provide clear pass/fail results
    - Audit all authentication attempts
    - Enforce security constraints
    
    Architecture:
    - Dependency injection of services
    - Clear separation of concerns
    - Comprehensive error reporting
    - Structured audit logging
    """
    
    def __init__(
        self,
        voter_repository: 'VoterRepository',
        session_manager: Optional[SessionManager] = None,
        audit_logger: Optional[AuditLogger] = None,
        face_match_threshold: float = 0.7
    ):
        """
        Initialize authentication pipeline.
        
        Args:
            voter_repository: Voter persistence layer
            session_manager: Session management (created if None)
            audit_logger: Audit logging (created if None)
            face_match_threshold: Face similarity threshold (0.0-1.0)
        """
        self.voter_repository = voter_repository
        self.session_manager = session_manager or SessionManager()
        self.audit_logger = audit_logger or AuditLogger()
        self.face_match_threshold = face_match_threshold
        
        logger.info(f"AuthenticationPipeline initialized with face threshold={face_match_threshold}")
    
    def authenticate(
        self,
        nfc_uid: str,
        face_embedding: Optional[bytes] = None,
        nfc_reader: Optional[Callable[[str], bool]] = None,
        face_verifier: Optional[Callable[[bytes, bytes], float]] = None
    ) -> AuthenticationResult:
        """
        Execute full authentication pipeline.
        
        Args:
            nfc_uid: NFC card UID from reader
            face_embedding: Captured face embedding bytes
            nfc_reader: Optional callback to verify NFC (for testing)
            face_verifier: Optional callback to compare faces (returns confidence 0-1)
            
        Returns:
            AuthenticationResult with success status and optional session
        """
        logger.info(f"Starting authentication pipeline for NFC UID: {nfc_uid}")
        
        # Stage 1: Verify NFC
        if not self._verify_nfc(nfc_uid, nfc_reader):
            self.audit_logger.log_nfc_read_failure("Invalid NFC UID format")
            return AuthenticationResult(
                success=False,
                message="NFC verification failed",
                error_stage="nfc_verification"
            )
        self.audit_logger.log_nfc_read_success(nfc_uid)
        
        # Stage 2: Verify voter exists
        voter = self._verify_voter_exists(nfc_uid)
        if not voter:
            self.audit_logger.log_voter_not_found(nfc_uid)
            return AuthenticationResult(
                success=False,
                message="Voter not registered",
                error_stage="voter_lookup"
            )
        self.audit_logger.log_voter_verified(voter.id)
        
        # Stage 3: Check not already voted
        if not self._verify_not_voted(voter):
            self.audit_logger.log_voter_already_voted(voter.id)
            return AuthenticationResult(
                success=False,
                message="Voter has already cast vote",
                error_stage="vote_eligibility"
            )
        
        # Stage 4: Verify face
        if face_embedding and voter.face_embedding:
            confidence = self._verify_face(
                voter.face_embedding,
                face_embedding,
                face_verifier
            )
            if confidence < self.face_match_threshold:
                self.audit_logger.log_face_match_failure(
                    f"Face confidence {confidence:.2f} below threshold {self.face_match_threshold}"
                )
                return AuthenticationResult(
                    success=False,
                    message="Face verification failed",
                    error_stage="face_verification"
                )
            self.audit_logger.log_face_match_success(voter.id, confidence)
        else:
            logger.warning("Face verification skipped: embedding not available")
        
        # Stage 5: Issue session token
        session = self.session_manager.create_session(voter)
        self.audit_logger.log_session_issued(voter.id, session.session_id)
        
        logger.info(f"Authentication successful for voter {voter.id}, session {session.session_id}")
        return AuthenticationResult(
            success=True,
            message="Authentication successful",
            session=session
        )
    
    def _verify_nfc(self, nfc_uid: str, verifier: Optional[Callable[[str], bool]] = None) -> bool:
        """
        Stage 1: Verify NFC card validity.
        
        Args:
            nfc_uid: NFC card UID
            verifier: Optional custom verification callback
            
        Returns:
            True if NFC is valid
        """
        if not nfc_uid or len(nfc_uid.strip()) == 0:
            logger.error("Empty NFC UID provided")
            return False
        
        if verifier:
            return verifier(nfc_uid)
        
        # Default: just check format (non-empty string)
        return len(nfc_uid.strip()) > 0
    
    def _verify_voter_exists(self, nfc_uid: str) -> Optional[Voter]:
        """
        Stage 2: Verify voter is registered.
        
        Args:
            nfc_uid: NFC card UID to lookup
            
        Returns:
            Voter object if found, None otherwise
        """
        voter = self.voter_repository.find_by_nfc_uid(nfc_uid)
        if voter:
            logger.info(f"Voter found: {voter.id}")
        else:
            logger.warning(f"No voter found for NFC UID: {nfc_uid}")
        return voter
    
    def _verify_not_voted(self, voter: Voter) -> bool:
        """
        Stage 3: Verify voter hasn't already voted.
        
        Args:
            voter: Voter object
            
        Returns:
            True if voter is eligible to vote
        """
        eligible = voter.is_eligible_to_vote()
        if not eligible:
            logger.warning(f"Voter {voter.id} already voted")
        return eligible
    
    def _verify_face(
        self,
        stored_embedding: bytes,
        captured_embedding: bytes,
        verifier: Optional[Callable[[bytes, bytes], float]] = None
    ) -> float:
        """
        Stage 4: Verify face biometric.
        
        Args:
            stored_embedding: Face embedding from registration
            captured_embedding: Face embedding from voting attempt
            verifier: Custom comparator callback (returns confidence 0-1)
            
        Returns:
            Confidence score 0.0-1.0
        """
        if verifier:
            return verifier(stored_embedding, captured_embedding)
        
        # Default: return 1.0 (perfect match) if bytes match, 0.0 otherwise
        # In production, use actual ML comparison
        return 1.0 if stored_embedding == captured_embedding else 0.0
    
    def verify_session_for_voting(self, session_token: str) -> Optional[Voter]:
        """
        Verify session is valid for voting and return associated voter.
        
        Args:
            session_token: Session token to verify
            
        Returns:
            Voter object if session valid, None otherwise
        """
        if not self.session_manager.validate_session(session_token):
            logger.error("Invalid session token for voting")
            return None
        
        session = self.session_manager.get_session(session_token)
        if not session or not session.voter_id:
            logger.error("Session exists but lacks voter reference")
            return None
        
        # Consume the token (one-time use)
        self.session_manager.consume_session(session_token)
        
        return self.voter_repository.find_by_id(session.voter_id)
