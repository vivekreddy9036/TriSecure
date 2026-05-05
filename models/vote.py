"""
Domain model for Vote entity.

This module defines the Vote model which represents a single cast vote
with blockchain-ready hash chaining for tamper-proof integrity.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4
import hashlib
import hmac as _hmac
from typing import Optional


@dataclass
class Vote:
    """
    Represents a single cast vote with blockchain-style integrity.
    
    Attributes:
        vote_id: Unique identifier (UUID) for this vote
        voter_id: Reference to the voter who cast this vote
        candidate: The chosen candidate identifier
        timestamp: When the vote was cast
        previous_hash: Hash of the previous vote in the chain
        current_hash: SHA256 hash of (candidate + timestamp + previous_hash)
    """
    
    vote_id: UUID = field(default_factory=uuid4)
    voter_id: UUID = field(default_factory=uuid4)
    candidate: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    previous_hash: str = "0" * 64  # Genesis block hash (64 zeros for SHA256)
    current_hash: str = ""
    vote_hmac: str = ""

    def __post_init__(self) -> None:
        """Calculate current hash after initialization."""
        if not self.current_hash:
            self.current_hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """
        Calculate SHA256 hash of (candidate + timestamp + previous_hash).
        
        Returns:
            Hex digest of SHA256 hash
        """
        hash_input = f"{self.candidate}{self.timestamp.isoformat()}{self.previous_hash}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def verify_integrity(self) -> bool:
        """
        Verify that current_hash matches calculated hash.
        
        Returns:
            True if vote hash is valid, False otherwise
        """
        calculated = self.calculate_hash()
        return self.current_hash == calculated
    
    def compute_vote_hmac(self, signing_key: bytes) -> str:
        """Compute HMAC-SHA256 over canonical vote fields."""
        payload = (
            f"{self.vote_id}\x00{self.voter_id}\x00{self.candidate}"
            f"\x00{self.timestamp.isoformat()}\x00{self.previous_hash}"
        ).encode()
        return _hmac.new(signing_key, payload, "sha256").hexdigest()

    def verify_vote_hmac(self, signing_key: bytes) -> bool:
        """Verify stored vote_hmac matches computed value."""
        if not self.vote_hmac:
            return False
        expected = self.compute_vote_hmac(signing_key)
        return _hmac.compare_digest(expected, self.vote_hmac)

    def verify_chain_link(self, previous_vote: Optional['Vote']) -> bool:
        """
        Verify that this vote is properly linked to the previous vote.
        
        Args:
            previous_vote: The previous vote in the chain (None for first vote)
            
        Returns:
            True if chain linkage is valid
        """
        if previous_vote is None:
            # First vote should reference genesis hash
            return self.previous_hash == "0" * 64
        return self.previous_hash == previous_vote.current_hash
    
    def __str__(self) -> str:
        return f"Vote(id={self.vote_id}, candidate={self.candidate}, hash={self.current_hash[:8]}...)"
    
    def __repr__(self) -> str:
        return self.__str__()
