"""
NFC Card Reader Service.

Abstracts NFC hardware communication for Raspberry Pi PN532 module.
Uses I2C interface (address 0x24).
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
    NFC card reader abstraction for PN532 NFC module.
    
    Hardware:
    - Device: PN532 NFC Reader (I2C)
    - Address: 0x24 (configurable)
    - Interface: I2C (compatible with Raspberry Pi)
    
    Responsibilities:
    - Initialize PN532 device
    - Read NFC card UIDs
    - Handle I2C communication errors gracefully
    - Provide clean API for authentication pipeline
    
    Architecture:
    - Hardware abstraction layer
    - Graceful error handling for Linux ARM
    - No hardcoded device paths
    - Ready for mock injection in tests
    """
    
    def __init__(self, i2c_address: int = 0x24, i2c_bus: int = 1, timeout: float = 5.0):
        """
        Initialize NFC service.
        
        Args:
            i2c_address: I2C address of PN532 module (0x24 default)
            i2c_bus: I2C bus number for Raspberry Pi (1 for Pi 4)
            timeout: Read timeout in seconds
        """
        self.i2c_address = i2c_address
        self.i2c_bus = i2c_bus
        self.timeout = timeout
        self._device = None
        self._initialized = False
        
        logger.info(f"NFCService initialized (address=0x{i2c_address:02x}, bus={i2c_bus})")
    
    def initialize(self) -> bool:
        """
        Initialize NFC device connection.
        
        Returns:
            True if initialization successful
        """
        try:
            # Import here to handle missing dependencies gracefully
            import board
            import busio
            from adafruit_pn532.i2c import PN532_I2C
            
            # Initialize I2C bus
            i2c = busio.I2C(board.SCL, board.SDA)
            self._device = PN532_I2C(i2c, address=self.i2c_address)
            
            # Verify device communication
            self._device.SAM_configuration()
            self._initialized = True
            
            logger.info("NFC device initialized successfully")
            return True
            
        except ImportError:
            logger.warning("NFC libraries not installed (Adafruit PN532). Running in simulation mode.")
            self._initialized = False
            return False
        
        except Exception as e:
            logger.error(f"Failed to initialize NFC device: {e}")
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
            # Read card (blocking operation)
            uid = self._device.read_passive_target(timeout=self.timeout)
            
            if uid is None:
                logger.debug("No NFC card detected")
                return NFCReadResult(
                    success=False,
                    error_message="No NFC card detected"
                )
            
            # Convert UID bytes to hex string
            uid_str = uid.hex().upper()
            logger.info(f"NFC card read successfully: {uid_str}")
            
            return NFCReadResult(
                success=True,
                uid=uid_str
            )
        
        except OSError as e:
            logger.error(f"I2C communication error: {e}")
            return NFCReadResult(
                success=False,
                error_message=f"I2C communication failed: {e}"
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
