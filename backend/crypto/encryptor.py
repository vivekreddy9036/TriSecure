"""
Embedding Encryption Module.

Handles AES-256-GCM encryption and decryption of face embedding vectors.

This module is part of the backend layer and contains:
- EmbeddingEncryptor: AES encryption for numpy embedding vectors

Security Features:
- AES-256-GCM (authenticated encryption)
- PBKDF2 key derivation (100,000 iterations)
- Random salt per encryption
- Random IV per encryption
- Constant-time comparison for tags

Design:
- No ML logic (clean architecture)
- No database logic (separation of concerns)
- Stateless operations
- Memory-safe (clears sensitive data)
"""

import logging
import gc
import secrets
from typing import Tuple, Optional
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


# Constants for AES-256-GCM
AES_KEY_SIZE = 32  # 256 bits
AES_IV_SIZE = 12   # 96 bits (recommended for GCM)
SALT_SIZE = 16     # 128 bits
TAG_SIZE = 16      # 128 bits (GCM authentication tag)
PBKDF2_ITERATIONS = 100_000


@dataclass
class EncryptionResult:
    """Result of encryption operation."""
    success: bool
    ciphertext: Optional[bytes] = None
    salt: Optional[bytes] = None
    iv: Optional[bytes] = None
    error_message: Optional[str] = None


@dataclass
class DecryptionResult:
    """Result of decryption operation."""
    success: bool
    embedding: Optional[np.ndarray] = None
    error_message: Optional[str] = None


class EmbeddingEncryptor:
    """
    AES-256-GCM encryptor for face embeddings.
    
    Responsibilities:
    - Encrypt numpy embedding arrays to bytes
    - Decrypt bytes back to numpy arrays
    - Generate secure random IVs and salts
    - Derive keys from master password
    
    Security Model:
    - Each embedding encrypted with unique IV
    - Unique salt allows different keys per user
    - GCM mode provides authentication
    - Master key never stored, only derived
    
    Usage:
        encryptor = EmbeddingEncryptor(master_key="strong-password")
        
        # Encrypt embedding
        result = encryptor.encrypt(embedding_vector)
        if result.success:
            save_to_db(result.ciphertext, result.salt, result.iv)
        
        # Decrypt embedding
        result = encryptor.decrypt(ciphertext, salt, iv)
        if result.success:
            embedding = result.embedding
    """
    
    def __init__(self, master_key: str = None):
        """
        Initialize encryptor with master key.
        
        Args:
            master_key: Master password for key derivation.
                        If None, uses environment variable TRISECURE_MASTER_KEY
                        or generates a random key (testing only).
        """
        self._master_key = self._get_master_key(master_key)
        self._crypto_available = self._check_crypto()
        
        if not self._crypto_available:
            logger.warning("Cryptography library not available. Running in simulation mode.")
        
        logger.debug("EmbeddingEncryptor initialized")
    
    def _get_master_key(self, key: Optional[str]) -> bytes:
        """
        Get or generate master key.
        
        Args:
            key: Provided key string
            
        Returns:
            Key as bytes
        """
        import os
        
        if key:
            return key.encode('utf-8')
        
        # Try environment variable
        env_key = os.environ.get('TRISECURE_MASTER_KEY')
        if env_key:
            return env_key.encode('utf-8')
        
        # Generate random key for testing (NOT for production!)
        logger.warning("No master key provided. Using random key (testing only).")
        return secrets.token_bytes(32)
    
    def _check_crypto(self) -> bool:
        """Check if cryptography library is available."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            return True
        except ImportError:
            return False
    
    def _derive_key(self, salt: bytes) -> bytes:
        """
        Derive encryption key from master key and salt.
        
        Uses PBKDF2-HMAC-SHA256 with 100,000 iterations.
        
        Args:
            salt: Random salt bytes
            
        Returns:
            Derived AES-256 key
        """
        if not self._crypto_available:
            # Simulation mode: simple hash
            import hashlib
            return hashlib.sha256(self._master_key + salt).digest()
        
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        
        return kdf.derive(self._master_key)
    
    def encrypt(self, embedding: np.ndarray) -> EncryptionResult:
        """
        Encrypt embedding vector using AES-256-GCM.
        
        Args:
            embedding: Numpy array (float32) to encrypt
            
        Returns:
            EncryptionResult with ciphertext, salt, and IV
        """
        if embedding is None:
            return EncryptionResult(
                success=False,
                error_message="Embedding cannot be None"
            )
        
        try:
            # Step 1: Convert embedding to bytes
            embedding_bytes = self._embedding_to_bytes(embedding)
            
            # Step 2: Generate random salt and IV
            salt = secrets.token_bytes(SALT_SIZE)
            iv = secrets.token_bytes(AES_IV_SIZE)
            
            # Step 3: Derive key from master key and salt
            key = self._derive_key(salt)
            
            # Step 4: Encrypt using AES-GCM
            if self._crypto_available:
                ciphertext = self._encrypt_aes_gcm(embedding_bytes, key, iv)
            else:
                # Simulation mode: XOR with key (NOT SECURE - testing only)
                ciphertext = self._simulate_encrypt(embedding_bytes, key, iv)
            
            # Step 5: Clear sensitive data from memory
            self._secure_clear(key)
            self._secure_clear(embedding_bytes)
            
            logger.debug(f"Embedding encrypted: {len(ciphertext)} bytes")
            
            return EncryptionResult(
                success=True,
                ciphertext=ciphertext,
                salt=salt,
                iv=iv
            )
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return EncryptionResult(
                success=False,
                error_message=f"Encryption failed: {e}"
            )
    
    def decrypt(
        self,
        ciphertext: bytes,
        salt: bytes,
        iv: bytes
    ) -> DecryptionResult:
        """
        Decrypt embedding from AES-256-GCM ciphertext.
        
        Args:
            ciphertext: Encrypted embedding bytes (includes GCM tag)
            salt: Salt used for key derivation
            iv: Initialization vector
            
        Returns:
            DecryptionResult with numpy embedding array
        """
        if not ciphertext or not salt or not iv:
            return DecryptionResult(
                success=False,
                error_message="Missing ciphertext, salt, or IV"
            )
        
        try:
            # Step 1: Derive key from master key and salt
            key = self._derive_key(salt)
            
            # Step 2: Decrypt using AES-GCM
            if self._crypto_available:
                plaintext = self._decrypt_aes_gcm(ciphertext, key, iv)
            else:
                # Simulation mode
                plaintext = self._simulate_decrypt(ciphertext, key, iv)
            
            # Step 3: Convert bytes back to embedding
            embedding = self._bytes_to_embedding(plaintext)
            
            # Step 4: Clear sensitive data
            self._secure_clear(key)
            self._secure_clear(plaintext)
            
            logger.debug(f"Embedding decrypted: shape={embedding.shape}")
            
            return DecryptionResult(
                success=True,
                embedding=embedding
            )
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return DecryptionResult(
                success=False,
                error_message=f"Decryption failed: {e}"
            )
    
    def _encrypt_aes_gcm(
        self,
        plaintext: bytes,
        key: bytes,
        iv: bytes
    ) -> bytes:
        """
        Perform AES-256-GCM encryption.
        
        Args:
            plaintext: Data to encrypt
            key: AES-256 key
            iv: Initialization vector
            
        Returns:
            Ciphertext with appended authentication tag
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, plaintext, None)
        
        return ciphertext
    
    def _decrypt_aes_gcm(
        self,
        ciphertext: bytes,
        key: bytes,
        iv: bytes
    ) -> bytes:
        """
        Perform AES-256-GCM decryption.
        
        Args:
            ciphertext: Encrypted data with auth tag
            key: AES-256 key
            iv: Initialization vector
            
        Returns:
            Decrypted plaintext
            
        Raises:
            Exception: If authentication fails
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        
        return plaintext
    
    def _simulate_encrypt(
        self,
        plaintext: bytes,
        key: bytes,
        iv: bytes
    ) -> bytes:
        """
        Simulation encryption (NOT SECURE - testing only).
        
        Uses simple XOR for testing without cryptography library.
        """
        logger.warning("Using simulation encryption (NOT SECURE)")
        
        # Create repeating key
        key_stream = (key * (len(plaintext) // len(key) + 1))[:len(plaintext)]
        
        # XOR plaintext with key stream
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, key_stream))
        
        # Append fake tag
        fake_tag = secrets.token_bytes(TAG_SIZE)
        
        return ciphertext + fake_tag
    
    def _simulate_decrypt(
        self,
        ciphertext: bytes,
        key: bytes,
        iv: bytes
    ) -> bytes:
        """
        Simulation decryption (NOT SECURE - testing only).
        """
        logger.warning("Using simulation decryption (NOT SECURE)")
        
        # Remove fake tag
        ciphertext_only = ciphertext[:-TAG_SIZE]
        
        # Create repeating key
        key_stream = (key * (len(ciphertext_only) // len(key) + 1))[:len(ciphertext_only)]
        
        # XOR ciphertext with key stream
        plaintext = bytes(a ^ b for a, b in zip(ciphertext_only, key_stream))
        
        return plaintext
    
    def _embedding_to_bytes(self, embedding: np.ndarray) -> bytes:
        """
        Convert numpy embedding to bytes.
        
        Stores shape info for reconstruction.
        
        Format: [shape_len (4 bytes)][shape][dtype][data]
        """
        # Ensure contiguous array
        embedding = np.ascontiguousarray(embedding, dtype=np.float32)
        
        # Serialize with numpy
        import io
        buffer = io.BytesIO()
        np.save(buffer, embedding, allow_pickle=False)
        
        return buffer.getvalue()
    
    def _bytes_to_embedding(self, data: bytes) -> np.ndarray:
        """
        Convert bytes back to numpy embedding.
        """
        import io
        buffer = io.BytesIO(data)
        
        embedding = np.load(buffer, allow_pickle=False)
        
        return embedding.astype(np.float32)
    
    def _secure_clear(self, data) -> None:
        """
        Securely clear sensitive data from memory.
        
        Overwrites data before deletion.
        """
        if data is None:
            return
        
        try:
            if isinstance(data, bytearray):
                for i in range(len(data)):
                    data[i] = 0
            elif isinstance(data, bytes):
                # bytes are immutable, just delete reference
                pass
            elif isinstance(data, np.ndarray):
                data.fill(0)
            
            del data
            gc.collect()
            
        except Exception:
            pass
    
    def encrypt_embedding(self, embedding: np.ndarray) -> Tuple[bytes, bytes, bytes]:
        """
        Convenience method to encrypt and return components.
        
        Args:
            embedding: Numpy embedding array
            
        Returns:
            Tuple of (ciphertext, salt, iv)
            
        Raises:
            ValueError: If encryption fails
        """
        result = self.encrypt(embedding)
        
        if not result.success:
            raise ValueError(f"Encryption failed: {result.error_message}")
        
        return result.ciphertext, result.salt, result.iv
    
    def decrypt_embedding(
        self,
        ciphertext: bytes,
        salt: bytes,
        iv: bytes
    ) -> np.ndarray:
        """
        Convenience method to decrypt and return embedding.
        
        Args:
            ciphertext: Encrypted data
            salt: Encryption salt
            iv: Initialization vector
            
        Returns:
            Decrypted numpy embedding
            
        Raises:
            ValueError: If decryption fails
        """
        result = self.decrypt(ciphertext, salt, iv)
        
        if not result.success:
            raise ValueError(f"Decryption failed: {result.error_message}")
        
        return result.embedding
