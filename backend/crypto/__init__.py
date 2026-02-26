"""
Cryptography module for embedding encryption.

Provides:
- EmbeddingEncryptor: AES-256 encryption for face embeddings
"""

from backend.crypto.encryptor import EmbeddingEncryptor, EncryptionResult, DecryptionResult

__all__ = ["EmbeddingEncryptor", "EncryptionResult", "DecryptionResult"]
