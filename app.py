"""
TRIsecure - Integrated Application
===================================
Interactive voting terminal that combines:
  • Webcam face recognition  (FaceCamera + FaceAuthenticator)
  • NFC card identification  (NFCService — real PN532 or simulation)
  • SQLite voter database    (SQLiteVoterRepository)
  • Blockchain vote ledger   (BlockchainLogger)

Menu
----
  1  Enroll voter      → NFC scan + webcam face capture → register
  2  Cast vote         → NFC scan + live face match → ballot
  3  Verify face only  → live webcam identification (no vote)
  4  View statistics   → voters / votes / blockchain integrity
  5  Re-enroll face    → update face template for an existing voter
  0  Exit

Usage:
    python app.py
    python app.py --candidates "Alice,Bob,Charlie"
    python app.py --threshold 0.45
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

# ── Project imports ────────────────────────────────────────────────────────────
from config import get_config, setup_logging
from models import Voter, Vote
from repositories import SQLiteVoterRepository, SQLiteVoteRepository, SQLiteAuditRepository
from core import AuditLogger, SessionManager, AuthenticationPipeline
from hardware.nfc import NFCService
from security import BlockchainLogger
from hardware.camera.face_auth import FaceCamera, FaceAuthenticator

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FACE_MODELS_DIR = Path("data/face_models")
FACE_MODELS_DIR.mkdir(parents=True, exist_ok=True)


# ── Display detection ──────────────────────────────────────────────────────────
def _has_display() -> bool:
    """Return True when a graphical display is available (X11 / Wayland)."""
    import os
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


_HEADLESS = not _has_display()
if _HEADLESS:
    logger.info("No display detected — running in headless mode (GUI windows disabled).")


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.flatten().astype(np.float32), b.flatten().astype(np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(np.dot(a / na, b / nb), -1.0, 1.0))


def _legacy_model_path(name: str) -> Path:
    """Legacy name-based template path (backward compat only)."""
    return FACE_MODELS_DIR / f"{name.lower().replace(' ', '_')}.npy"


def _voter_model_path(voter_id) -> Path:
    """Path to multi-template face model file keyed by voter UUID."""
    return FACE_MODELS_DIR / f"{voter_id}.npz"


def _save_templates(
    voter_id,
    embedding: np.ndarray,
    append: bool = True,
) -> Path:
    """
    Save a face template for a voter.  Supports storing multiple
    templates per voter in a single .npz file.

    Args:
        voter_id:  Voter UUID.
        embedding: New embedding vector (1-D).
        append:    If True, add to existing templates; if False, replace all.

    Returns:
        Path to the saved .npz file.
    """
    path = _voter_model_path(voter_id)
    new_template = embedding.flatten().astype(np.float32).reshape(1, -1)

    if append and path.exists():
        try:
            existing = np.load(str(path))["templates"]
            if existing.ndim == 1:
                existing = existing.reshape(1, -1)
            # Dimension guard: only stack if dims match
            if existing.shape[1] == new_template.shape[1]:
                templates = np.vstack([existing, new_template])
            else:
                logger.warning(
                    f"Dimension mismatch (stored={existing.shape[1]}, "
                    f"new={new_template.shape[1]}). Replacing templates."
                )
                templates = new_template
        except Exception as e:
            logger.warning(f"Failed to load existing templates, starting fresh: {e}")
            templates = new_template
    else:
        templates = new_template

    np.savez(str(path), templates=templates)
    return path


def _load_templates(voter_id, voter_name: str = None) -> Optional[np.ndarray]:
    """
    Load all face templates for a voter.

    Returns:
        2-D array of shape (N, embedding_dim) or None if nothing found.
        Falls back to legacy name-based .npy when the new .npz is absent.
    """
    # Primary: voter-ID based .npz
    path = _voter_model_path(voter_id)
    if path.exists():
        try:
            data = np.load(str(path))
            templates = data["templates"].astype(np.float32)
            if templates.ndim == 1:
                templates = templates.reshape(1, -1)
            return templates
        except Exception as e:
            logger.error(f"Corrupt template file {path}: {e}")

    # Fallback: legacy name-based .npy
    if voter_name:
        legacy = _legacy_model_path(voter_name)
        if legacy.exists():
            try:
                emb = np.load(str(legacy)).astype(np.float32)
                return emb.reshape(1, -1) if emb.ndim == 1 else emb
            except Exception as e:
                logger.error(f"Corrupt legacy model {legacy}: {e}")

    return None


def _count_templates(voter_id) -> int:
    """Return the number of stored templates for a voter."""
    path = _voter_model_path(voter_id)
    if not path.exists():
        return 0
    try:
        data = np.load(str(path))
        t = data["templates"]
        return t.shape[0] if t.ndim == 2 else 1
    except Exception:
        return 0


def _match_against_templates(
    live_embedding: np.ndarray,
    templates: np.ndarray,
) -> float:
    """
    Compare a live embedding against all stored templates.

    Returns the highest cosine similarity (best match).
    """
    if templates is None or len(templates) == 0:
        return -1.0
    best = -1.0
    for t in templates:
        sim = _cosine_similarity(live_embedding, t)
        if sim > best:
            best = sim
    return best


# Cosine similarity above which two face embeddings are treated as the same
# person during enrollment.  Set higher than the auth threshold so only
# near-identical faces are flagged as duplicates.
_DUPLICATE_FACE_THRESHOLD = 0.68


def _check_face_uniqueness(
    new_embedding: np.ndarray,
    voter_repo,
    exclude_voter_id=None,
    threshold: float = _DUPLICATE_FACE_THRESHOLD,
):
    """
    Aadhaar-style biometric deduplication.

    Compares *new_embedding* against every enrolled voter's face templates.
    Returns early as soon as a duplicate is found.

    Args:
        new_embedding:    Embedding to check.
        voter_repo:       Voter repository (iterable via find_all()).
        exclude_voter_id: Voter ID to skip — pass the current voter's ID
                          during re-enrollment so they don't block themselves.
        threshold:        Cosine similarity at or above which the face is
                          considered already registered.

    Returns:
        Tuple (is_duplicate: bool, matched_voter_name: str | None, best_sim: float)
    """
    best_name: Optional[str] = None
    best_sim = -1.0

    for voter in voter_repo.find_all():
        if exclude_voter_id and str(voter.id) == str(exclude_voter_id):
            continue
        templates = _load_templates(voter.id, voter.name)
        if templates is None or len(templates) == 0:
            continue
        sim = _match_against_templates(new_embedding, templates)
        if sim > best_sim:
            best_sim = sim
            best_name = voter.name
        # Short-circuit: no need to check further once clearly over threshold
        if best_sim >= threshold:
            break

    return best_sim >= threshold, best_name, best_sim


def _sep(char: str = "─", width: int = 60) -> str:
    return char * width


def _header(title: str) -> None:
    print("\n" + _sep("═"))
    print(f"  {title}")
    print(_sep("═"))


# ══════════════════════════════════════════════════════════════════════════════
# Face pipeline helpers
# ══════════════════════════════════════════════════════════════════════════════

def _init_camera_and_auth(device: int = 0):
    """Return initialised (FaceCamera, FaceAuthenticator) pair."""
    camera = FaceCamera(device=device, width=320, height=240, fps=15)
    auth = FaceAuthenticator()
    camera.initialize()
    auth.initialize()
    return camera, auth


def _capture_face_embedding(
    camera: FaceCamera,
    authenticator: FaceAuthenticator,
    num_samples: int = 3,
    prompt: str = "Capturing face",
) -> Optional[np.ndarray]:
    """
    Collect `num_samples` embeddings and return their averaged +
    re-normalized vector.  When a display is available a live preview
    window is shown; on headless systems the capture runs silently.
    Returns None if capture fails.
    """
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not installed.")
        return None

    COOLDOWN = 2.0
    embeddings = []
    last_capture = 0.0
    show_gui = not _HEADLESS

    window = f"TRIsecure — {prompt}"
    if show_gui:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 320, 240)

    print(f"  [Camera] {prompt}  ({num_samples} sample(s) needed)" +
          ("  —  press Q to abort" if show_gui else ""))

    while len(embeddings) < num_samples:
        frame = camera.capture_frame()
        if frame is None:
            break

        detection = camera.detect_face(frame)
        face_found = detection.success and detection.face_image is not None

        if show_gui:
            display = frame.copy()
            status = f"Samples: {len(embeddings)}/{num_samples}"
            cv2.putText(display, status, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

        if face_found:
            if show_gui:
                x, y, w, h = detection.face_location
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 220, 0), 2)
                cv2.putText(display, "Face OK", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 0), 2)

            now = time.time()
            if now - last_capture >= COOLDOWN:
                result = authenticator.extract_embedding(detection.face_image)
                if result.success and result.embedding is not None:
                    embeddings.append(result.embedding)
                    last_capture = now
                    print(f"  [Camera] Sample {len(embeddings)}/{num_samples} captured.")
                    if show_gui:
                        overlay = display.copy()
                        overlay[:] = (0, 200, 0)
                        cv2.addWeighted(overlay, 0.3, display, 0.7, 0, display)
                        cv2.putText(display, f"CAPTURED {len(embeddings)}/{num_samples}",
                                    (140, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255,255,255), 3)
                        cv2.imshow(window, display)
                        cv2.waitKey(600)
                    continue
        else:
            if show_gui:
                cv2.putText(display, "No face", (20, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 60, 220), 2)

        if show_gui:
            cv2.imshow(window, display)
            key = cv2.waitKey(30) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                print("  [Camera] Aborted by user.")
                cv2.destroyWindow(window)
                return None

    if show_gui:
        cv2.destroyWindow(window)

    if not embeddings:
        return None

    avg = np.stack(embeddings, axis=0).mean(axis=0)
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = (avg / norm).astype(np.float32)
    return avg


# ══════════════════════════════════════════════════════════════════════════════
# Main Application
# ══════════════════════════════════════════════════════════════════════════════

class TRIsecureApp:

    def __init__(self, candidates: list, face_threshold: float, camera_device: int):
        self.candidates = candidates
        self.face_threshold = face_threshold
        self.camera_device = camera_device

        cfg = get_config()

        # Repositories
        self.voter_repo  = SQLiteVoterRepository(cfg.DATABASE_PATH)
        self.vote_repo   = SQLiteVoteRepository(cfg.DATABASE_PATH)
        self.audit_repo  = SQLiteAuditRepository(cfg.DATABASE_PATH)

        # Core
        self.audit_logger    = AuditLogger(self.audit_repo)
        self.session_manager = SessionManager(cfg.SESSION_DURATION_SECONDS)

        # NFC
        self.nfc = NFCService(timeout=cfg.NFC_TIMEOUT)
        nfc_ok = self.nfc.initialize()
        logger.info(f"NFC: {'✓ Hardware' if nfc_ok else '⚠ Simulation mode'}")

        # Blockchain
        self.blockchain = BlockchainLogger(self.vote_repo)

        logger.info(f"Face threshold : {face_threshold}")
        logger.info(f"Candidates     : {candidates}")
        logger.info(f"Face models dir: {FACE_MODELS_DIR.resolve()}")

    # ── NFC ───────────────────────────────────────────────────────────────────

    def _scan_nfc(self, prompt: str = "Present NFC card") -> Optional[str]:
        """Blocking NFC read with console feedback."""
        print(f"\n  [NFC] {prompt} …")
        try:
            uid = self.nfc.read_card_blocking()
            print(f"  [NFC] UID: {uid}")
            return uid
        except RuntimeError as e:
            print(f"  [NFC] Read failed: {e}")
            return None

    def _write_voter_id_to_card(self, voter_id: str, voter_name: str, expected_uid: str) -> bool:
        """
        Write encrypted voter UUID to the NFC card.

        Asks the voter to tap the card again and verifies it is the SAME card
        that was scanned during enrollment (UID must match expected_uid).

        Returns True if write succeeded.
        """
        print(f"\n  [NFC] Please tap the SAME NFC card again to write the encrypted voter ID…")
        try:
            uid = self.nfc.read_card_blocking(max_wait=30.0)
        except RuntimeError as e:
            print(f"  [NFC] Card not detected: {e}")
            return False

        if uid.upper() != expected_uid.upper():
            print(f"  [NFC] ✗ SECURITY VIOLATION — Card mismatch detected!")
            print(f"         Expected UID : {expected_uid.upper()}")
            print(f"         Presented UID: {uid.upper()}")
            print(f"         Enrollment aborted. The registered card must be used for writing.")
            return False

        result = self.nfc.write_voter_id(voter_id)
        if result.success:
            print(f"  [NFC] ✓ Encrypted voter ID written to card  (voter: {voter_name})")
        else:
            print(f"  [NFC] ✗ Write failed: {result.error_message}")
        return result.success

    # ── Menu actions ──────────────────────────────────────────────────────────

    def enroll_voter(self) -> None:
        """Register a new voter: NFC scan + webcam face capture."""
        _header("ENROLL NEW VOTER")

        name = input("  Voter name: ").strip()
        if not name:
            print("  Name cannot be empty.")
            return

        # Check if a voter with this name exists in the DB
        existing_by_name = None
        for v in self.voter_repo.find_all():
            if v.name.lower() == name.lower():
                existing_by_name = v
                break
        if existing_by_name and _count_templates(existing_by_name.id) > 0:
            overwrite = input(f"  '{name}' already has face templates. Overwrite? [y/N]: ").strip().lower()
            if overwrite != "y":
                print("  Enrollment cancelled.")
                return

        # 1. NFC
        nfc_uid = self._scan_nfc("Scan the NFC card for this voter")
        if not nfc_uid:
            return

        # Check NFC not already taken by another voter
        existing_voter = self.voter_repo.find_by_nfc_uid(nfc_uid)
        if existing_voter and existing_voter.name != name:
            print(f"  ✗ NFC card already registered to '{existing_voter.name}'.")
            return

        # 2. Face capture
        print(f"\n  [Face] Starting webcam for '{name}' …")
        camera, auth = _init_camera_and_auth(self.camera_device)
        try:
            embedding = _capture_face_embedding(
                camera, auth, num_samples=3,
                prompt=f"Enrolling — {name}"
            )
        finally:
            camera.release()
            auth.release()

        if embedding is None:
            print("  ✗ Face capture failed. Enrollment aborted.")
            return

        # 3. Biometric deduplication (Aadhaar-style)
        #    Skip the existing record for this voter — re-enrolling the same
        #    person should not block them.
        print("  [Face] Running deduplication check against existing registrations…")
        exclude_id = existing_by_name.id if existing_by_name else None
        is_dup, dup_name, dup_sim = _check_face_uniqueness(
            embedding, self.voter_repo, exclude_voter_id=exclude_id
        )
        if is_dup:
            print(_sep())
            print("  ✗ ENROLLMENT REJECTED — Face already registered in the system!")
            print(f"    Matched voter : {dup_name}")
            print(f"    Similarity    : {dup_sim * 100:.1f}%")
            print("    Each person may only register once (biometric deduplication).")
            print(_sep())
            return
        print(f"  [Face] Deduplication passed (best match: {dup_sim * 100:.1f}%  <  threshold)")

        # 4. Persist — save voter first so we have a stable UUID
        voter = existing_voter or Voter(name=name)
        voter.name = name
        voter.nfc_uid = nfc_uid
        voter.face_embedding = embedding.tobytes()
        self.voter_repo.save(voter)

        # Save multi-template file (fresh enrollment replaces old templates)
        emb_path = _save_templates(voter.id, embedding, append=False)
        n_templates = _count_templates(voter.id)

        # 5. Write encrypted voter UUID onto the NFC card (must be same card as step 1)
        write_ok = self._write_voter_id_to_card(str(voter.id), name, nfc_uid)

        print(_sep())
        print(f"  ✓ Voter enrolled successfully!")
        print(f"    Name       : {name}")
        print(f"    NFC UID    : {nfc_uid}")
        print(f"    Face model : {emb_path.name}")
        print(f"    Templates  : {n_templates}")
        print(f"    Voter ID   : {voter.id}")
        print(f"    NFC write  : {'✓ UUID encrypted on card' if write_ok else '⚠ Skipped (manual retry possible)'}")
        print(_sep())

    def cast_vote(self) -> None:
        """Full voting flow: NFC → face match → ballot → record."""
        _header("CAST VOTE")

        # ── Step 1: NFC ──────────────────────────────────────────────────────
        nfc_uid = self._scan_nfc("Scan your NFC card")
        if not nfc_uid:
            return

        voter = self.voter_repo.find_by_nfc_uid(nfc_uid)
        if not voter:
            print("  ✗ NFC card not registered. Please enroll first.")
            return

        if voter.has_voted:
            print(f"  ✗ '{voter.name}' has already cast their vote.")
            return

        print(f"  ✓ Voter found: {voter.name}")

        # ── Step 2: Face verification ────────────────────────────────────────
        stored_templates = _load_templates(voter.id, voter.name)
        if stored_templates is None:
            print(f"  ✗ No face model found for '{voter.name}'. Please re-enroll.")
            return
        print(f"  [Face] {stored_templates.shape[0]} template(s) loaded for matching.")

        print(f"\n  [Face] Please look at the camera for verification …")
        camera, auth = _init_camera_and_auth(self.camera_device)
        try:
            live_embedding = _capture_face_embedding(
                camera, auth, num_samples=1,
                prompt=f"Verifying — {voter.name}"
            )
        finally:
            camera.release()
            auth.release()

        if live_embedding is None:
            print("  ✗ Face capture failed. Vote aborted.")
            return

        similarity = _match_against_templates(live_embedding, stored_templates)
        match = similarity >= self.face_threshold

        print(f"\n  [Face] Similarity : {similarity * 100:.1f}%")
        print(f"  [Face] Threshold  : {self.face_threshold * 100:.0f}%")
        print(f"  [Face] Result     : {'✓ MATCH' if match else '✗ NO MATCH'}")

        if not match:
            print("  ✗ Face verification failed. Vote rejected.")
            self.audit_logger.log_nfc_read_failure(
                f"Face mismatch for {voter.name}: {similarity:.3f} < {self.face_threshold}"
            )
            return

        # ── Step 3: Ballot ───────────────────────────────────────────────────
        print(f"\n  Welcome, {voter.name}! Please choose a candidate:\n")
        for i, c in enumerate(self.candidates, 1):
            print(f"    {i}. {c}")
        print("    0. Cancel / Abstain\n")

        choice_str = input("  Your choice: ").strip()
        try:
            choice = int(choice_str)
        except ValueError:
            print("  ✗ Invalid input. Vote cancelled.")
            return

        if choice == 0:
            print("  Vote cancelled by voter.")
            return

        if choice < 1 or choice > len(self.candidates):
            print("  ✗ Choice out of range. Vote cancelled.")
            return

        candidate = self.candidates[choice - 1]

        # ── Step 4: Record ───────────────────────────────────────────────────
        confirm = input(f"\n  Confirm vote for '{candidate}'? [Y/n]: ").strip().lower()
        if confirm not in ("", "y", "yes"):
            print("  Vote cancelled.")
            return

        # Issue session, cast vote, mark voter
        session = self.session_manager.create_session(voter)

        vote = Vote(voter_id=voter.id, candidate=candidate)
        vote = self.blockchain.log_vote(vote)

        voter.mark_as_voted()
        self.voter_repo.save(voter)

        self.session_manager.deactivate_session(session.token)
        self.audit_logger.log_vote_cast(voter.id, candidate)

        print(_sep())
        print(f"  ✓ Vote recorded successfully!")
        print(f"    Voter     : {voter.name}")
        print(f"    Candidate : {candidate}")
        print(f"    Vote ID   : {vote.vote_id}")
        print(_sep())

    def verify_face_only(self) -> None:
        """Identify who is in front of the camera (no vote)."""
        _header("FACE IDENTIFICATION")

        # Load face templates grouped by voter from the database
        models = {}   # {voter_name: np.ndarray of shape (N, dim)}
        voters = self.voter_repo.find_all()
        for v in voters:
            templates = _load_templates(v.id, v.name)
            if templates is not None and len(templates) > 0:
                models[v.name] = templates

        if not models:
            print("  No face models enrolled yet.  Run option 1 first.")
            return

        total_tpl = sum(t.shape[0] for t in models.values())
        print(f"  Loaded {len(models)} voter(s) ({total_tpl} template(s)): {', '.join(models.keys())}")
        print("  Press Q in the camera window to stop.\n")

        try:
            import cv2
        except ImportError:
            logger.error("OpenCV required.")
            return

        camera, auth = _init_camera_and_auth(self.camera_device)
        COOLDOWN = 1.5
        last_capture = 0.0
        last_name = "Scanning…"
        last_sim  = 0.0
        last_match = False
        last_loc  = None

        window = "TRIsecure — Face Identification"
        show_gui = not _HEADLESS
        if show_gui:
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 640, 480)

        try:
            while True:
                frame = camera.capture_frame()
                if frame is None:
                    break

                detection = camera.detect_face(frame)
                display = frame.copy() if show_gui else None
                face_found = detection.success and detection.face_image is not None

                now = time.time()
                if face_found and (now - last_capture) >= COOLDOWN:
                    result = auth.extract_embedding(detection.face_image)
                    if result.success and result.embedding is not None:
                        best_name, best_sim, is_match = "Unknown", -1.0, False
                        e = result.embedding
                        for vname, templates in models.items():
                            sim = _match_against_templates(e, templates)
                            if sim > best_sim:
                                best_sim, best_name = sim, vname
                        is_match = best_sim >= self.face_threshold
                        last_name  = best_name if is_match else "Unknown"
                        last_sim   = best_sim
                        last_match = is_match
                        last_loc   = detection.face_location
                        last_capture = now

                        status = "MATCH" if is_match else "NO MATCH"
                        logger.info(f"Identity: {last_name} | Similarity: {best_sim*100:.1f}% | {status}")

                # Draw (only when display available)
                if show_gui:
                    if last_loc:
                        x, y, w, h = last_loc
                        color = (0, 220, 0) if last_match else (0, 60, 220)
                        cv2.rectangle(display, (x, y), (x + w, y + h), color, 2)
                        label = f"{last_name}  ({last_sim*100:.1f}%)"
                        cv2.putText(display, label, (x, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                    if not face_found:
                        cv2.putText(display, "No face detected", (15, 60),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 100, 255), 2)

                    cv2.putText(display, "Q = quit", (10, display.shape[0] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
                    cv2.imshow(window, display)

                    if cv2.waitKey(30) & 0xFF in (ord('q'), ord('Q'), 27):
                        break
                else:
                    # Headless: run a single pass then stop
                    break
        finally:
            if show_gui:
                cv2.destroyWindow(window)
            camera.release()
            auth.release()

    def show_statistics(self) -> None:
        """Print voter counts, vote tallies and blockchain integrity."""
        _header("SYSTEM STATISTICS")

        voters = self.voter_repo.find_all()
        voted  = [v for v in voters if v.has_voted]
        eligible = [v for v in voters if not v.has_voted]

        print(f"  Registered voters : {len(voters)}")
        print(f"  Already voted     : {len(voted)}")
        print(f"  Still eligible    : {len(eligible)}")

        # Enrolled face templates
        total_templates = 0
        print(f"  Face templates:")
        for v in voters:
            n = _count_templates(v.id)
            total_templates += n
            if n > 0:
                print(f"    • {v.name:<25} {n} template(s)")
            else:
                # Check legacy .npy fallback
                legacy = _legacy_model_path(v.name)
                if legacy.exists():
                    print(f"    • {v.name:<25} 1 template (legacy .npy)")
                    total_templates += 1
                else:
                    print(f"    • {v.name:<25} ✗ no templates")
        print(f"  Total templates   : {total_templates}")

        print()
        stats = self.blockchain.get_blockchain_statistics()
        print(f"  Total votes cast  : {stats['total_votes']}")
        print(f"  Blockchain valid  : {'✓ Yes' if stats['chain_valid'] else '✗ COMPROMISED'}")

        if stats.get("votes_per_candidate"):
            print("\n  Votes per candidate:")
            for cand, count in stats["votes_per_candidate"].items():
                bar = "█" * count
                print(f"    {cand:<25} {bar} ({count})")

        if voters:
            print("\n  Voter status:")
            for v in voters:
                status = "✓ voted" if v.has_voted else "○ pending"
                has_tpl = _count_templates(v.id) > 0 or _legacy_model_path(v.name).exists()
                model = "face ✓" if has_tpl else "face ✗"
                print(f"    {v.name:<25} {status:<12} {model}  NFC: {v.nfc_uid or 'none'}")

        print(_sep())

    def reenroll_face(self) -> None:
        """Update face template for an existing voter (NFC identifies them)."""
        _header("RE-ENROLL FACE")

        nfc_uid = self._scan_nfc("Scan voter's NFC card")
        if not nfc_uid:
            return

        voter = self.voter_repo.find_by_nfc_uid(nfc_uid)
        if not voter:
            print("  ✗ NFC not registered. Use option 1 to do a full enrolment.")
            return

        print(f"  Voter: {voter.name}")
        confirm = input("  Re-capture face for this voter? [Y/n]: ").strip().lower()
        if confirm not in ("", "y", "yes"):
            print("  Cancelled.")
            return

        camera, auth = _init_camera_and_auth(self.camera_device)
        try:
            embedding = _capture_face_embedding(
                camera, auth, num_samples=3,
                prompt=f"Re-enrolling — {voter.name}"
            )
        finally:
            camera.release()
            auth.release()

        if embedding is None:
            print("  ✗ Face capture failed.")
            return

        # Biometric deduplication — exclude this voter so they don't block
        # their own re-enrollment, but catch if someone else tries to use
        # the same NFC card with a different face.
        print("  [Face] Running deduplication check against other registrations…")
        is_dup, dup_name, dup_sim = _check_face_uniqueness(
            embedding, self.voter_repo, exclude_voter_id=voter.id
        )
        if is_dup:
            print(_sep())
            print("  ✗ RE-ENROLLMENT REJECTED — Face matches another registered voter!")
            print(f"    Matched voter : {dup_name}")
            print(f"    Similarity    : {dup_sim * 100:.1f}%")
            print("    Biometric deduplication prevents cross-registration.")
            print(_sep())
            return
        print(f"  [Face] Deduplication passed (best match: {dup_sim * 100:.1f}%  <  threshold)")

        # Append new template to existing ones (improves recognition
        # by adding templates captured under different conditions).
        emb_path = _save_templates(voter.id, embedding, append=True)
        voter.face_embedding = embedding.tobytes()
        self.voter_repo.save(voter)
        n_templates = _count_templates(voter.id)

        # Re-write encrypted voter UUID to card with updated info
        write_ok = self._write_voter_id_to_card(str(voter.id), voter.name)

        print(f"  ✓ Face template added for '{voter.name}'  →  {emb_path.name}")
        print(f"    Total templates for this voter: {n_templates}")
        print(f"    NFC write  : {'✓ UUID encrypted on card' if write_ok else '⚠ Skipped (manual retry possible)'}")

    # ── Main loop ─────────────────────────────────────────────────────────────

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
                self.enroll_voter()
            elif choice == "2":
                self.cast_vote()
            elif choice == "3":
                self.verify_face_only()
            elif choice == "4":
                self.show_statistics()
            elif choice == "5":
                self.reenroll_face()
            elif choice == "0":
                print("\n  Goodbye. Audit log saved.\n")
                break
            else:
                print("  ✗ Invalid option.")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="TRIsecure integrated voting terminal")
    p.add_argument("--candidates", "-c",
                   default="Candidate A,Candidate B,Candidate C",
                   help="Comma-separated list of candidates")
    p.add_argument("--threshold", "-t", type=float, default=0.55,
                   help="Face cosine similarity threshold (default: 0.55)")
    p.add_argument("--device", "-d", type=int, default=0,
                   help="Webcam device index (default: 0)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    candidates = [c.strip() for c in args.candidates.split(",") if c.strip()]

    cfg = get_config()
    setup_logging(cfg)

    app = TRIsecureApp(
        candidates=candidates,
        face_threshold=args.threshold,
        camera_device=args.device,
    )
    app.run()
