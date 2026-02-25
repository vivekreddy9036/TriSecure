"""
TRIsecure - Production-Grade Secure eVoting System
Raspberry Pi 4 + Ubuntu 22.04 ARM + Face Recognition + NFC + Hash-Chaining

Main entry point and system orchestration.
"""

import logging
import sys
import signal
from typing import Optional
from uuid import uuid4
from datetime import datetime

# Import architecture layers
from config import get_config, setup_logging, DeploymentMode
from models import Voter, Vote, Session, AuditEvent, EventType, EventStatus
from core import SessionManager, AuditLogger, AuthenticationPipeline, AuthenticationResult
from repositories import SQLiteVoterRepository, SQLiteVoteRepository, SQLiteAuditRepository
from services import NFCService, CameraService, FaceService
from security import BlockchainLogger, EncryptionHooks

logger = logging.getLogger(__name__)


class TRIsecureSystem:
    """
    Main TRIsecure system controller.
    
    Responsibilities:
    - Initialize all subsystems
    - Orchestrate hardware interfaces
    - Manage voting workflow
    - Handle graceful shutdown
    
    Architecture:
    - Dependency injection of services
    - Hardware abstraction via service layer
    - Clean separation of concerns
    - Production-ready error handling
    """
    
    def __init__(self):
        """Initialize TRIsecure system."""
        self.config = get_config()
        self.logger = logging.getLogger(__name__)
        
        # Repositories
        self.voter_repo = SQLiteVoterRepository(self.config.DATABASE_PATH)
        self.vote_repo = SQLiteVoteRepository(self.config.DATABASE_PATH)
        self.audit_repo = SQLiteAuditRepository(self.config.DATABASE_PATH)
        
        # Core services
        self.audit_logger = AuditLogger(self.audit_repo)
        self.session_manager = SessionManager(self.config.SESSION_DURATION_SECONDS)
        
        # Hardware services
        self.nfc_service = None
        self.camera_service = None
        self.face_service = None
        
        # Authentication
        self.auth_pipeline = None
        
        # Security
        self.blockchain_logger = BlockchainLogger(self.vote_repo)
        self.encryption_hooks = EncryptionHooks()
        
        # State
        self.running = False
        
        self.logger.info("TRIsecure system initialized")
    
    def initialize(self) -> bool:
        """
        Initialize all subsystems.
        
        Returns:
            True if initialization successful
        """
        self.logger.info("=" * 70)
        self.logger.info("TRISECURE INITIALIZATION")
        self.logger.info(f"Mode: {self.config.MODE.value}")
        self.logger.info(f"Database: {self.config.DATABASE_PATH}")
        self.logger.info("=" * 70)
        
        try:
            # Initialize hardware services
            self._initialize_hardware_services()
            
            # Initialize authentication pipeline
            self.auth_pipeline = AuthenticationPipeline(
                voter_repository=self.voter_repo,
                session_manager=self.session_manager,
                audit_logger=self.audit_logger,
                face_match_threshold=self.config.FACE_MATCH_THRESHOLD
            )
            
            self.audit_logger.log_event(
                EventType.CONFIG_LOADED,
                EventStatus.SUCCESS,
                f"System initialized in {self.config.MODE.value} mode"
            )
            
            self.logger.info("✓ TRIsecure initialization complete")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ Initialization failed: {e}", exc_info=True)
            self.audit_logger.log_system_error(f"Initialization failed: {e}")
            return False
    
    def _initialize_hardware_services(self) -> None:
        """Initialize NFC, Camera, and Face services."""
        # NFC Service
        if self.config.NFC_ENABLED:
            self.logger.info("Initializing NFC service...")
            self.nfc_service = NFCService(
                i2c_address=self.config.NFC_I2C_ADDRESS,
                i2c_bus=self.config.NFC_I2C_BUS,
                timeout=self.config.NFC_TIMEOUT
            )
            nfc_ok = self.nfc_service.initialize()
            self.logger.info(f"  NFC: {'✓ Ready' if nfc_ok else '⚠ Simulation mode'}")
        
        # Camera Service
        if self.config.CAMERA_ENABLED:
            self.logger.info("Initializing camera service...")
            self.camera_service = CameraService(
                device=self.config.CAMERA_DEVICE,
                width=self.config.CAMERA_WIDTH,
                height=self.config.CAMERA_HEIGHT,
                fps=self.config.CAMERA_FPS
            )
            cam_ok = self.camera_service.initialize()
            self.logger.info(f"  Camera: {'✓ Ready' if cam_ok else '⚠ Simulation mode'}")
        
        # Face Service
        if self.config.FACE_ENABLED:
            self.logger.info("Initializing face recognition service...")
            self.face_service = FaceService(
                model=self.config.FACE_MODEL,
                jitter=self.config.FACE_JITTER
            )
            face_ok = self.face_service.initialize()
            self.logger.info(f"  Face: {'✓ Ready' if face_ok else '⚠ Simulation mode'}")
    
    def register_voter_workflow(self, name: str) -> Optional[Voter]:
        """
        Register a new voter (Voter Registration Mode).
        
        Flow:
        1. Prompt for voter name
        2. Request NFC card registration
        3. Capture face for embedding
        4. Store voter with encrypted embedding
        5. Log audit event
        
        Args:
            name: Voter full name
            
        Returns:
            Registered Voter object or None if failed
        """
        self.logger.info(f"Starting voter registration: {name}")
        
        try:
            # Create voter
            voter = Voter(name=name)
            
            # 1. Capture NFC
            if self.nfc_service:
                self.logger.info("  → Present NFC card")
                try:
                    voter.nfc_uid = self.nfc_service.read_card_blocking()
                    self.audit_logger.log_event(
                        EventType.VOTER_NFC_REGISTERED,
                        EventStatus.SUCCESS,
                        f"NFC registered for {name}"
                    )
                except RuntimeError as e:
                    self.logger.error(f"NFC registration failed: {e}")
                    return None
            
            # 2. Capture face embedding
            if self.camera_service and self.face_service:
                self.logger.info("  → Capturing face image")
                frame = self.camera_service.capture_frame_for_embedding()
                if frame is not None:
                    embedding_result = self.face_service.generate_embedding(frame)
                    if embedding_result.success:
                        voter.face_embedding = embedding_result.embedding.tobytes()
                        self.audit_logger.log_event(
                            EventType.VOTER_FACE_REGISTERED,
                            EventStatus.SUCCESS,
                            f"Face embedding captured for {name}"
                        )
            
            # 3. Save voter
            voter = self.voter_repo.save(voter)
            self.audit_logger.log_event(
                EventType.VOTER_REGISTERED,
                EventStatus.SUCCESS,
                f"Voter registered: {name}",
                voter_id=voter.id
            )
            
            self.logger.info(f"✓ Voter registered: {voter.id}")
            return voter
        
        except Exception as e:
            self.logger.error(f"Voter registration failed: {e}", exc_info=True)
            self.audit_logger.log_system_error(f"Voter registration failed: {e}")
            return None
    
    def voting_workflow(self, candidate: str) -> bool:
        """
        Execute voting workflow (Strict Authentication Pipeline).
        
        Flow:
        1. Read NFC card
        2. Verify voter exists and hasn't voted
        3. Capture and verify face
        4. Issue 60-second session token
        5. Cast vote
        6. Mark voter as voted
        7. Log to blockchain-style chain
        8. Audit log
        
        Args:
            candidate: Candidate identifier
            
        Returns:
            True if vote cast successfully
        """
        self.logger.info(f"Starting voting workflow for candidate: {candidate}")
        
        try:
            # Step 1: Read NFC
            if not self.nfc_service:
                self.logger.error("NFC service not available")
                return False
            
            nfc_result = self.nfc_service.read_card()
            if not nfc_result.success or not nfc_result.uid:
                self.logger.error(f"NFC read failed: {nfc_result.error_message}")
                return False
            
            nfc_uid = nfc_result.uid
            self.logger.info(f"  → NFC card read: {nfc_uid}")
            
            # Step 2-5: Authentication pipeline
            face_embedding = None
            if self.camera_service and self.face_service:
                frame = self.camera_service.capture_frame_for_embedding()
                if frame is not None:
                    emb_result = self.face_service.generate_embedding(frame)
                    if emb_result.success:
                        face_embedding = emb_result.embedding.tobytes()
            
            auth_result = self.auth_pipeline.authenticate(
                nfc_uid=nfc_uid,
                face_embedding=face_embedding
            )
            
            if not auth_result.success or not auth_result.session:
                self.logger.error(f"Authentication failed: {auth_result.message}")
                return False
            
            session = auth_result.session
            self.logger.info(f"  → Session issued: {session.session_id}")
            
            # Step 6: Cast vote
            voter = self.voter_repo.find_by_nfc_uid(nfc_uid)
            if not voter:
                self.logger.error("Voter disappeared after authentication (data corruption)")
                return False
            
            vote = Vote(
                voter_id=voter.id,
                candidate=candidate
            )
            
            # Step 7: Append to blockchain log
            vote = self.blockchain_logger.log_vote(vote)
            
            # Step 8: Mark voter as voted
            voter.mark_as_voted()
            self.voter_repo.save(voter)
            
            # Step 9: Audit
            self.audit_logger.log_vote_cast(voter.id, candidate)
            
            # Deactivate session
            self.session_manager.deactivate_session(session.token)
            
            self.logger.info(f"✓ Vote cast successfully for {candidate}")
            return True
        
        except Exception as e:
            self.logger.error(f"Voting workflow failed: {e}", exc_info=True)
            self.audit_logger.log_system_error(f"Voting failed: {e}")
            return False
    
    def display_statistics(self) -> None:
        """Display voting system statistics."""
        self.logger.info("=" * 70)
        self.logger.info("TRISECURE STATISTICS")
        self.logger.info("=" * 70)
        
        # Voters
        voters = self.voter_repo.find_all()
        voted_count = sum(1 for v in voters if v.has_voted)
        self.logger.info(f"Registered Voters: {len(voters)}")
        self.logger.info(f"Voted: {voted_count}")
        self.logger.info(f"Eligible: {len(voters) - voted_count}")
        
        # Votes
        stats = self.blockchain_logger.get_blockchain_statistics()
        self.logger.info(f"\nVotes Cast: {stats['total_votes']}")
        self.logger.info(f"Blockchain Valid: {'✓ Yes' if stats['chain_valid'] else '✗ No'}")
        
        if stats['votes_per_candidate']:
            self.logger.info("\nVotes Per Candidate:")
            for candidate, count in stats['votes_per_candidate'].items():
                self.logger.info(f"  {candidate}: {count}")
        
        # Audit
        events = self.audit_repo.get_recent(10)
        self.logger.info(f"\nRecent Audit Events: {len(events)}")
        for event in events[:3]:
            self.logger.info(f"  [{event.event_type.value}] {event.message}")
        
        self.logger.info("=" * 70)
    
    def verify_vote_integrity(self) -> bool:
        """
        Verify vote chain integrity.
        
        Returns:
            True if blockchain is valid (no tampering)
        """
        valid = self.blockchain_logger.verify_blockchain_integrity()
        status = "✓ VALID" if valid else "✗ COMPROMISED"
        self.logger.info(f"Vote Integrity: {status}")
        return valid
    
    def cleanup(self) -> None:
        """Clean shutdown of all subsystems."""
        self.logger.info("Shutting down TRIsecure...")
        
        # Cleanup session manager
        if self.session_manager:
            self.session_manager.cleanup_expired_sessions()
        
        # Close hardware
        if self.nfc_service:
            self.nfc_service.close()
        if self.camera_service:
            self.camera_service.close()
        
        self.audit_logger.log_event(
            EventType.CONFIG_LOADED,
            EventStatus.SUCCESS,
            "System shutdown complete"
        )
        
        self.logger.info("✓ TRIsecure shutdown complete")


def main():
    """
    Main entry point for TRIsecure system.
    
    Entry point for systemd service or standalone execution.
    """
    # Configuration
    config = get_config()
    setup_logging(config)
    
    logger.info("╔═══════════════════════════════════════════════════════════════════╗")
    logger.info("║           TRISECURE - SECURE eVOTING SYSTEM v1.0                 ║")
    logger.info("║      Raspberry Pi 4 + Ubuntu ARM + Face Recognition + NFC         ║")
    logger.info("╚═══════════════════════════════════════════════════════════════════╝")
    
    # Initialize system
    system = TRIsecureSystem()
    
    if not system.initialize():
        logger.error("Failed to initialize system")
        sys.exit(1)
    
    # Signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        system.cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Example usage - In production, this would be a CLI or web UI
    if config.is_development():
        logger.info("\nDeveloper Mode: Running example workflow...")
        
        # Register a voter
        voter = system.register_voter_workflow("John Doe")
        if voter:
            logger.info(f"Voter registered: {voter.id}")
        
        # Cast a vote
        success = system.voting_workflow("Candidate A")
        logger.info(f"Vote cast: {'✓ Success' if success else '✗ Failed'}")
        
        # Display stats
        system.display_statistics()
        
        # Verify integrity
        system.verify_vote_integrity()
    else:
        logger.info("Production mode: Waiting for commands...")
        logger.info("(This would be controlled by CLI or API)")
    
    system.cleanup()


if __name__ == "__main__":
    main()
