"""
NFC hardware module for TRIsecure.

Provides:
- NFCService: PN532 NFC reader over SPI (Raspberry Pi)
  Falls back to simulation mode on non-Pi hardware.
"""

from hardware.nfc.nfc_service import NFCService, NFCReadResult

__all__ = ["NFCService", "NFCReadResult"]
