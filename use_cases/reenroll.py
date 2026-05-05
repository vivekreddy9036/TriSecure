"""Re-enroll face use-case: update face template for an existing voter."""

import logging

from use_cases._face_helpers import (
    init_camera_and_auth, capture_face_embedding,
    save_templates, count_templates, check_face_uniqueness,
)

logger = logging.getLogger(__name__)


class ReenrollUseCase:

    def __init__(self, voter_repo, nfc_service,
                 camera_device: int = 0, headless: bool = False):
        self._voter_repo = voter_repo
        self._nfc = nfc_service
        self._device = camera_device
        self._headless = headless

    def execute(self, nfc_uid: str) -> bool:
        voter = self._voter_repo.find_by_nfc_uid(nfc_uid)
        if not voter:
            print("  ✗ NFC not registered. Use option 1 to do a full enrolment.")
            return False

        print(f"  Voter: {voter.name}")
        confirm = input("  Re-capture face for this voter? [Y/n]: ").strip().lower()
        if confirm not in ("", "y", "yes"):
            print("  Cancelled.")
            return False

        camera, auth = init_camera_and_auth(self._device)
        try:
            embedding = capture_face_embedding(
                camera, auth, num_samples=3,
                prompt=f"Re-enrolling — {voter.name}",
                headless=self._headless,
            )
        finally:
            camera.release()
            auth.release()

        if embedding is None:
            print("  ✗ Face capture failed.")
            return False

        print("  [Face] Running deduplication check against other registrations…")
        is_dup, dup_name, dup_sim = check_face_uniqueness(
            embedding, self._voter_repo, exclude_voter_id=voter.id
        )
        if is_dup:
            print("  " + "─" * 58)
            print("  ✗ RE-ENROLLMENT REJECTED — Face matches another registered voter!")
            print(f"    Matched voter : {dup_name}")
            print(f"    Similarity    : {dup_sim * 100:.1f}%")
            print("  " + "─" * 58)
            return False
        print(f"  [Face] Deduplication passed (best match: {dup_sim * 100:.1f}%)")

        emb_path = save_templates(voter.id, embedding, append=True)
        voter.face_embedding = embedding.tobytes()
        self._voter_repo.save(voter)
        n_templates = count_templates(voter.id)

        # Re-write encrypted voter UUID to card (must be same card)
        write_ok = self._write_voter_id(str(voter.id), voter.name, voter.nfc_uid)

        print(f"  ✓ Face template added for '{voter.name}'  →  {emb_path.name}")
        print(f"    Total templates for this voter: {n_templates}")
        print(f"    NFC write  : {'✓ UUID encrypted on card' if write_ok else '⚠ Skipped'}")
        return True

    def _write_voter_id(self, voter_id: str, voter_name: str, expected_uid: str) -> bool:
        print("\n  [NFC] Please tap the SAME NFC card again to write the encrypted voter ID…")
        try:
            uid = self._nfc.read_card_blocking(max_wait=30.0)
        except RuntimeError as e:
            print(f"  [NFC] Card not detected: {e}")
            return False

        if uid.upper() != expected_uid.upper():
            print("  [NFC] ✗ SECURITY VIOLATION — Card mismatch detected!")
            return False

        result = self._nfc.write_voter_id(voter_id)
        if result.success:
            print(f"  [NFC] ✓ Encrypted voter ID written to card  (voter: {voter_name})")
        else:
            print(f"  [NFC] ✗ Write failed: {result.error_message}")
        return result.success
