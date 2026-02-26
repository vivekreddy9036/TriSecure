"""
Client layer for TRIsecure biometric authentication.

Provides:
- BiometricClient: Orchestration-only client (no ML code)
"""

from client.main import BiometricClient, EnrollmentResult, VerificationResult

__all__ = ["BiometricClient", "EnrollmentResult", "VerificationResult"]
