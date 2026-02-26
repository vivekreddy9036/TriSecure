"""
Backend layer for TRIsecure.

Modules
-------
crypto/     AES-256-GCM encryption for face embedding vectors.
db/         SQLite storage for encrypted biometric templates.
client.py   BiometricClient — orchestrates camera + authenticator +
            encryptor + database into a simple enroll/verify API.
"""

from backend.client import BiometricClient, EnrollmentResult, VerificationResult, create_biometric_client

__all__ = [
    "BiometricClient",
    "EnrollmentResult",
    "VerificationResult",
    "create_biometric_client",
]
