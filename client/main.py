"""
Biometric Client - Orchestration Layer.

This module orchestrates the biometric authentication pipeline,
connecting hardware, crypto, and database layers.

Design Principles:
- Orchestration only (no ML logic)
- No database queries (delegated to backend)
- No crypto operations (delegated to encryptor)
- No face detection/embedding (delegated to hardware)
- Clean separation of concerns

Flow (Enrollment):
    NFC tap → capture face → extract embedding → encrypt → store

Flow (Verification):
    NFC tap → capture face → extract embedding → 
    load encrypted template → decrypt → compare → approve/reject
"""

import logging
import gc
from typing import Optional, Tuple
from dataclasses import dataclass
from uuid import UUID

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EnrollmentResult:
    """Result of face enrollment operation."""
    success: bool
    user_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class VerificationResult:
    """Result of face verification operation."""
    success: bool
    verified: bool = False
    similarity: float = 0.0
    user_id: Optional[str] = None
    error_message: Optional[str] = None


class BiometricClient:
    """
    Biometric authentication orchestration client.
    
    Responsibilities:
    - Coordinate enrollment workflow
    - Coordinate verification workflow
    - Connect hardware, crypto, and database layers
    - Handle errors gracefully
    - Ensure security (clear sensitive data)
    
    Architecture:
    - Depends on hardware layer (face_auth)
    - Depends on backend.crypto (encryptor)
    - Depends on backend.db (database)
    - Contains NO ML code
    - Contains NO database queries
    - Contains NO crypto operations
    
    Usage:
        from hardware.camera import FaceCamera, FaceAuthenticator
        from backend.crypto import EmbeddingEncryptor
        from backend.db import BiometricDatabase
        from client import BiometricClient
        
        # Initialize components
        camera = FaceCamera()
        authenticator = FaceAuthenticator(threshold=0.55)
        encryptor = EmbeddingEncryptor(master_key="secret")
        database = BiometricDatabase("biometrics.db")
        
        # Create client
        client = BiometricClient(
            camera=camera,
            authenticator=authenticator,
            encryptor=encryptor,
            database=database
        )
        
        # Initialize all components
        client.initialize()
        
        # Enroll user
        result = client.enroll_user("user123")
        if result.success:
            print("Enrolled!")
        
        # Verify user
        result = client.verify_user("user123")
        if result.verified:
            print("Verified!")
        
        # Cleanup
        client.shutdown()
    """
    
    def __init__(
        self,
        camera,           # FaceCamera instance (hardware layer)
        authenticator,    # FaceAuthenticator instance (hardware layer)
        encryptor,        # EmbeddingEncryptor instance (backend.crypto)
        database,         # BiometricDatabase instance (backend.db)
        threshold: float = 0.55
    ):
        """
        Initialize biometric client.
        
        Args:
            camera: FaceCamera for face capture and detection
            authenticator: FaceAuthenticator for embedding extraction
            encryptor: EmbeddingEncryptor for AES encryption
            database: BiometricDatabase for template storage
            threshold: Similarity threshold for verification (0.5-0.6)
        """
        self._camera = camera
        self._authenticator = authenticator
        self._encryptor = encryptor
        self._database = database
        self._threshold = threshold
        
        self._initialized = False
        
        logger.debug(f"BiometricClient created: threshold={threshold}")
    
    def initialize(self) -> bool:
        """
        Initialize all subsystems.
        
        Returns:
            True if all components initialized successfully
            
        Raises:
            RuntimeError: If critical component fails to initialize
        """
        try:
            # Initialize camera
            logger.info("Initializing camera...")
            if not self._camera.initialize():
                raise RuntimeError("Camera initialization failed")
            
            # Initialize face authenticator
            logger.info("Initializing face authenticator...")
            if not self._authenticator.initialize():
                raise RuntimeError("Authenticator initialization failed")
            
            # Initialize database
            logger.info("Initializing biometric database...")
            if not self._database.initialize():
                raise RuntimeError("Database initialization failed")
            
            self._initialized = True
            logger.info("BiometricClient initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            raise RuntimeError(f"BiometricClient initialization failed: {e}")
    
    def enroll_user(self, user_id: str) -> EnrollmentResult:
        """
        Enroll a new user's face.
        
        Workflow:
        1. Capture face from camera
        2. Extract embedding using MobileFaceNet
        3. Encrypt embedding using AES-256-GCM
        4. Store encrypted embedding in database
        5. Clear sensitive data from memory
        
        Args:
            user_id: Unique user identifier (e.g., from NFC card)
            
        Returns:
            EnrollmentResult with success status
        """
        if not self._initialized:
            return EnrollmentResult(
                success=False,
                error_message="BiometricClient not initialized"
            )
        
        if not user_id:
            return EnrollmentResult(
                success=False,
                error_message="user_id cannot be empty"
            )
        
        logger.info(f"Starting enrollment for user: {user_id}")
        
        embedding = None
        face_image = None
        
        try:
            # Step 1: Capture face from camera
            logger.debug("Step 1: Capturing face...")
            detection_result = self._camera.capture_and_detect()
            
            if not detection_result.success:
                return EnrollmentResult(
                    success=False,
                    error_message=f"Face capture failed: {detection_result.error_message}"
                )
            
            if not detection_result.face_found if hasattr(detection_result, 'face_found') else detection_result.face_image is None:
                return EnrollmentResult(
                    success=False,
                    error_message="No face detected in frame"
                )
            
            face_image = detection_result.face_image
            
            # Step 2: Extract embedding
            logger.debug("Step 2: Extracting embedding...")
            embedding_result = self._authenticator.extract_embedding(face_image)
            
            if not embedding_result.success:
                return EnrollmentResult(
                    success=False,
                    error_message=f"Embedding extraction failed: {embedding_result.error_message}"
                )
            
            embedding = embedding_result.embedding
            
            # Step 3: Encrypt embedding
            logger.debug("Step 3: Encrypting embedding...")
            encryption_result = self._encryptor.encrypt(embedding)
            
            if not encryption_result.success:
                return EnrollmentResult(
                    success=False,
                    error_message=f"Encryption failed: {encryption_result.error_message}"
                )
            
            # Step 4: Store in database
            logger.debug("Step 4: Storing encrypted embedding...")
            stored = self._database.store_embedding(
                user_id=user_id,
                encrypted_embedding=encryption_result.ciphertext,
                salt=encryption_result.salt,
                iv=encryption_result.iv
            )
            
            if not stored:
                return EnrollmentResult(
                    success=False,
                    error_message="Failed to store embedding in database"
                )
            
            logger.info(f"User enrolled successfully: {user_id}")
            
            return EnrollmentResult(
                success=True,
                user_id=user_id
            )
            
        except Exception as e:
            logger.error(f"Enrollment failed: {e}")
            return EnrollmentResult(
                success=False,
                error_message=f"Enrollment failed: {e}"
            )
        
        finally:
            # Step 5: Clear sensitive data from memory
            self._clear_sensitive_data(embedding, face_image)
    
    def verify_user(self, user_id: str) -> VerificationResult:
        """
        Verify user's face against stored template.
        
        Workflow:
        1. Check if user has stored embedding
        2. Capture live face from camera
        3. Extract embedding from live face
        4. Retrieve and decrypt stored template
        5. Compare embeddings using cosine similarity
        6. Approve/reject based on threshold
        7. Clear sensitive data from memory
        
        Args:
            user_id: User identifier (e.g., from NFC card)
            
        Returns:
            VerificationResult with verification status and similarity score
        """
        if not self._initialized:
            return VerificationResult(
                success=False,
                error_message="BiometricClient not initialized"
            )
        
        if not user_id:
            return VerificationResult(
                success=False,
                error_message="user_id cannot be empty"
            )
        
        logger.info(f"Starting verification for user: {user_id}")
        
        live_embedding = None
        stored_embedding = None
        face_image = None
        
        try:
            # Step 1: Check if user has stored embedding
            logger.debug("Step 1: Checking for stored template...")
            if not self._database.has_embedding(user_id):
                return VerificationResult(
                    success=False,
                    error_message=f"No enrollment found for user: {user_id}"
                )
            
            # Step 2: Capture live face
            logger.debug("Step 2: Capturing live face...")
            detection_result = self._camera.capture_and_detect()
            
            if not detection_result.success:
                return VerificationResult(
                    success=False,
                    error_message=f"Face capture failed: {detection_result.error_message}"
                )
            
            if detection_result.face_image is None:
                return VerificationResult(
                    success=False,
                    error_message="No face detected in frame"
                )
            
            face_image = detection_result.face_image
            
            # Step 3: Extract embedding from live face
            logger.debug("Step 3: Extracting live embedding...")
            embedding_result = self._authenticator.extract_embedding(face_image)
            
            if not embedding_result.success:
                return VerificationResult(
                    success=False,
                    error_message=f"Embedding extraction failed: {embedding_result.error_message}"
                )
            
            live_embedding = embedding_result.embedding
            
            # Step 4: Retrieve and decrypt stored template
            logger.debug("Step 4: Retrieving stored template...")
            record = self._database.get_embedding(user_id)
            
            if not record:
                return VerificationResult(
                    success=False,
                    error_message="Failed to retrieve stored template"
                )
            
            logger.debug("Step 4b: Decrypting stored template...")
            decryption_result = self._encryptor.decrypt(
                ciphertext=record.encrypted_embedding,
                salt=record.salt,
                iv=record.iv
            )
            
            if not decryption_result.success:
                return VerificationResult(
                    success=False,
                    error_message=f"Decryption failed: {decryption_result.error_message}"
                )
            
            stored_embedding = decryption_result.embedding
            
            # Step 5: Compare embeddings
            logger.debug("Step 5: Comparing embeddings...")
            is_match, similarity = self._authenticator.compare_embeddings(
                live_embedding,
                stored_embedding,
                threshold=self._threshold
            )
            
            # Step 6: Return result
            if is_match:
                logger.info(f"User verified: {user_id} (similarity={similarity:.4f})")
            else:
                logger.warning(f"Verification failed: {user_id} (similarity={similarity:.4f})")
            
            return VerificationResult(
                success=True,
                verified=is_match,
                similarity=similarity,
                user_id=user_id
            )
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return VerificationResult(
                success=False,
                error_message=f"Verification failed: {e}"
            )
        
        finally:
            # Step 7: Clear sensitive data from memory
            self._clear_sensitive_data(live_embedding, stored_embedding, face_image)
    
    def _clear_sensitive_data(self, *arrays) -> None:
        """
        Securely clear sensitive numpy arrays from memory.
        
        Overwrites with zeros before deletion.
        """
        for arr in arrays:
            if arr is not None:
                try:
                    if isinstance(arr, np.ndarray):
                        arr.fill(0)
                    del arr
                except Exception:
                    pass
        
        gc.collect()
    
    def is_user_enrolled(self, user_id: str) -> bool:
        """
        Check if user has enrolled face template.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if user has stored embedding
        """
        return self._database.has_embedding(user_id)
    
    def delete_enrollment(self, user_id: str) -> bool:
        """
        Delete user's biometric enrollment.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if deletion successful
        """
        if self._database.delete_embedding(user_id):
            logger.info(f"Enrollment deleted: {user_id}")
            return True
        return False
    
    def shutdown(self) -> None:
        """
        Shutdown all subsystems and release resources.
        """
        logger.info("Shutting down BiometricClient...")
        
        try:
            if self._camera:
                self._camera.release()
        except Exception as e:
            logger.warning(f"Camera release error: {e}")
        
        try:
            if self._authenticator:
                self._authenticator.release()
        except Exception as e:
            logger.warning(f"Authenticator release error: {e}")
        
        try:
            if self._database:
                self._database.close()
        except Exception as e:
            logger.warning(f"Database close error: {e}")
        
        self._initialized = False
        gc.collect()
        
        logger.info("BiometricClient shutdown complete")
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()
        return False


# ============================================================================
# Convenience Functions (for integration with main TRIsecure system)
# ============================================================================

def enroll_user(user_id: str, client: BiometricClient) -> EnrollmentResult:
    """
    Convenience function to enroll user.
    
    Args:
        user_id: User identifier from NFC
        client: Initialized BiometricClient
        
    Returns:
        EnrollmentResult
    """
    return client.enroll_user(user_id)


def verify_user(user_id: str, client: BiometricClient) -> VerificationResult:
    """
    Convenience function to verify user.
    
    Args:
        user_id: User identifier from NFC
        client: Initialized BiometricClient
        
    Returns:
        VerificationResult
    """
    return client.verify_user(user_id)


def create_biometric_client(
    camera_device: int = 0,
    threshold: float = 0.55,
    db_path: str = "biometrics.db",
    master_key: str = None
) -> BiometricClient:
    """
    Factory function to create complete BiometricClient.
    
    Creates and configures all required components.
    
    Args:
        camera_device: Camera device index
        threshold: Similarity threshold (0.5-0.6 recommended)
        db_path: Path to SQLite database
        master_key: Master encryption key (uses env var if not provided)
        
    Returns:
        Configured BiometricClient (not yet initialized)
        
    Usage:
        client = create_biometric_client(threshold=0.55)
        client.initialize()
        
        result = client.verify_user("user123")
        
        client.shutdown()
    """
    from hardware.camera import FaceCamera, FaceAuthenticator
    from backend.crypto import EmbeddingEncryptor
    from backend.db import BiometricDatabase
    
    # Create components
    camera = FaceCamera(device=camera_device)
    authenticator = FaceAuthenticator(threshold=threshold)
    encryptor = EmbeddingEncryptor(master_key=master_key)
    database = BiometricDatabase(db_path=db_path)
    
    # Create client
    return BiometricClient(
        camera=camera,
        authenticator=authenticator,
        encryptor=encryptor,
        database=database,
        threshold=threshold
    )


# ============================================================================
# Integration Example (NFC → Face → Vote flow)
# ============================================================================

def biometric_authentication_flow(
    nfc_user_id: str,
    client: BiometricClient,
    on_verified: callable = None,
    on_failed: callable = None
) -> bool:
    """
    Complete biometric authentication flow.
    
    This is the main integration point for the voting system.
    
    Flow:
        NFC tap (user_id received)
        ↓
        Check if enrolled → if not, enroll first
        ↓
        Capture live face
        ↓
        Verify against stored template
        ↓
        If verified → call on_verified callback
        If failed → call on_failed callback
    
    Args:
        nfc_user_id: User ID from NFC card
        client: Initialized BiometricClient
        on_verified: Callback when verification succeeds (receives user_id)
        on_failed: Callback when verification fails (receives user_id, error)
        
    Returns:
        True if user is verified
    """
    logger.info(f"Starting biometric authentication: {nfc_user_id}")
    
    # Check enrollment status
    if not client.is_user_enrolled(nfc_user_id):
        logger.warning(f"User not enrolled: {nfc_user_id}")
        if on_failed:
            on_failed(nfc_user_id, "User not enrolled")
        return False
    
    # Verify user
    result = client.verify_user(nfc_user_id)
    
    if not result.success:
        logger.error(f"Verification error: {result.error_message}")
        if on_failed:
            on_failed(nfc_user_id, result.error_message)
        return False
    
    if result.verified:
        logger.info(f"User verified successfully: {nfc_user_id}")
        if on_verified:
            on_verified(nfc_user_id)
        return True
    else:
        logger.warning(f"Face mismatch: {nfc_user_id} (similarity={result.similarity:.4f})")
        if on_failed:
            on_failed(nfc_user_id, f"Face mismatch (similarity={result.similarity:.4f})")
        return False
