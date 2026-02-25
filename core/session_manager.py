"""
Session Manager for temporary voting authentication sessions.

Manages creation, validation, and lifecycle of one-time voting tokens.
"""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from trisecure.models import Session, Voter

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages temporary sessions for authenticated voters.
    
    Responsibilities:
    - Generate secure session tokens
    - Validate session validity and expiry
    - One-time token enforcement
    - Session deactivation after use
    
    Architecture:
    - Stateless token generation using secure randomness
    - Time-based expiry (default 60 seconds)
    - In-memory storage for active sessions (persistence handled by repository)
    """
    
    DEFAULT_SESSION_DURATION_SECONDS = 60
    
    def __init__(self, duration_seconds: int = DEFAULT_SESSION_DURATION_SECONDS):
        """
        Initialize SessionManager.
        
        Args:
            duration_seconds: How long session remains valid (default 60)
        """
        self.duration_seconds = duration_seconds
        self._active_sessions: dict[str, Session] = {}  # In-memory cache
        logger.info(f"SessionManager initialized with {duration_seconds}s duration")
    
    def create_session(self, voter: Voter) -> Session:
        """
        Create a new authenticated session for a voter.
        
        Args:
            voter: Authenticated Voter object
            
        Returns:
            New Session object with secure token
            
        Raises:
            ValueError: If voter is invalid
        """
        if not voter or not voter.id:
            logger.error("Attempted to create session for invalid voter")
            raise ValueError("Invalid voter for session creation")
        
        session = Session(
            voter_id=voter.id,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=self.duration_seconds),
            is_active=True
        )
        
        self._active_sessions[session.token] = session
        logger.info(f"Session created for voter {voter.id}: {session.session_id}")
        return session
    
    def validate_session(self, token: str) -> bool:
        """
        Validate if a session token is valid for use.
        
        Args:
            token: Session token to validate
            
        Returns:
            True if token is valid and can be used for voting
        """
        session = self._active_sessions.get(token)
        if not session:
            logger.warning(f"Session token not found: {token[:8]}...")
            return False
        
        if not session.is_valid():
            logger.warning(f"Session invalid: expired={session.is_expired()}, used={session.used}, active={session.is_active}")
            return False
        
        remaining = session.get_remaining_seconds()
        logger.debug(f"Session valid: {session.session_id}, {remaining}s remaining")
        return True
    
    def consume_session(self, token: str) -> Optional[Session]:
        """
        Mark a session as used (one-time use enforcement).
        
        Args:
            token: Session token to consume
            
        Returns:
            Session object if valid, None otherwise
        """
        session = self._active_sessions.get(token)
        if not session or not session.is_valid():
            logger.error(f"Attempted to consume invalid session token: {token[:8]}...")
            return None
        
        session.mark_as_used()
        logger.info(f"Session consumed: {session.session_id}")
        return session
    
    def get_session(self, token: str) -> Optional[Session]:
        """
        Retrieve a session by token.
        
        Args:
            token: Session token
            
        Returns:
            Session object if found, None otherwise
        """
        return self._active_sessions.get(token)
    
    def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions from memory.
        
        Returns:
            Number of sessions cleaned up
        """
        expired_tokens = [
            token for token, session in self._active_sessions.items()
            if session.is_expired()
        ]
        
        for token in expired_tokens:
            del self._active_sessions[token]
        
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired sessions")
        
        return len(expired_tokens)
    
    def deactivate_session(self, token: str) -> bool:
        """
        Explicitly deactivate a session.
        
        Args:
            token: Session token to deactivate
            
        Returns:
            True if session was deactivated, False if not found
        """
        session = self._active_sessions.get(token)
        if session:
            session.deactivate()
            logger.info(f"Session deactivated: {session.session_id}")
            return True
        return False
