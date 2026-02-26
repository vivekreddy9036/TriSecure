"""
Database module for biometric template storage.

Provides:
- BiometricDatabase: SQLite storage for encrypted face embeddings
"""

from backend.db.database import BiometricDatabase, BiometricRecord

__all__ = ["BiometricDatabase", "BiometricRecord"]
