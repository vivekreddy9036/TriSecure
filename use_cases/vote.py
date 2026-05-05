"""Cast vote use-case: NFC → face match → ballot → record."""

import logging
from typing import List

from models import Vote
from use_cases._face_helpers import (
    init_camera_and_auth, capture_face_embedding,
    load_templates, match_against_templates,
)

logger = logging.getLogger(__name__)


class CastVoteUseCase:

    def __init__(self, voter_repo, vote_repo, blockchain, session_manager,
                 audit_logger, candidates: List[str],
                 face_threshold: float = 0.55,
                 camera_device: int = 0, headless: bool = False):
        self._voter_repo = voter_repo
        self._vote_repo = vote_repo
        self._blockchain = blockchain
        self._session_mgr = session_manager
        self._audit = audit_logger
        self._candidates = candidates
        self._threshold = face_threshold
        self._device = camera_device
        self._headless = headless

    def execute(self, nfc_uid: str) -> bool:
        voter = self._voter_repo.find_by_nfc_uid(nfc_uid)
        if not voter:
            print("  ✗ NFC card not registered. Please enroll first.")
            return False

        if voter.has_voted:
            print(f"  ✗ '{voter.name}' has already cast their vote.")
            return False

        print(f"  ✓ Voter found: {voter.name}")

        # Face verification
        stored_templates = load_templates(voter.id, voter.name)
        if stored_templates is None:
            print(f"  ✗ No face model found for '{voter.name}'. Please re-enroll.")
            return False
        print(f"  [Face] {stored_templates.shape[0]} template(s) loaded for matching.")

        print(f"\n  [Face] Please look at the camera for verification …")
        camera, auth = init_camera_and_auth(self._device)
        try:
            live_embedding = capture_face_embedding(
                camera, auth, num_samples=1,
                prompt=f"Verifying — {voter.name}",
                headless=self._headless,
            )
        finally:
            camera.release()
            auth.release()

        if live_embedding is None:
            print("  ✗ Face capture failed. Vote aborted.")
            return False

        similarity = match_against_templates(live_embedding, stored_templates)
        match = similarity >= self._threshold

        print(f"\n  [Face] Similarity : {similarity * 100:.1f}%")
        print(f"  [Face] Threshold  : {self._threshold * 100:.0f}%")
        print(f"  [Face] Result     : {'✓ MATCH' if match else '✗ NO MATCH'}")

        if not match:
            print("  ✗ Face verification failed. Vote rejected.")
            self._audit.log_face_match_failure(
                f"Face mismatch for {voter.name}: {similarity:.3f} < {self._threshold}"
            )
            return False

        # Ballot
        print(f"\n  Welcome, {voter.name}! Please choose a candidate:\n")
        for i, c in enumerate(self._candidates, 1):
            print(f"    {i}. {c}")
        print("    0. Cancel / Abstain\n")

        choice_str = input("  Your choice: ").strip()
        try:
            choice = int(choice_str)
        except ValueError:
            print("  ✗ Invalid input. Vote cancelled.")
            return False

        if choice == 0:
            print("  Vote cancelled by voter.")
            return False

        if choice < 1 or choice > len(self._candidates):
            print("  ✗ Choice out of range. Vote cancelled.")
            return False

        candidate = self._candidates[choice - 1]

        confirm = input(f"\n  Confirm vote for '{candidate}'? [Y/n]: ").strip().lower()
        if confirm not in ("", "y", "yes"):
            print("  Vote cancelled.")
            return False

        # Record
        session = self._session_mgr.create_session(voter)
        vote = Vote(voter_id=voter.id, candidate=candidate)
        vote = self._blockchain.log_vote(vote)
        voter.mark_as_voted()
        self._voter_repo.save(voter)
        self._session_mgr.deactivate_session(session.token)
        self._audit.log_vote_cast(voter.id, candidate)

        print("  " + "─" * 58)
        print(f"  ✓ Vote recorded successfully!")
        print(f"    Voter     : {voter.name}")
        print(f"    Candidate : {candidate}")
        print(f"    Vote ID   : {vote.vote_id}")
        print("  " + "─" * 58)
        return True
