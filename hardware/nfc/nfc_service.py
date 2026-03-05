"""
NFC Card Reader/Writer Service (SPI).

Abstracts NFC hardware communication for Raspberry Pi PN532 module over SPI.
Falls back to simulation mode when hardware libraries are unavailable
(e.g. development on Windows/Mac laptops).

Capabilities:
- Read NFC card UIDs (blocking — waits until card is tapped)
- Write encrypted voter UUID to NTAG2xx / MIFARE Ultralight tags
- Read encrypted voter UUID from tags
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lightweight XOR-based encryption for NFC payloads ──────────────────────
# We derive a 16-byte key from a shared secret via SHA-256 and XOR
# the plaintext.  This is intentionally simple so it works on the
# constrained 144-byte NTAG213 user memory and is easy to audit.
# For production, replace with AES-128 (cryptography.fernet).

_NFC_SECRET = b"TRIsecure-NFC-2026"          # change per deployment

def _derive_key(secret: bytes, length: int = 16) -> bytes:
    return hashlib.sha256(secret).digest()[:length]

def _xor_crypt(data: bytes, key: bytes) -> bytes:
    """Symmetric XOR encryption/decryption."""
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


@dataclass
class NFCReadResult:
    """Result of NFC card read operation."""
    success: bool
    uid: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class NFCWriteResult:
    """Result of NFC card write operation."""
    success: bool
    error_message: Optional[str] = None


class NFCService:
    """
    NFC card reader/writer abstraction for PN532 NFC module over SPI.

    Hardware:
    - Device: PN532 NFC Reader (SPI)
    - Bus: SPI0 (SCK, MOSI, MISO)
    - CS: configurable (default D8 / CE0)
    - RESET: configurable (default D25)

    Responsibilities:
    - Initialize PN532 device
    - Read NFC card UIDs (true blocking — polls until tap)
    - Write encrypted voter UUID to NTAG2xx user memory
    - Read encrypted voter UUID back from tag
    - Handle SPI communication errors gracefully

    Simulation mode:
    - Activates automatically when Adafruit PN532 libraries are not installed
    - Returns a random hex UID so the rest of the pipeline can still be tested
    """

    # NTAG2xx user-memory starts at page 4 (pages 0-3 are reserved).
    _USER_PAGE_START = 4
    # We write 36 bytes = 9 pages (UUID is 36 chars as hex-encoded string).
    _PAYLOAD_PAGES = 9

    def __init__(
        self,
        spi_cs_pin: str = "D8",
        spi_reset_pin: str = "D25",
        spi_baudrate: int = 1_000_000,
        timeout: float = 5.0,
        poll_interval: float = 0.3,
    ):
        self.spi_cs_pin = spi_cs_pin
        self.spi_reset_pin = spi_reset_pin
        self.spi_baudrate = spi_baudrate
        self.timeout = timeout
        self.poll_interval = poll_interval

        self._device = None
        self._initialized = False
        self._key = _derive_key(_NFC_SECRET)

        logger.info(
            f"NFCService (SPI) created (CS={spi_cs_pin}, RESET={spi_reset_pin}, "
            f"baudrate={spi_baudrate})"
        )

    # ── Initialization ────────────────────────────────────────────────────────

    def initialize(self) -> bool:
        """Initialize NFC device connection over SPI. Returns True if successful."""
        try:
            import board
            import busio
            from digitalio import DigitalInOut
            from adafruit_pn532.spi import PN532_SPI

            cs_pin = DigitalInOut(getattr(board, self.spi_cs_pin))
            reset_pin = DigitalInOut(getattr(board, self.spi_reset_pin))

            spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
            while not spi.try_lock():
                pass
            try:
                spi.configure(baudrate=self.spi_baudrate)
            finally:
                spi.unlock()

            self._device = PN532_SPI(spi, cs_pin, reset=reset_pin, debug=False)
            ic, ver, rev, support = self._device.firmware_version
            logger.info(f"Found PN532 with firmware version: {ver}.{rev}")
            self._device.SAM_configuration()

            self._initialized = True
            logger.info("NFC device (SPI) initialized successfully")
            return True

        except ImportError:
            logger.warning(
                "Adafruit PN532 libraries not installed — running in simulation mode."
            )
            self._initialized = False
            return False

        except Exception as e:
            logger.error(f"Failed to initialize NFC device (SPI): {e}")
            logger.warning("NFC hardware unavailable — system will work in demo mode.")
            self._initialized = False
            return False

    # ── Read UID ──────────────────────────────────────────────────────────────

    def read_card(self) -> NFCReadResult:
        """Single-shot NFC card UID read.  Returns simulation UID when off-hardware."""
        if not self._initialized:
            logger.warning("NFC device not initialized. Returning simulated UID.")
            return NFCReadResult(success=True, uid=secrets.token_hex(7).upper())

        try:
            uid = self._device.read_passive_target(timeout=self.timeout)
            if uid is None:
                return NFCReadResult(success=False, error_message="No NFC card detected")

            uid_str = "".join(f"{b:02X}" for b in uid)
            logger.info(f"NFC card read: {uid_str}")
            return NFCReadResult(success=True, uid=uid_str)

        except OSError as e:
            logger.error(f"SPI communication error: {e}")
            return NFCReadResult(success=False, error_message=f"SPI error: {e}")
        except Exception as e:
            logger.error(f"NFC read error: {e}")
            return NFCReadResult(success=False, error_message=f"NFC read failed: {e}")

    def read_card_blocking(self, max_wait: float = 30.0) -> str:
        """
        Blocking read — polls until an NFC card is tapped.

        Args:
            max_wait: Maximum seconds to wait before raising RuntimeError.

        Returns:
            NFC UID hex string.

        Raises:
            RuntimeError: If no card tapped within max_wait or hardware error.
        """
        logger.info("Waiting for NFC card...")

        # Simulation mode — return immediately
        if not self._initialized:
            logger.warning("NFC device not initialized. Returning simulated UID.")
            return secrets.token_hex(7).upper()

        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            try:
                uid = self._device.read_passive_target(timeout=self.timeout)
                if uid is not None:
                    uid_str = "".join(f"{b:02X}" for b in uid)
                    logger.info(f"NFC card detected: {uid_str}")
                    return uid_str
            except OSError as e:
                logger.warning(f"SPI glitch during wait: {e}")
            except Exception as e:
                logger.error(f"NFC error during wait: {e}")
                raise RuntimeError(f"NFC read failed: {e}")

            time.sleep(self.poll_interval)

        raise RuntimeError(f"No NFC card detected within {max_wait}s")

    # ── Write encrypted voter UUID to tag ─────────────────────────────────────

    def write_voter_id(self, voter_uuid: str) -> NFCWriteResult:
        """
        Write an encrypted voter UUID to the currently-presented NTAG2xx tag.

        The voter UUID (36 chars, e.g. 'xxxxxxxx-xxxx-…') is encrypted with
        a shared key and written to user-memory pages 4-12.

        The card must already be on the reader (call after read_card).

        Args:
            voter_uuid: The voter's UUID string (36 characters).

        Returns:
            NFCWriteResult with success status.
        """
        if not self._initialized:
            logger.info(f"[Simulation] Would write voter ID: {voter_uuid[:8]}…")
            return NFCWriteResult(success=True)

        try:
            # Encode and encrypt
            plaintext = voter_uuid.encode("utf-8")            # 36 bytes
            ciphertext = _xor_crypt(plaintext, self._key)

            # Pad to multiple of 4 (NTAG2xx page = 4 bytes)
            padded = ciphertext + b'\x00' * (4 - len(ciphertext) % 4) \
                     if len(ciphertext) % 4 != 0 else ciphertext

            # Write page by page
            for i in range(0, len(padded), 4):
                page = self._USER_PAGE_START + (i // 4)
                data = padded[i:i+4]
                self._device.ntag2xx_write_block(page, data)
                logger.debug(f"Wrote page {page}: {data.hex()}")

            logger.info(f"Encrypted voter ID written to NFC tag ({len(padded)} bytes)")
            return NFCWriteResult(success=True)

        except Exception as e:
            logger.error(f"NFC write failed: {e}")
            return NFCWriteResult(success=False, error_message=str(e))

    def read_voter_id(self) -> Optional[str]:
        """
        Read and decrypt the voter UUID from the currently-presented NTAG2xx tag.

        The card must already be on the reader.

        Returns:
            Decrypted voter UUID string or None if read fails / no data.
        """
        if not self._initialized:
            logger.info("[Simulation] No real tag to read voter ID from.")
            return None

        try:
            raw = bytearray()
            for page in range(self._USER_PAGE_START,
                              self._USER_PAGE_START + self._PAYLOAD_PAGES):
                block = self._device.ntag2xx_read_block(page)
                if block is None:
                    logger.warning(f"Failed to read page {page}")
                    return None
                raw.extend(block)

            # Trim to 36 bytes (UUID length) and decrypt
            ciphertext = bytes(raw[:36])
            plaintext = _xor_crypt(ciphertext, self._key)
            voter_uuid = plaintext.decode("utf-8", errors="replace")

            # Basic UUID format validation (8-4-4-4-12)
            if len(voter_uuid) == 36 and voter_uuid.count("-") == 4:
                logger.info(f"Voter ID read from NFC: {voter_uuid[:8]}…")
                return voter_uuid
            else:
                logger.debug("NFC tag does not contain a valid voter UUID")
                return None

        except Exception as e:
            logger.error(f"NFC read voter ID failed: {e}")
            return None

    # ── Utilities ─────────────────────────────────────────────────────────────

    def is_initialized(self) -> bool:
        """Check if NFC hardware is properly initialized."""
        return self._initialized

    def close(self) -> None:
        """Close NFC device connection."""
        if self._device:
            try:
                self._device = None
                logger.info("NFC device closed")
            except Exception as e:
                logger.error(f"Error closing NFC device: {e}")

