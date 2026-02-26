"""
Biometric Client — orchestration layer.

Connects hardware (camera + face authenticator), encryption and the
biometric database into a single enroll/verify API.

Pipeline
--------
Enrollment:
    NFC tap → capture face → extract embedding → encrypt (AES-256-GCM) → store in DB

Verification:
    NFC tap → capture face → extract embedding →
    retrieve encrypted template → decrypt → cosine compare → approve / reject

Usage::

    from backend.client import create_biometric_client

    client = create_biometric_client(threshold=0.55)
    client.initialize()

    client.enroll_user("user_nfc_uid")
    result = client.verify_user("user_nfc_uid")
    if result.verified:
        print("Access granted")

    client.shutdown()
"""

import gc
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class EnrollmentResult:
    success: bool
    user_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class VerificationResult:
    success: bool
    verified: bool = False
    similarity: float = 0.0
    user_id: Optional[str] = None
    error_message: Optional[str] = None


# ── Main client ───────────────────────────────────────────────────────────────

class BiometricClient:
    """
    Orchestration-only biometric client.

    Contains NO ML code, NO database queries, NO crypto operations —
    those are all delegated to the injected components.
    """

    def __init__(self, camera, authenticator, encryptor, database,
                 threshold: float = 0.55):
        self._camera        = camera
        self._authenticator = authenticator
        self._encryptor     = encryptor
        self._database      = database
        self._threshold     = threshold
        self._initialized   = False
        logger.debug(f"BiometricClient created (threshold={threshold})")

    def initialize(self) -> bool:
        """Initialize all subsystems. Raises RuntimeError on failure."""
        try:
            logger.info("Initializing camera...")
            if not self._camera.initialize():
                raise RuntimeError("Camera initialization failed")

            logger.info("Initializing face authenticator...")
            if not self._authenticator.initialize():
                raise RuntimeError("Authenticator initialization failed")

            logger.info("Initializing biometric database...")
            if not self._database.initialize():
                raise RuntimeError("Database initialization failed")

            self._initialized = True
            logger.info("BiometricClient ready")
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            raise RuntimeError(f"BiometricClient initialization failed: {e}")

    # ── Enroll ────────────────────────────────────────────────────────────────

    def enroll_user(self, user_id: str) -> EnrollmentResult:
        """
        Enroll a user.  Steps:
        1. Capture face
        2. Extract embedding
        3. Encrypt
        4. Store in DB
        5. Clear sensitive data
        """
        if not self._initialized:
            return EnrollmentResult(success=False, error_message="Not initialized")
        if not user_id:
            return EnrollmentResult(success=False, error_message="user_id is empty")

        logger.info(f"Enrolling user: {user_id}")
        embedding = face_image = None
        try:
            detection = self._camera.capture_and_detect()
            if not detection.success or detection.face_image is None:
                return EnrollmentResult(
                    success=False,
                    error_message=f"Face capture failed: {detection.error_message}"
                )
            face_image = detection.face_image

            emb_result = self._authenticator.extract_embedding(face_image)
            if not emb_result.success:
                return EnrollmentResult(
                    success=False,
                    error_message=f"Embedding failed: {emb_result.error_message}"
                )
            embedding = emb_result.embedding

            enc_result = self._encryptor.encrypt(embedding)
            if not enc_result.success:
                return EnrollmentResult(
                    success=False,
                    error_message=f"Encryption failed: {enc_result.error_message}"
                )

            stored = self._database.store_embedding(
                user_id=user_id,
                encrypted_embedding=enc_result.ciphertext,
                salt=enc_result.salt,
                iv=enc_result.iv,
            )
            if not stored:
                return EnrollmentResult(success=False,
                                        error_message="DB store failed")

            logger.info(f"User enrolled: {user_id}")
            return EnrollmentResult(success=True, user_id=user_id)

        except Exception as e:
            logger.error(f"Enrollment error: {e}")
            return EnrollmentResult(success=False, error_message=str(e))
        finally:
            self._clear(embedding, face_image)

    # ── Verify ────────────────────────────────────────────────────────────────

    def verify_user(self, user_id: str) -> VerificationResult:
        """
        Verify a user.  Steps:
        1. Check enrollment exists
        2. Capture live face
        3. Extract live embedding
        4. Retrieve + decrypt stored template
        5. Cosine compare
        6. Clear sensitive data
        """
        if not self._initialized:
            return VerificationResult(success=False, error_message="Not initialized")
        if not user_id:
            return VerificationResult(success=False, error_message="user_id is empty")

        logger.info(f"Verifying user: {user_id}")
        live_emb = stored_emb = face_image = None
        try:
            if not self._database.has_embedding(user_id):
                return VerificationResult(
                    success=False,
                    error_message=f"No enrollment found for: {user_id}"
                )

            detection = self._camera.capture_and_detect()
            if not detection.success or detection.face_image is None:
                return VerificationResult(
                    success=False,
                    error_message=f"Face capture failed: {detection.error_message}"
                )
            face_image = detection.face_image

            emb_result = self._authenticator.extract_embedding(face_image)
            if not emb_result.success:
                return VerificationResult(
                    success=False,
                    error_message=f"Embedding failed: {emb_result.error_message}"
                )
            live_emb = emb_result.embedding

            record = self._database.get_embedding(user_id)
            if not record:
                return VerificationResult(success=False,
                                          error_message="Failed to retrieve template")

            dec_result = self._encryptor.decrypt(
                ciphertext=record.encrypted_embedding,
                salt=record.salt,
                iv=record.iv,
            )
            if not dec_result.success:
                return VerificationResult(
                    success=False,
                    error_message=f"Decryption failed: {dec_result.error_message}"
                )
            stored_emb = dec_result.embedding

            is_match, similarity = self._authenticator.compare_embeddings(
                live_emb, stored_emb, threshold=self._threshold
            )

            if is_match:
                logger.info(f"Verified: {user_id} (sim={similarity:.4f})")
            else:
                logger.warning(f"Mismatch: {user_id} (sim={similarity:.4f})")

            return VerificationResult(
                success=True, verified=is_match,
                similarity=similarity, user_id=user_id
            )

        except Exception as e:
            logger.error(f"Verification error: {e}")
            return VerificationResult(success=False, error_message=str(e))
        finally:
            self._clear(live_emb, stored_emb, face_image)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear(self, *arrays) -> None:
        """Overwrite and release sensitive numpy arrays."""
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
        return self._database.has_embedding(user_id)

    def delete_enrollment(self, user_id: str) -> bool:
        if self._database.delete_embedding(user_id):
            logger.info(f"Enrollment deleted: {user_id}")
            return True
        return False

    def shutdown(self) -> None:
        logger.info("Shutting down BiometricClient...")
        for name, obj in [("camera", self._camera),
                           ("authenticator", self._authenticator),
                           ("database", self._database)]:
            if obj:
                try:
                    getattr(obj, "release", None) or getattr(obj, "close")
                    if hasattr(obj, "release"):
                        obj.release()
                    elif hasattr(obj, "close"):
                        obj.close()
                except Exception as e:
                    logger.warning(f"{name} shutdown error: {e}")
        self._initialized = False
        gc.collect()
        logger.info("BiometricClient shutdown complete")

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *_):
        self.shutdown()
        return False


# ── Factory ───────────────────────────────────────────────────────────────────

def create_biometric_client(
    camera_device: int = 0,
    threshold: float = 0.55,
    db_path: str = "data/biometrics.db",
    master_key: str = None,
) -> BiometricClient:
    """
    Factory — create a ready-to-initialize BiometricClient with all components wired.

    Args:
        camera_device: Webcam index (0 = built-in laptop cam)
        threshold:     Cosine similarity threshold (0.5–0.6 recommended)
        db_path:       Path to SQLite biometric database
        master_key:    AES master key (reads TRISECURE_MASTER_KEY env var if None)

    Returns:
        BiometricClient  (call .initialize() before use)
    """
    from hardware.camera.face_auth import FaceCamera, FaceAuthenticator
    from backend.crypto import EmbeddingEncryptor
    from backend.db import BiometricDatabase

    return BiometricClient(
        camera=FaceCamera(device=camera_device),
        authenticator=FaceAuthenticator(threshold=threshold),
        encryptor=EmbeddingEncryptor(master_key=master_key),
        database=BiometricDatabase(db_path=db_path),
        threshold=threshold,
    )
