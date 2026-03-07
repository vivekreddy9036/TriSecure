#!/usr/bin/env python3
"""
NFC Card Reader Test Script for TriSecure.

Standalone utility to test NFC card reading on the Raspberry Pi
using the PN532 module over SPI.

Usage:
    python nfc_test.py              # single read
    python nfc_test.py --loop       # continuous reading
    python nfc_test.py --timeout 10 # custom timeout in seconds
"""

import argparse
import logging
import sys
import time

# ── Configure logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def init_nfc(cs_pin="D8", reset_pin="D25", baudrate=1_000_000):
    """Initialize the PN532 NFC reader over SPI. Returns the device object."""
    try:
        import board
        import busio
        from digitalio import DigitalInOut
        from adafruit_pn532.spi import PN532_SPI

        cs = DigitalInOut(getattr(board, cs_pin))
        reset = DigitalInOut(getattr(board, reset_pin))

        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        while not spi.try_lock():
            pass
        try:
            spi.configure(baudrate=baudrate)
        finally:
            spi.unlock()

        pn532 = PN532_SPI(spi, cs, reset=reset, debug=False)
        ic, ver, rev, support = pn532.firmware_version
        logger.info(f"PN532 firmware version: {ver}.{rev}")
        pn532.SAM_configuration()
        return pn532

    except ImportError:
        logger.error(
            "Adafruit PN532 libraries not installed.\n"
            "Install with: pip install adafruit-circuitpython-pn532"
        )
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to initialize NFC reader: {e}")
        sys.exit(1)


def read_card(pn532, timeout=5.0):
    """Attempt to read an NFC card UID. Returns UID hex string or None."""
    uid = pn532.read_passive_target(timeout=timeout)
    if uid is None:
        return None
    return ":".join(f"{b:02X}" for b in uid)


def single_read(pn532, max_wait=30.0, poll_interval=0.3):
    """Block until a card is tapped, then print its UID."""
    print("\n╔══════════════════════════════════════╗")
    print("║   Tap an NFC card on the reader...   ║")
    print("╚══════════════════════════════════════╝\n")

    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        uid = read_card(pn532)
        if uid:
            print(f"  ✓ Card UID: {uid}")
            print(f"  ✓ Raw bytes: {len(uid.split(':'))} bytes\n")
            return uid
        time.sleep(poll_interval)

    print(f"  ✗ No card detected within {max_wait}s\n")
    return None


def continuous_read(pn532, poll_interval=0.5):
    """Continuously read NFC cards until Ctrl+C."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   Continuous NFC read (Ctrl+C to stop)   ║")
    print("╚══════════════════════════════════════════╝\n")

    last_uid = None
    count = 0

    try:
        while True:
            uid = read_card(pn532, timeout=1.0)
            if uid and uid != last_uid:
                count += 1
                print(f"  [{count}] Card UID: {uid}")
                last_uid = uid
            elif uid is None:
                last_uid = None  # reset so same card can be read again after removal
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print(f"\n\nStopped. Total unique reads: {count}")


def main():
    parser = argparse.ArgumentParser(description="TriSecure NFC Card Reader Test")
    parser.add_argument("--loop", action="store_true", help="Continuous reading mode")
    parser.add_argument("--timeout", type=float, default=30.0, help="Max wait time in seconds (default: 30)")
    parser.add_argument("--cs", default="D8", help="SPI chip-select pin (default: D8)")
    parser.add_argument("--reset", default="D25", help="Reset pin (default: D25)")
    args = parser.parse_args()

    print("\n=== TriSecure NFC Reader Test ===\n")

    pn532 = init_nfc(cs_pin=args.cs, reset_pin=args.reset)
    logger.info("NFC reader initialized successfully")

    if args.loop:
        continuous_read(pn532)
    else:
        single_read(pn532, max_wait=args.timeout)


if __name__ == "__main__":
    main()
