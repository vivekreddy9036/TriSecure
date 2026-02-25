"""
Domain model for Voter entity.

This module defines the Voter model which represents a registered voter
in the TRIsecure voting system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional


@dataclass
class Voter:
    """
    Represents a voter in the system.
    
    Attributes:
        id: Unique identifier (UUID) for the voter
        name: Full name of the voter
        nfc_uid: NFC card unique identifier (string representation)
        face_embedding: Serialized face embedding vector for biometric authentication
        has_voted: Flag indicating if voter has already cast vote
        created_at: Timestamp when voter was registered
        updated_at: Timestamp of last update
    """
    
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    nfc_uid: str = ""
    face_embedding: Optional[bytes] = None
    has_voted: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def mark_as_voted(self) -> None:
        """Mark this voter as having voted."""
        self.has_voted = True
        self.updated_at = datetime.utcnow()
    
    def is_eligible_to_vote(self) -> bool:
        """Check if voter is eligible to vote (hasn't already voted)."""
        return not self.has_voted
    
    def __str__(self) -> str:
        return f"Voter(id={self.id}, name={self.name}, has_voted={self.has_voted})"
    
    def __repr__(self) -> str:
        return self.__str__()
