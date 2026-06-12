"""
Post-quantum cryptography primitives.

HybridKEM:  Kyber-768 (FIPS 203/ML-KEM-768) + X25519, hybrid shared secret via HKDF-SHA256.
            Falls back to X25519-only when liboqs is unavailable.

DilithiumSigner: Dilithium-3 (FIPS 204/ML-DSA-65) digital signatures.
                 Falls back to Ed25519 (PyNaCl) when liboqs is unavailable.
"""

import logging
from typing import Tuple

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

logger = logging.getLogger(__name__)

_OQS_AVAILABLE = False
try:
    import oqs  # type: ignore
    _OQS_AVAILABLE = True
except ImportError:
    logger.warning("liboqs-python not found — PQC falls back to classical primitives")


_INFO = b"trisecure-hybrid-v1"
_KEY_LEN = 32


def _hkdf_extract_expand(ikm: bytes, info: bytes = _INFO, length: int = _KEY_LEN) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=info,
    ).derive(ikm)


class HybridKEM:
    """
    Hybrid Key Encapsulation Mechanism.

    When liboqs is available: Kyber-768 + X25519.
    Fallback: X25519 only (documented in paper as baseline).
    Shared secret = HKDF-SHA256(x25519_ss || kyber_ss, info="trisecure-hybrid-v1")
    """

    def __init__(self) -> None:
        self._pqc = _OQS_AVAILABLE

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Return (public_key, secret_key) as concatenated raw bytes."""
        x25519_sk = X25519PrivateKey.generate()
        x25519_pk = x25519_sk.public_key().public_bytes_raw()
        x25519_sk_bytes = x25519_sk.private_bytes_raw()

        if self._pqc:
            kem = oqs.KeyEncapsulation("Kyber768")
            kyber_pk = kem.generate_keypair()
            kyber_sk = kem.export_secret_key()
            pk = x25519_pk + kyber_pk
            sk = x25519_sk_bytes + kyber_sk
        else:
            pk = x25519_pk
            sk = x25519_sk_bytes

        return pk, sk

    def encapsulate(self, public_key: bytes) -> Tuple[bytes, bytes]:
        """Return (ciphertext, shared_secret)."""
        x25519_pk_bytes = public_key[:32]
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        peer_pub = X25519PublicKey.from_public_bytes(x25519_pk_bytes)
        eph_sk = X25519PrivateKey.generate()
        x25519_ss = eph_sk.exchange(peer_pub)
        eph_pk = eph_sk.public_key().public_bytes_raw()

        if self._pqc and len(public_key) > 32:
            kyber_pk = public_key[32:]
            with oqs.KeyEncapsulation("Kyber768") as kem:
                kyber_ct, kyber_ss = kem.encap_secret(kyber_pk)
            ikm = x25519_ss + kyber_ss
            ct = eph_pk + kyber_ct
        else:
            ikm = x25519_ss
            ct = eph_pk

        shared_secret = _hkdf_extract_expand(ikm)
        return ct, shared_secret

    def decapsulate(self, secret_key: bytes, ciphertext: bytes) -> bytes:
        """Return shared_secret from ciphertext + secret_key."""
        x25519_sk_bytes = secret_key[:32]
        eph_pk_bytes = ciphertext[:32]

        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        x25519_sk = X25519PrivateKey.from_private_bytes(x25519_sk_bytes)
        eph_pub = X25519PublicKey.from_public_bytes(eph_pk_bytes)
        x25519_ss = x25519_sk.exchange(eph_pub)

        if self._pqc and len(secret_key) > 32 and len(ciphertext) > 32:
            kyber_sk = secret_key[32:]
            kyber_ct = ciphertext[32:]
            with oqs.KeyEncapsulation("Kyber768", secret_key=kyber_sk) as kem:
                kyber_ss = kem.decap_secret(kyber_ct)
            ikm = x25519_ss + kyber_ss
        else:
            ikm = x25519_ss

        return _hkdf_extract_expand(ikm)

    @staticmethod
    def key_sizes() -> dict:
        if _OQS_AVAILABLE:
            return {
                "public_key": 32 + 1184,   # X25519 + Kyber768
                "secret_key": 32 + 2400,   # X25519 + Kyber768
                "ciphertext": 32 + 1088,   # eph X25519 pk + Kyber768 ct
                "shared_secret": 32,
                "backend": "X25519+Kyber768",
            }
        return {
            "public_key": 32,
            "secret_key": 32,
            "ciphertext": 32,
            "shared_secret": 32,
            "backend": "X25519-only (liboqs unavailable)",
        }


class DilithiumSigner:
    """
    Digital signatures.

    When liboqs available: Dilithium-3 (~3293-byte signatures, FIPS 204/ML-DSA-65).
    Fallback: Ed25519 via PyNaCl (64-byte signatures).
    """

    def __init__(self) -> None:
        self._pqc = _OQS_AVAILABLE

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Return (public_key, secret_key)."""
        if self._pqc:
            signer = oqs.Signature("Dilithium3")
            pk = signer.generate_keypair()
            sk = signer.export_secret_key()
            return pk, sk
        else:
            from nacl.signing import SigningKey
            sk_obj = SigningKey.generate()
            return bytes(sk_obj.verify_key), bytes(sk_obj)

    def sign(self, message: bytes, secret_key: bytes) -> bytes:
        if self._pqc:
            with oqs.Signature("Dilithium3", secret_key=secret_key) as signer:
                return signer.sign(message)
        else:
            from nacl.signing import SigningKey
            sk_obj = SigningKey(secret_key)
            signed = sk_obj.sign(message)
            return signed.signature

    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        try:
            if self._pqc:
                with oqs.Signature("Dilithium3") as verifier:
                    return verifier.verify(message, signature, public_key)
            else:
                from nacl.signing import VerifyKey
                vk = VerifyKey(public_key)
                vk.verify(message, signature)
                return True
        except Exception:
            return False

    @staticmethod
    def algorithm_info() -> dict:
        if _OQS_AVAILABLE:
            return {"algorithm": "Dilithium3", "sig_size_bytes": 3293, "pk_size_bytes": 1952}
        return {"algorithm": "Ed25519 (fallback)", "sig_size_bytes": 64, "pk_size_bytes": 32}
