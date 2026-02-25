"""
NFC Card Reader Service (SPI).

Abstracts NFC hardware communication for Raspberry Pi PN532 module over SPI.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class NFCReadResult:
    """Result of NFC card read operation."""
    success: bool
    uid: Optional[str] = None
    error_message: Optional[str] = None


class NFCService:
    """
    NFC card reader abstraction for PN532 NFC module over SPI.

    Hardware:
    - Device: PN532 NFC Reader (SPI)
    - Bus: SPI0 (SCK, MOSI, MISO)
    - CS: configurable (default D8 / CE0)
    - RESET: configurable (default D25)

    Responsibilities:
    - Initialize PN532 device
    - Read NFC card UIDs
    - Handle SPI communication errors gracefully
    - Provide clean API for authentication pipeline
    """

    def __init__(
        self,
        spi_cs_pin: str = "D8",
        spi_reset_pin: str = "D25",
        spi_baudrate: int = 1_000_000,
        timeout: float = 5.0,
    ):
        """
        Initialize NFC service (SPI).

        Args:
            spi_cs_pin: Board pin name for CS (e.g. "D8")
            spi_reset_pin: Board pin name for RESET (e.g. "D25")
            spi_baudrate: SPI clock in Hz
            timeout: Read timeout in seconds
        """
        self.spi_cs_pin = spi_cs_pin
        self.spi_reset_pin = spi_reset_pin
        self.spi_baudrate = spi_baudrate
        self.timeout = timeout

        self._device = None
        self._initialized = False

        logger.info(
            f"NFCService (SPI) initialized (CS={spi_cs_pin}, RESET={spi_reset_pin}, "
            f"baudrate={spi_baudrate})"
        )

    def initialize(self) -> bool:
        """
        Initialize NFC device connection over SPI.

        Returns:
            True if initialization successful
        """
        try:
            import board
            import busio
            from digitalio import DigitalInOut
            from adafruit_pn532.spi import PN532_SPI

            # Map string pin names like "D8" to board.D8
            cs_pin = DigitalInOut(getattr(board, self.spi_cs_pin))
            reset_pin = DigitalInOut(getattr(board, self.spi_reset_pin))

            # Setup SPI bus
            spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

            # Ensure SPI is configured (optional, but safe)
            while not spi.try_lock():
                pass
            try:
                spi.configure(baudrate=self.spi_baudrate)
            finally:
                spi.unlock()

            # Initialize PN532 over SPI
            self._device = PN532_SPI(spi, cs_pin, reset=reset_pin, debug=False)

            # Get firmware and configure
            ic, ver, rev, support = self._device.firmware_version
            logger.info(f"Found PN532 with firmware version: {ver}.{rev}")
            self._device.SAM_configuration()

            self._initialized = True
            logger.info("NFC device (SPI) initialized successfully")
            return True

        except ImportError:
            logger.warning(
                "NFC SPI libraries not installed (Adafruit PN532). "
                "Running in simulation mode."
            )
            self._initialized = False
            return False

        except Exception as e:
            logger.error(f"Failed to initialize NFC device (SPI): {e}")
            logger.warning("NFC hardware unavailable. System will work in demo mode.")
            self._initialized = False
            return False

    def read_card(self) -> NFCReadResult:
        """
        Read NFC card UID.

        Returns:
            NFCReadResult with UID or error message
        """
        if not self._initialized:
            logger.warning("NFC device not initialized. Returning demo UID.")
            # Return demo UID for development
            return NFCReadResult(
                success=True,
                uid="04ABC123D4E5F6"  # Demo UID
            )

        try:
            # Read card (blocking up to timeout seconds)
            uid = self._device.read_passive_target(timeout=self.timeout)

            if uid is None:
                logger.debug("No NFC card detected")
                return NFCReadResult(
                    success=False,
                    error_message="No NFC card detected"
                )

            # Convert UID bytes to hex string
            uid_str = ''.join(f"{b:02X}" for b in uid)
            logger.info(f"NFC card read successfully: {uid_str}")

            return NFCReadResult(
                success=True,
                uid=uid_str
            )

        except OSError as e:
            logger.error(f"SPI communication error: {e}")
            return NFCReadResult(
                success=False,
                error_message=f"SPI communication failed: {e}"
            )

        except Exception as e:
            logger.error(f"NFC read error: {e}")
            return NFCReadResult(
                success=False,
                error_message=f"NFC read failed: {e}"
            )

    def read_card_blocking(self) -> str:
        """
        Blocking read - waits for NFC card.

        Returns:
            NFC UID string

        Raises:
            RuntimeError: If read fails
        """
        logger.info("Waiting for NFC card...")
        result = self.read_card()

        if not result.success or not result.uid:
            raise RuntimeError(result.error_message or "Failed to read NFC card")

        return result.uid

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