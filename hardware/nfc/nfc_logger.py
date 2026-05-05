"""NFC diagnostics logger — wraps NFCService for hardware testing."""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from hardware.nfc.nfc_service import NFCService

logger = logging.getLogger(__name__)


class NFCLogger:
    """Log NFC card UIDs to a file for hardware diagnostics."""

    def __init__(self, log_path: str = "nfc_log.txt"):
        self.log_path = Path(log_path)
        self._service = NFCService()

    def run(self) -> None:
        """Block until Ctrl-C, logging every card tap to file and stdout."""
        initialized = self._service.initialize()
        if not initialized:
            print("  NFC hardware not available — running in simulation mode.")
        else:
            print("  NFC hardware initialized.")

        print("  Waiting for NFC card… (Ctrl-C to stop)")

        while True:
            try:
                uid = self._service.read_card_blocking(max_wait=30.0)
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                line = f"{timestamp} - UID: {uid}"
                print(f"  {line}")
                with open(self.log_path, "a") as f:
                    f.write(line + "\n")
                time.sleep(1.0)
            except RuntimeError:
                pass  # Timeout — no card tapped; keep waiting
            except KeyboardInterrupt:
                print("\n  Stopped.")
                break


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    NFCLogger().run()
