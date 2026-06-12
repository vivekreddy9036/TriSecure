"""
Session Manager for temporary voting authentication sessions.

Manages creation, validation, and lifecycle of one-time voting tokens.
"""

import hashlib
import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone

from models import Session, Voter

logger = logging.getLogger(__name__)

try:
    from repositories.session_repository import SQLiteSessionRepository as _SessionRepo
    _REPO_AVAILABLE = True
except ImportError:
    _REPO_AVAILABLE = False


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

    @staticmethod
    def _token_key(token: str) -> str:
        """Store SHA-256 of token as dict key, never the raw token."""
        return hashlib.sha256(token.encode()).hexdigest()

    def __init__(
        self,
        duration_seconds: int = DEFAULT_SESSION_DURATION_SECONDS,
        db_path: Optional[str] = None,
    ):
        self.duration_seconds = duration_seconds
        self._active_sessions: dict[str, Session] = {}  # In-memory cache

        # Optional persistent backend — use default DB path when not overridden
        self._repo = None
        if _REPO_AVAILABLE:
            try:
                path = db_path or "data/sessions.db"
                self._repo = _SessionRepo(path)
            except Exception as exc:
                logger.warning(f"SessionRepository unavailable ({exc}) — in-memory only")

        logger.info(f"SessionManager initialized: {duration_seconds}s TTL, "
                    f"persistent={'yes' if self._repo else 'no'}")
    
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
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.duration_seconds),
            is_active=True
        )

        self._active_sessions[self._token_key(session.token)] = session
        if self._repo:
            try:
                self._repo.save(session)
            except Exception as exc:
                logger.warning(f"Failed to persist session to DB: {exc}")
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
        session = self._active_sessions.get(self._token_key(token))
        if not session and self._repo:
            # Recover from restart — check persistent store
            session = self._repo.find_by_token(token)
            if session:
                self._active_sessions[self._token_key(token)] = session
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
        session = self._active_sessions.get(self._token_key(token))
        if not session or not session.is_valid():
            logger.error(f"Attempted to consume invalid session token: {token[:8]}...")
            return None
        
        session.mark_as_used()
        if self._repo:
            try:
                self._repo.mark_used(token)
            except Exception as exc:
                logger.warning(f"Failed to update session in DB: {exc}")
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
        return self._active_sessions.get(self._token_key(token))
    
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
        session = self._active_sessions.get(self._token_key(token))
        if session:
            session.deactivate()
            logger.info(f"Session deactivated: {session.session_id}")
            return True
        return False
