"""Enroll voter use-case: NFC scan + face capture + deduplication + persist."""

import logging
from typing import Optional

from models import Voter
from use_cases._face_helpers import (
    init_camera_and_auth, capture_face_embedding,
    save_templates, count_templates, check_face_uniqueness,
    legacy_model_path,
)

logger = logging.getLogger(__name__)


class EnrollUseCase:

    def __init__(self, voter_repo, nfc_service, audit_logger,
                 camera_device: int = 0, headless: bool = False):
        self._voter_repo = voter_repo
        self._nfc = nfc_service
        self._audit = audit_logger
        self._device = camera_device
        self._headless = headless

    def execute(self, name: str, nfc_uid: str) -> bool:
        """
        Enroll a new voter.

        Args:
            name:    Voter's full name (non-empty).
            nfc_uid: UID already scanned from the card before calling this.

        Returns:
            True on success.
        """
        if not name.strip():
            print("  Name cannot be empty.")
            return False

        # Check if a voter with this name exists (re-enrollment path)
        existing_by_name = None
        for v in self._voter_repo.find_all():
            if v.name.lower() == name.lower():
                existing_by_name = v
                break
        if existing_by_name and count_templates(existing_by_name.id) > 0:
            overwrite = input(f"  '{name}' already has face templates. Overwrite? [y/N]: ").strip().lower()
            if overwrite != "y":
                print("  Enrollment cancelled.")
                return False

        # Check NFC not already taken by another voter
        existing_voter = self._voter_repo.find_by_nfc_uid(nfc_uid)
        if existing_voter and existing_voter.name.lower() != name.lower():
            print(f"  ✗ NFC card already registered to '{existing_voter.name}'.")
            return False

        # Face capture
        print(f"\n  [Face] Starting webcam for '{name}' …")
        camera, auth = init_camera_and_auth(self._device)
        try:
            embedding = capture_face_embedding(
                camera, auth, num_samples=3,
                prompt=f"Enrolling — {name}",
                headless=self._headless,
            )
        finally:
            camera.release()
            auth.release()

        if embedding is None:
            print("  ✗ Face capture failed. Enrollment aborted.")
            return False

        # Biometric deduplication
        print("  [Face] Running deduplication check against existing registrations…")
        exclude_id = existing_by_name.id if existing_by_name else None
        is_dup, dup_name, dup_sim = check_face_uniqueness(
            embedding, self._voter_repo, exclude_voter_id=exclude_id
        )
        if is_dup:
            print("  ─" * 30)
            print("  ✗ ENROLLMENT REJECTED — Face already registered in the system!")
            print(f"    Matched voter : {dup_name}")
            print(f"    Similarity    : {dup_sim * 100:.1f}%")
            print("  ─" * 30)
            return False
        print(f"  [Face] Deduplication passed (best match: {dup_sim * 100:.1f}%)")

        # Persist voter
        voter = existing_voter or Voter(name=name)
        voter.name = name
        voter.nfc_uid = nfc_uid
        voter.face_embedding = embedding.tobytes()
        self._voter_repo.save(voter)

        emb_path = save_templates(voter.id, embedding, append=False)
        n_templates = count_templates(voter.id)

        # Write encrypted voter UUID to the NFC card (requires same card)
        write_ok = self._write_voter_id(str(voter.id), name, nfc_uid)

        print("  " + "─" * 58)
        print(f"  ✓ Voter enrolled successfully!")
        print(f"    Name       : {name}")
        print(f"    NFC UID    : {nfc_uid}")
        print(f"    Face model : {emb_path.name}")
        print(f"    Templates  : {n_templates}")
        print(f"    Voter ID   : {voter.id}")
        print(f"    NFC write  : {'✓ UUID encrypted on card' if write_ok else '⚠ Skipped'}")
        print("  " + "─" * 58)
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
