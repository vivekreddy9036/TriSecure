"""
Blockchain-Ready Vote Logger.

Prepares vote integrity layer for blockchain integration.
Implements hash chaining and append-only semantics for blockchain compatibility.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List

from models import Vote
from repositories import VoteRepositoryBase

logger = logging.getLogger(__name__)


@dataclass
class BlockchainRecord:
    """Record compatible with blockchain systems."""
    
    block_hash: str  # Current block hash
    previous_hash: str  # Previous block hash
    data: str  # Vote data
    timestamp: str  # ISO timestamp
    nonce: int = 0  # For PoW systems (future)


class BlockchainLogger:
    """
    Blockchain-ready vote logging layer.
    
    Features:
    - Internal hash chaining (blockchain-style)
    - Append-only vote log
    - Chain verification
    - Blockchain export format
    - Ready for external blockchain integration
    
    Architecture:
    - Delegates to VoteRepository for persistence
    - Implements blockchain compatibility layer
    - Separates blockchain logic from voting logic
    - Designed for future ledger integration
    
    Blockchain Integration Roadmap:
    1. Current: Internal hash chaining (tamper-proof)
    2. Phase 2: Ethereum smart contract logging
    3. Phase 3: Hyperledger Fabric channel
    4. Phase 4: Distributed voter database sync
    """
    
    def __init__(self, vote_repository: VoteRepositoryBase):
        """
        Initialize blockchain logger.
        
        Args:
            vote_repository: Vote persistence layer
        """
        self.vote_repository = vote_repository
        logger.info("BlockchainLogger initialized (internal hash chaining mode)")
    
    def log_vote(self, vote: Vote) -> Vote:
        """
        Log vote to blockchain-compatible log.
        
        Performs:
        1. Calculates previous hash from last vote
        2. Appends vote with hash chaining
        3. Returns logging result
        
        Args:
            vote: Vote object to log
            
        Returns:
            Logged vote with hash chains set
        """
        try:
            # Append to vote repository (handles hash chain)
            logged_vote = self.vote_repository.append_vote(vote)
            logger.info(f"Vote logged to blockchain chain: {logged_vote.vote_id}")
            return logged_vote
        
        except Exception as e:
            logger.error(f"Failed to log vote: {e}")
            raise
    
    def get_blockchain_record(self, vote: Vote) -> BlockchainRecord:
        """
        Get blockchain-compatible record for a vote.
        
        Args:
            vote: Vote object
            
        Returns:
            BlockchainRecord with blockchain fields
        """
        return BlockchainRecord(
            block_hash=vote.current_hash,
            previous_hash=vote.previous_hash,
            data=f"vote:{vote.voter_id}:{vote.candidate}",
            timestamp=vote.timestamp.isoformat(),
            nonce=0
        )
    
    def export_to_blockchain_format(self) -> List[BlockchainRecord]:
        """
        Export entire vote log in blockchain format.
        
        Returns:
            List of BlockchainRecord objects
        """
        votes = self.vote_repository.get_all_votes()
        records = [self.get_blockchain_record(vote) for vote in votes]
        logger.info(f"Exported {len(records)} votes to blockchain format")
        return records
    
    def verify_blockchain_integrity(self) -> bool:
        """
        Verify integrity of blockchain-style vote chain.
        
        Delegated to vote repository chain verification.
        
        Returns:
            True if chain is valid and tamper-proof
        """
        valid = self.vote_repository.verify_chain()
        status = "VALID" if valid else "COMPROMISED"
        logger.info(f"Blockchain integrity check: {status}")
        return valid
    
    def get_blockchain_statistics(self) -> dict:
        """
        Get statistics about the blockchain-style vote log.
        
        Returns:
            Dictionary with blockchain stats
        """
        votes = self.vote_repository.get_all_votes()
        
        # Count votes per candidate
        candidate_counts = {}
        for vote in votes:
            candidate_counts[vote.candidate] = candidate_counts.get(vote.candidate, 0) + 1
        
        stats = {
            'total_votes': len(votes),
            'chain_valid': self.verify_blockchain_integrity(),
            'votes_per_candidate': candidate_counts,
            'first_vote': votes[0].timestamp.isoformat() if votes else None,
            'last_vote': votes[-1].timestamp.isoformat() if votes else None,
            'chain_height': len(votes)
        }
        
        return stats


class SmartContractInterface:
    """
    Placeholder interface for future Ethereum smart contract integration.
    
    Design:
    - At Phase 2, implement Eth contract deployment
    - Store vote hashes on Ethereum for distributed verification
    - Maintain local copy for offline operation
    - Sync with contract periodically
    """
    
    def __init__(self, contract_address: Optional[str] = None):
        """
        Initialize smart contract interface.
        
        Args:
            contract_address: Ethereum contract address (when deployed)
        """
        self.contract_address = contract_address
        self._available = contract_address is not None
        
        if not self._available:
            logger.warning("Smart contract not deployed. Running in local-only mode.")
    
    def deploy_contract(self, web3_provider: str) -> str:
        """
        Deploy voting contract to blockchain.
        
        Args:
            web3_provider: Web3.py provider URL (e.g., Infura)
            
        Returns:
            Contract address
            
        Raises:
            NotImplementedError: Until Phase 2
        """
        raise NotImplementedError("Smart contract deployment not yet available")
    
    def post_vote_hash(self, vote_hash: str) -> bool:
        """
        Post vote hash to blockchain.
        
        Args:
            vote_hash: SHA256 hash of encrypted vote
            
        Returns:
            True if posted successfully
            
        Raises:
            NotImplementedError: Until Phase 2
        """
        raise NotImplementedError("Smart contract posting not yet available")
    
    def verify_vote_on_chain(self, vote_hash: str) -> bool:
        """
        Verify vote hash exists on blockchain.
        
        Args:
            vote_hash: Hash to verify
            
        Returns:
            True if hash found on chain
            
        Raises:
            NotImplementedError: Until Phase 2
        """
        raise NotImplementedError("Smart contract verification not yet available")
