"""Interactive menu for the TRIsecure voting terminal."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _sep(char: str = "─", width: int = 60) -> str:
    return char * width


def _header(title: str) -> None:
    print("\n" + _sep("═"))
    print(f"  {title}")
    print(_sep("═"))


class TRIsecureMenu:
    """
    Interactive CLI menu.

    Delegates all business operations to injected use-case objects so this
    class contains zero business logic — only prompts and dispatch.
    """

    def __init__(self, nfc_service, enroll_uc, vote_uc, verify_uc,
                 reenroll_uc, statistics_fn):
        self._nfc = nfc_service
        self._enroll = enroll_uc
        self._vote = vote_uc
        self._verify = verify_uc
        self._reenroll = reenroll_uc
        self._statistics = statistics_fn

    def _scan_nfc(self, prompt: str = "Present NFC card") -> Optional[str]:
        print(f"\n  [NFC] {prompt} …")
        try:
            uid = self._nfc.read_card_blocking()
            print(f"  [NFC] UID: {uid}")
            return uid
        except RuntimeError as e:
            print(f"  [NFC] Read failed: {e}")
            return None

    def run(self) -> None:
        print("\n")
        print("╔══════════════════════════════════════════════════════════╗")
        print("║         TRIsecure — Secure eVoting Terminal              ║")
        print("║   Face Recognition  ·  NFC Auth  ·  Blockchain Ledger   ║")
        print("╚══════════════════════════════════════════════════════════╝")

        while True:
            print(f"""
  {_sep('-', 40)}
   1  Enroll voter        (NFC + webcam face)
   2  Cast vote           (NFC + face match + ballot)
   3  Identify face       (webcam live identification)
   4  Statistics          (voters / votes / integrity)
   5  Re-enroll face      (update face template)
   0  Exit
  {_sep('-', 40)}""")

            choice = input("  Select option: ").strip()

            if choice == "1":
                _header("ENROLL NEW VOTER")
                name = input("  Voter name: ").strip()
                if not name:
                    print("  Name cannot be empty.")
                    continue
                nfc_uid = self._scan_nfc("Scan the NFC card for this voter")
                if nfc_uid:
                    self._enroll.execute(name, nfc_uid)

            elif choice == "2":
                _header("CAST VOTE")
                nfc_uid = self._scan_nfc("Scan your NFC card")
                if nfc_uid:
                    self._vote.execute(nfc_uid)

            elif choice == "3":
                _header("FACE IDENTIFICATION")
                self._verify.execute()

            elif choice == "4":
                self._statistics()

            elif choice == "5":
                _header("RE-ENROLL FACE")
                nfc_uid = self._scan_nfc("Scan voter's NFC card")
                if nfc_uid:
                    self._reenroll.execute(nfc_uid)

            elif choice == "0":
                print("\n  Goodbye. Audit log saved.\n")
                break
            else:
                print("  ✗ Invalid option.")
