"""
Domain model for Session entity.

This module defines the Session model representing temporary authentication
sessions issued after successful biometric verification.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4
import secrets
from typing import Optional


@dataclass
class Session:
    """
    Represents a temporary, one-time voting session.
    
    Attributes:
        session_id: Unique identifier (UUID) for this session
        voter_id: Reference to the authenticated voter
        token: Secure random token (one-time use)
        issued_at: When session was created
        expires_at: When session expires (default 60 seconds)
        is_active: Whether session is still valid
        used: Whether this token has been used
    """
    
    session_id: UUID = field(default_factory=uuid4)
    voter_id: UUID = field(default_factory=uuid4)
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    issued_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(seconds=60))
    is_active: bool = True
    used: bool = False
    
    def is_expired(self) -> bool:
        """
        Check if session has expired.
        
        Returns:
            True if current time is past expires_at
        """
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """
        Check if session is valid for use.
        
        A session is valid if:
        - It's marked as active
        - It hasn't expired
        - It hasn't been used yet
        
        Returns:
            True if session can be used for voting
        """
        return self.is_active and not self.is_expired() and not self.used
    
    def mark_as_used(self) -> None:
        """Mark this session token as consumed."""
        self.used = True
    
    def deactivate(self) -> None:
        """Deactivate the session."""
        self.is_active = False
    
    def get_remaining_seconds(self) -> int:
        """
        Get remaining valid seconds for this session.
        
        Returns:
            Seconds remaining, or 0 if expired
        """
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))
    
    def __str__(self) -> str:
        status = "VALID" if self.is_valid() else "INVALID"
        return f"Session(id={self.session_id}, voter={self.voter_id}, status={status}, remaining={self.get_remaining_seconds()}s)"
    
    def __repr__(self) -> str:
        return self.__str__()
