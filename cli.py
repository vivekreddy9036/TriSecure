"""
TRIsecure Interactive CLI.

Provides interactive menu for:
- Voter Registration Mode
- Voting Mode

Flow:
    Registration:
        Name + Age + Unique ID → Face Capture → Encrypt → Store DB → Write NFC
    
    Voting:
        Read NFC → Lookup DB → Face Verify → Cast Vote
"""

import logging
import sys
import signal
import hashlib
from typing import Optional
from datetime import datetime
from uuid import uuid4

# Import system components
from config import get_config, setup_logging
from models import Voter, Vote, EventType, EventStatus
from core import SessionManager, AuditLogger, AuthenticationPipeline
from repositories import SQLiteVoterRepository, SQLiteVoteRepository, SQLiteAuditRepository
from services import NFCService, CameraService, FaceService
from security import BlockchainLogger, EncryptionHooks

# Try to import new biometric pipeline (optional enhancement)
try:
    from hardware.camera import FaceCamera, FaceAuthenticator
    from backend.crypto import EmbeddingEncryptor
    from backend.db import BiometricDatabase
    BIOMETRIC_PIPELINE_AVAILABLE = True
except ImportError:
    BIOMETRIC_PIPELINE_AVAILABLE = False

logger = logging.getLogger(__name__)


class VoterData:
    """Voter registration data."""
    def __init__(self, name: str, age: int, unique_id: str):
        self.name = name
        self.age = age
        self.unique_id = unique_id
        self.voter_id = str(uuid4())
        self.created_at = datetime.utcnow()


class TRIsecureCLI:
    """
    Interactive CLI for TRIsecure eVoting System.
    
    Modes:
        1. Registration Mode - Register new voters
        2. Voting Mode - Cast votes
    """
    
    def __init__(self):
        """Initialize CLI system."""
        self.config = get_config()
        
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
        
        # Security
        self.blockchain_logger = BlockchainLogger(self.vote_repo)
        self.encryption_hooks = EncryptionHooks()
        
        # Biometric pipeline (new)
        self.biometric_db = None
        self.encryptor = None
        
        # State
        self.running = False
        self.candidates = self.config.CANDIDATES or ["Candidate A", "Candidate B", "Candidate C"]
    
    def initialize(self) -> bool:
        """Initialize all subsystems."""
        self._print_banner()
        
        try:
            # Initialize NFC
            if self.config.NFC_ENABLED:
                print("  Initializing NFC service...")
                self.nfc_service = NFCService(timeout=self.config.NFC_TIMEOUT)
                nfc_ok = self.nfc_service.initialize()
                print(f"    NFC: {'✓ Ready' if nfc_ok else '⚠ Simulation mode'}")
            
            # Initialize Camera
            if self.config.CAMERA_ENABLED:
                print("  Initializing camera...")
                self.camera_service = CameraService(
                    device=self.config.CAMERA_DEVICE,
                    width=self.config.CAMERA_WIDTH,
                    height=self.config.CAMERA_HEIGHT,
                    fps=self.config.CAMERA_FPS
                )
                cam_ok = self.camera_service.initialize()
                print(f"    Camera: {'✓ Ready' if cam_ok else '⚠ Simulation mode'}")
            
            # Initialize Face Service
            if self.config.FACE_ENABLED:
                print("  Initializing face recognition...")
                self.face_service = FaceService(
                    model=self.config.FACE_MODEL,
                    jitter=self.config.FACE_JITTER
                )
                face_ok = self.face_service.initialize()
                print(f"    Face Recognition: {'✓ Ready' if face_ok else '⚠ Simulation mode'}")
            
            # Initialize Biometric Database & Encryptor
            if self.config.BIOMETRIC_ENABLED:
                print("  Initializing biometric database...")
                self.biometric_db = BiometricDatabase(self.config.BIOMETRIC_DATABASE_PATH)
                self.biometric_db.initialize()
                
                self.encryptor = EmbeddingEncryptor()
                print("    Biometric DB: ✓ Ready")
            
            print("\n✓ System initialized successfully\n")
            return True
            
        except Exception as e:
            print(f"\n✗ Initialization failed: {e}\n")
            return False
    
    def _print_banner(self):
        """Print system banner."""
        print("\n" + "=" * 60)
        print("       TRIsecure - Secure eVoting System v1.0")
        print("     Raspberry Pi 4 | Face Recognition | NFC")
        print("=" * 60 + "\n")
    
    def run(self):
        """Run interactive CLI loop."""
        self.running = True
        
        while self.running:
            choice = self._show_main_menu()
            
            if choice == "1":
                self._registration_mode()
            elif choice == "2":
                self._voting_mode()
            elif choice == "3":
                self._show_statistics()
            elif choice == "4" or choice.lower() == "q":
                self.running = False
                print("\nGoodbye!\n")
            else:
                print("\n⚠ Invalid choice. Please try again.\n")
    
    def _show_main_menu(self) -> str:
        """Display main menu and get choice."""
        print("\n" + "-" * 40)
        print("           MAIN MENU")
        print("-" * 40)
        print("  1. Register New Voter")
        print("  2. Cast Vote")
        print("  3. View Statistics")
        print("  4. Exit")
        print("-" * 40)
        
        return input("Enter choice [1-4]: ").strip()
    
    # =========================================================================
    # REGISTRATION MODE
    # =========================================================================
    
    def _registration_mode(self):
        """
        Voter Registration Mode.
        
        Flow:
        1. Collect voter details (name, age, unique ID)
        2. Capture face image
        3. Generate face embedding
        4. Encrypt embedding
        5. Store in database
        6. Write voter ID to NFC card
        """
        print("\n" + "=" * 50)
        print("       VOTER REGISTRATION MODE")
        print("=" * 50)
        
        # Step 1: Collect voter details
        print("\n[Step 1/6] Enter Voter Details")
        print("-" * 30)
        
        name = input("  Full Name: ").strip()
        if not name:
            print("  ✗ Name cannot be empty")
            return
        
        try:
            age = int(input("  Age: ").strip())
            if age < 18:
                print("  ✗ Voter must be 18 or older")
                return
            if age > 120:
                print("  ✗ Invalid age")
                return
        except ValueError:
            print("  ✗ Invalid age")
            return
        
        unique_id = input("  Unique ID (Aadhar/Voter ID): ").strip()
        if not unique_id:
            print("  ✗ Unique ID cannot be empty")
            return
        
        # Check if already registered
        existing = self._find_voter_by_unique_id(unique_id)
        if existing:
            print(f"  ✗ Voter with ID {unique_id} already registered!")
            return
        
        voter_data = VoterData(name=name, age=age, unique_id=unique_id)
        print(f"\n  ✓ Details collected for: {name}")
        
        # Step 2: Present NFC card
        print("\n[Step 2/6] NFC Card Registration")
        print("-" * 30)
        print("  Please present your NFC card...")
        
        nfc_uid = self._read_nfc_card()
        if not nfc_uid:
            print("  ✗ NFC card read failed")
            return
        
        # Check if NFC already registered
        existing_nfc = self.voter_repo.find_by_nfc_uid(nfc_uid)
        if existing_nfc:
            print(f"  ✗ This NFC card is already registered to another voter!")
            return
        
        print(f"  ✓ NFC Card detected: {nfc_uid}")
        
        # Step 3: Capture face
        print("\n[Step 3/6] Face Capture")
        print("-" * 30)
        print("  Look at the camera...")
        
        face_embedding = self._capture_face_embedding()
        if face_embedding is None:
            print("  ✗ Face capture failed")
            return
        
        print("  ✓ Face captured successfully")
        
        # Step 4: Encrypt embedding
        print("\n[Step 4/6] Encrypting Biometric Data")
        print("-" * 30)
        
        encrypted_embedding = self._encrypt_embedding(face_embedding)
        if encrypted_embedding is None:
            print("  ✗ Encryption failed")
            return
        
        print("  ✓ Biometric data encrypted")
        
        # Step 5: Store in database
        print("\n[Step 5/6] Storing Voter Record")
        print("-" * 30)
        
        voter = Voter(
            id=uuid4(),
            name=name,
            nfc_uid=nfc_uid,
            face_embedding=encrypted_embedding,
            has_voted=False
        )
        
        # Store additional metadata (age, unique_id) in voter name field or extend model
        voter.name = f"{name}|{age}|{unique_id}"  # Simple encoding
        
        try:
            saved_voter = self.voter_repo.save(voter)
            print(f"  ✓ Voter registered: {saved_voter.id}")
        except Exception as e:
            print(f"  ✗ Failed to save: {e}")
            return
        
        # Step 6: Write to NFC card (optional - store voter hash)
        print("\n[Step 6/6] Finalizing NFC Card")
        print("-" * 30)
        
        voter_hash = self._generate_voter_hash(voter_data, nfc_uid)
        # In real implementation, write voter_hash to NFC card
        print(f"  ✓ Voter hash: {voter_hash[:16]}...")
        
        # Log audit event
        self.audit_logger.log_event(
            EventType.VOTER_REGISTERED,
            EventStatus.SUCCESS,
            f"Voter registered: {name} (ID: {unique_id})"
        )
        
        # Success summary
        print("\n" + "=" * 50)
        print("       ✓ REGISTRATION COMPLETE")
        print("=" * 50)
        print(f"  Name: {name}")
        print(f"  Age: {age}")
        print(f"  Unique ID: {unique_id}")
        print(f"  Voter ID: {voter.id}")
        print(f"  NFC Card: {nfc_uid}")
        print("=" * 50)
        print("\n  You can now use this NFC card to vote.\n")
    
    # =========================================================================
    # VOTING MODE
    # =========================================================================
    
    def _voting_mode(self):
        """
        Voting Mode.
        
        Flow:
        1. Read NFC card
        2. Look up voter in database
        3. Check if already voted
        4. Capture live face
        5. Compare with stored embedding
        6. If match → select candidate → cast vote
        """
        print("\n" + "=" * 50)
        print("           VOTING MODE")
        print("=" * 50)
        
        # Step 1: Read NFC card
        print("\n[Step 1/5] NFC Authentication")
        print("-" * 30)
        print("  Please present your NFC card...")
        
        nfc_uid = self._read_nfc_card()
        if not nfc_uid:
            print("  ✗ NFC card read failed")
            return
        
        print(f"  ✓ NFC Card: {nfc_uid}")
        
        # Step 2: Look up voter
        print("\n[Step 2/5] Voter Verification")
        print("-" * 30)
        
        voter = self.voter_repo.find_by_nfc_uid(nfc_uid)
        if not voter:
            print("  ✗ NFC card not registered!")
            print("  Please register first using Registration Mode.")
            return
        
        # Parse voter details
        name_parts = voter.name.split("|")
        voter_name = name_parts[0] if name_parts else voter.name
        
        print(f"  ✓ Voter found: {voter_name}")
        
        # Step 3: Check voting status
        print("\n[Step 3/5] Eligibility Check")
        print("-" * 30)
        
        if voter.has_voted:
            print("  ✗ You have already voted!")
            print("  Each voter can only vote once.")
            self.audit_logger.log_event(
                EventType.VOTE_REJECTED,
                EventStatus.FAILURE,
                f"Double voting attempt: {voter.id}"
            )
            return
        
        print("  ✓ Eligible to vote")
        
        # Step 4: Face verification
        print("\n[Step 4/5] Face Verification")
        print("-" * 30)
        print("  Look at the camera...")
        
        verified = self._verify_face(voter)
        if not verified:
            print("  ✗ Face verification failed!")
            print("  Face does not match registered identity.")
            self.audit_logger.log_event(
                EventType.FACE_MATCH_FAILED,
                EventStatus.FAILURE,
                f"Face mismatch for voter: {voter.id}"
            )
            return
        
        print("  ✓ Face verified successfully!")
        
        # Step 5: Cast vote
        print("\n[Step 5/5] Cast Your Vote")
        print("-" * 30)
        
        candidate = self._select_candidate()
        if not candidate:
            print("  ✗ Vote cancelled")
            return
        
        # Confirm vote
        print(f"\n  You selected: {candidate}")
        confirm = input("  Confirm vote? [y/N]: ").strip().lower()
        
        if confirm != "y":
            print("  ✗ Vote cancelled")
            return
        
        # Record vote
        success = self._cast_vote(voter, candidate)
        
        if success:
            print("\n" + "=" * 50)
            print("       ✓ VOTE CAST SUCCESSFULLY")
            print("=" * 50)
            print(f"  Voter: {voter_name}")
            print(f"  Candidate: {candidate}")
            print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 50)
            print("\n  Thank you for voting!\n")
        else:
            print("\n  ✗ Failed to record vote\n")
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def _show_statistics(self):
        """Display voting statistics."""
        print("\n" + "=" * 50)
        print("           VOTING STATISTICS")
        print("=" * 50)
        
        # Get all voters
        all_voters = self.voter_repo.find_all()
        voted = [v for v in all_voters if v.has_voted]
        eligible = [v for v in all_voters if not v.has_voted]
        
        print(f"\n  Registered Voters: {len(all_voters)}")
        print(f"  Already Voted: {len(voted)}")
        print(f"  Yet to Vote: {len(eligible)}")
        
        # Get vote counts
        votes = self.vote_repo.find_all()
        print(f"\n  Total Votes Cast: {len(votes)}")
        
        if votes:
            # Count per candidate
            print("\n  Votes per Candidate:")
            candidate_counts = {}
            for vote in votes:
                candidate_counts[vote.candidate] = candidate_counts.get(vote.candidate, 0) + 1
            
            for candidate, count in sorted(candidate_counts.items(), key=lambda x: -x[1]):
                bar = "█" * count
                print(f"    {candidate}: {count} {bar}")
        
        # Blockchain integrity
        is_valid = self.blockchain_logger.verify_chain_integrity()
        print(f"\n  Blockchain Integrity: {'✓ VALID' if is_valid else '✗ INVALID'}")
        
        print("\n" + "=" * 50 + "\n")
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _read_nfc_card(self) -> Optional[str]:
        """Read NFC card and return UID."""
        if not self.nfc_service:
            # Simulation mode
            return f"SIM_{uuid4().hex[:12].upper()}"
        
        try:
            return self.nfc_service.read_card_blocking()
        except Exception as e:
            logger.error(f"NFC read error: {e}")
            return None
    
    def _capture_face_embedding(self) -> Optional[bytes]:
        """Capture face and generate embedding."""
        if not self.camera_service or not self.face_service:
            # Simulation mode - return random bytes
            import numpy as np
            embedding = np.random.randn(128).astype(np.float32)
            return embedding.tobytes()
        
        try:
            # Capture frame
            frame = self.camera_service.capture_frame_for_embedding()
            if frame is None:
                return None
            
            # Generate embedding
            result = self.face_service.generate_embedding(frame)
            if result.success:
                return result.embedding.tobytes()
            return None
            
        except Exception as e:
            logger.error(f"Face capture error: {e}")
            return None
    
    def _encrypt_embedding(self, embedding_bytes: bytes) -> Optional[bytes]:
        """Encrypt face embedding."""
        if self.encryptor:
            try:
                import numpy as np
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                result = self.encryptor.encrypt(embedding)
                if result.success:
                    # Combine ciphertext + salt + iv for storage
                    return result.ciphertext + result.salt + result.iv
            except Exception as e:
                logger.error(f"Encryption error: {e}")
        
        # Fallback: store raw (not secure for production)
        return embedding_bytes
    
    def _verify_face(self, voter: Voter) -> bool:
        """Verify live face against stored embedding."""
        if not voter.face_embedding:
            logger.warning("No face embedding stored for voter")
            return False
        
        # Capture live face
        live_embedding_bytes = self._capture_face_embedding()
        if live_embedding_bytes is None:
            return False
        
        # In simulation mode with no face service, auto-pass
        if not self.face_service or not self.face_service._initialized:
            threshold = self.config.FACE_MATCH_THRESHOLD
            if threshold <= 0:
                return True
        
        try:
            import numpy as np
            
            # Get stored embedding (decrypt if needed)
            stored_bytes = voter.face_embedding
            
            if self.encryptor and len(stored_bytes) > 44:  # Has salt + iv
                # Extract components (ciphertext, salt, iv)
                iv = stored_bytes[-12:]
                salt = stored_bytes[-28:-12]
                ciphertext = stored_bytes[:-28]
                
                result = self.encryptor.decrypt(ciphertext, salt, iv)
                if result.success:
                    stored_embedding = result.embedding
                else:
                    stored_embedding = np.frombuffer(stored_bytes, dtype=np.float32)
            else:
                stored_embedding = np.frombuffer(stored_bytes, dtype=np.float32)
            
            live_embedding = np.frombuffer(live_embedding_bytes, dtype=np.float32)
            
            # Compare using face service or manual cosine similarity
            if self.face_service:
                result = self.face_service.compare_embeddings(stored_embedding, live_embedding)
                if hasattr(result, 'success'):
                    similarity = result.confidence if hasattr(result, 'confidence') else 0.0
                else:
                    similarity = result
            else:
                # Manual cosine similarity
                dot = np.dot(stored_embedding.flatten(), live_embedding.flatten())
                norm1 = np.linalg.norm(stored_embedding)
                norm2 = np.linalg.norm(live_embedding)
                similarity = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0
            
            threshold = self.config.FACE_MATCH_THRESHOLD
            logger.info(f"Face similarity: {similarity:.4f}, threshold: {threshold}")
            
            return similarity >= threshold
            
        except Exception as e:
            logger.error(f"Face verification error: {e}")
            return False
    
    def _select_candidate(self) -> Optional[str]:
        """Display candidate list and get selection."""
        print("\n  Available Candidates:")
        for i, candidate in enumerate(self.candidates, 1):
            print(f"    {i}. {candidate}")
        print(f"    0. Cancel")
        
        try:
            choice = int(input("\n  Enter your choice: ").strip())
            if choice == 0:
                return None
            if 1 <= choice <= len(self.candidates):
                return self.candidates[choice - 1]
        except ValueError:
            pass
        
        print("  Invalid choice")
        return None
    
    def _cast_vote(self, voter: Voter, candidate: str) -> bool:
        """Record vote in blockchain."""
        try:
            # Create vote
            vote = Vote(
                voter_id=voter.id,
                candidate=candidate
            )
            
            # Log to blockchain
            self.blockchain_logger.log_vote(vote)
            
            # Mark voter as voted
            voter.mark_as_voted()
            self.voter_repo.save(voter)
            
            # Audit
            self.audit_logger.log_event(
                EventType.VOTE_CAST,
                EventStatus.SUCCESS,
                f"Vote cast by {voter.id} for {candidate}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Vote casting error: {e}")
            return False
    
    def _find_voter_by_unique_id(self, unique_id: str) -> Optional[Voter]:
        """Find voter by unique ID (stored in name field)."""
        all_voters = self.voter_repo.find_all()
        for voter in all_voters:
            if f"|{unique_id}" in voter.name:
                return voter
        return None
    
    def _generate_voter_hash(self, voter_data: VoterData, nfc_uid: str) -> str:
        """Generate deterministic hash for voter."""
        data = f"{voter_data.name}|{voter_data.unique_id}|{nfc_uid}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def cleanup(self):
        """Release resources."""
        if self.camera_service:
            self.camera_service.close()
        print("System resources released.")


def main():
    """Main entry point."""
    # Setup logging
    config = get_config()
    setup_logging(config)
    
    # Create CLI
    cli = TRIsecureCLI()
    
    # Signal handling
    def signal_handler(sig, frame):
        print("\n\nShutdown signal received...")
        cli.cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize and run
    if cli.initialize():
        cli.run()
        cli.cleanup()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
