"""
TRIsecure V2 — Real-Data Pilot Collection Framework

Collects genuine authentication attempts, impostor attempts, and
physical presentation attacks (print / replay) from live subjects
using the deployed hardware stack (ArcFace + MiniFASNet + camera).

Outputs a CSV log compatible with pilot_metrics.py for computing
operational FAR, FRR, APCER, BPCER, and ACER.

Usage:
    python experiments/collect.py

Pilot target:
    10–15 enrolled subjects × 10 genuine attempts  = 100–150 genuine
    50 impostor attempts (different subject vs template)
    50 print attacks (A4 photo printed, held to camera)
    50 replay attacks (face video played on phone/screen)
    ─────────────────────────────────────────────────────
    ~300 total events → real operational metrics

CSV schema:
    timestamp, subject_id, attempt_type, face_score,
    pad_confidence, pad_live, ats_score, decision
"""

import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Paths ────────────────────────────────────────────────────────────────────
_DATA_DIR     = Path("data")
_ENROLL_FILE  = _DATA_DIR / "pilot_enrollments.json"
_CSV_FILE     = _DATA_DIR / "pilot_collection.csv"
_RESULTS_FILE = Path("experiments") / "pilot_metrics.json"

# ── Biometric thresholds (from paper Section IV) ──────────────────────────────
_FACE_THRESHOLD = 0.45   # ArcFace cosine similarity
_PAD_THRESHOLD  = 0.50   # MiniFASNet live probability
_ATS_HIGH       = 0.75
_ATS_MED        = 0.50

_CSV_FIELDS = [
    "timestamp", "subject_id", "attempt_type",
    "face_score", "pad_confidence", "pad_live",
    "ats_score", "decision",
]

ATTEMPT_TYPES = {
    "1": "GENUINE",
    "2": "IMPOSTOR",
    "3": "PRINT_ATTACK",
    "4": "REPLAY_ATTACK",
}


# ── Hardware initialisation ───────────────────────────────────────────────────

def _init_hardware():
    """Load camera, face recogniser, and PAD. Return (camera, face_auth, pad)."""
    from hardware.camera.face_auth import FaceAuthenticator, FaceCamera
    from hardware.camera.pad_detector import PADDetector

    print("  Initialising camera …", end=" ", flush=True)
    camera = FaceCamera(device=0)
    try:
        camera.initialize()
        print("OK")
    except Exception as exc:
        print(f"FAILED ({exc})")
        camera = None

    print("  Initialising MobileFaceNet …", end=" ", flush=True)
    face_auth = FaceAuthenticator()
    face_auth.initialize()
    mode = "simulation" if face_auth._simulation_mode else "MobileFaceNet ONNX"
    print(mode)

    print("  Initialising PAD …", end=" ", flush=True)
    pad = PADDetector()
    mode = "simulation" if pad._simulated else "MiniFASNetV2"
    print(mode)

    return camera, face_auth, pad


# ── Subject enrolment DB ──────────────────────────────────────────────────────

def _load_enrollments() -> dict:
    if _ENROLL_FILE.exists():
        with open(_ENROLL_FILE) as f:
            raw = json.load(f)
        return {k: np.array(v, dtype=np.float32) for k, v in raw.items()}
    return {}


def _save_enrollments(db: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_ENROLL_FILE, "w") as f:
        json.dump({k: v.tolist() for k, v in db.items()}, f)


def _enroll_subject(subject_id: str, camera, face_auth, db: dict,
                    n_frames: int = 5) -> bool:
    """Capture n_frames, average embedding, store in db."""
    print(f"\n  Enrolling {subject_id} — please look at the camera.")
    # Flush stale frames from the previous subject before starting
    if camera is not None:
        for _ in range(5):
            camera.capture_frame()
    embeddings = []
    for i in range(n_frames):
        input(f"  Frame {i+1}/{n_frames} — press Enter to capture …")
        face_img = _capture_face(camera, debug=(i == 0))
        if face_img is None:
            print("  No face detected, retrying …")
            continue
        result = face_auth.extract_embedding(face_img)
        if result.success:
            embeddings.append(result.embedding)
            print(f"  Captured (cosine self-check not applicable at enrol time)")
        else:
            print(f"  Extraction failed: {result.error_message}")

    if not embeddings:
        print("  Enrolment failed — no valid frames captured.")
        return False

    template = np.mean(np.stack(embeddings), axis=0).astype(np.float32)
    norm = np.linalg.norm(template)
    db[subject_id] = template / norm if norm > 0 else template
    _save_enrollments(db)
    print(f"  Enrolled {subject_id} from {len(embeddings)} frames.")
    return True


# ── Capture helpers ───────────────────────────────────────────────────────────

def _capture_face(camera, retries: int = 5, debug: bool = False):
    """Return cropped face array or None. Retries up to `retries` times."""
    if camera is None:
        return None
    for attempt in range(retries):
        if debug and attempt == 0:
            # Capture once, save for debug AND use the same frame for detection
            raw = camera.capture_frame()
            if raw is not None:
                import cv2
                debug_path = str(_DATA_DIR / "debug_frame.jpg")
                cv2.imwrite(debug_path, raw)
                print(f"  [debug] raw frame saved → {debug_path}")
                result = camera.detect_face(raw)
            else:
                result = camera.capture_and_detect()
        else:
            result = camera.capture_and_detect()

        if result.success:
            return result.face_image
        if attempt < retries - 1:
            print(f"  (retry {attempt + 1}/{retries - 1} — {result.error_message})")
    return None


def _ats_score(face_conf: float, nfc_valid: bool, pad_live: bool) -> float:
    w = {"face": 0.30, "nfc": 0.40, "pad": 0.30}  # normal context weights
    return w["face"] * face_conf + w["nfc"] * float(nfc_valid) + w["pad"] * float(pad_live)


def _decision(ats: float) -> str:
    if ats >= _ATS_HIGH:
        return "ACCEPT"
    elif ats >= _ATS_MED:
        return "ESCALATE"
    return "REJECT"


# ── CSV logging ───────────────────────────────────────────────────────────────

def _write_row(row: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not _CSV_FILE.exists()
    with open(_CSV_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _log_attempt(
    subject_id: str,
    attempt_type: str,
    face_score: float,
    pad_confidence: float,
    pad_live: bool,
    nfc_valid: bool = True,   # NFC assumed valid for genuine; False for impostor attacks
) -> None:
    from scipy.stats import norm as sp_norm

    # Face confidence (LR-sigmoid)
    MU_G, SG = 0.72, 0.08
    MU_I, SI = 0.28, 0.12
    p_g = float(sp_norm.pdf(face_score, MU_G, SG)) + 1e-12
    p_i = float(sp_norm.pdf(face_score, MU_I, SI)) + 1e-12
    lr = p_g / p_i
    face_conf = lr / (1.0 + lr)

    ats = _ats_score(face_conf, nfc_valid, pad_live)
    dec = _decision(ats)

    row = {
        "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "subject_id":     subject_id,
        "attempt_type":   attempt_type,
        "face_score":     round(face_score, 4),
        "pad_confidence": round(pad_confidence, 4),
        "pad_live":       int(pad_live),
        "ats_score":      round(ats, 4),
        "decision":       dec,
    }
    _write_row(row)
    print(f"  Logged: face={face_score:.3f}  PAD={pad_confidence:.3f}({'live' if pad_live else 'SPOOF'})  "
          f"ATS={ats:.3f}  → {dec}")


# ── Attempt handlers ──────────────────────────────────────────────────────────

def _run_genuine(subject_id: str, camera, face_auth, pad, db: dict) -> None:
    if subject_id not in db:
        print(f"  Subject {subject_id} not enrolled. Enrol first.")
        return
    template = db[subject_id]
    input("  Look at camera, press Enter …")
    face_img = _capture_face(camera)
    if face_img is None:
        print("  No face detected."); return

    emb_res = face_auth.extract_embedding(face_img)
    if not emb_res.success:
        print(f"  Embedding failed: {emb_res.error_message}"); return

    from hardware.camera.face_auth import FaceAuthenticator
    score = float(FaceAuthenticator.cosine_similarity(emb_res.embedding, template))

    pad_res = pad.detect(face_img)
    _log_attempt(subject_id, "GENUINE", score, pad_res.confidence, pad_res.is_live,
                 nfc_valid=True)


def _run_impostor(subject_id: str, vs_subject: str,
                  camera, face_auth, pad, db: dict) -> None:
    """Live person (subject_id) tries to authenticate as vs_subject."""
    if vs_subject not in db:
        print(f"  Target {vs_subject} not enrolled."); return
    template = db[vs_subject]
    input(f"  {subject_id} look at camera (authenticating as {vs_subject}), press Enter …")
    face_img = _capture_face(camera)
    if face_img is None:
        print("  No face detected."); return

    emb_res = face_auth.extract_embedding(face_img)
    if not emb_res.success:
        print(f"  Embedding failed: {emb_res.error_message}"); return

    score = float(np.dot(emb_res.embedding, template))
    pad_res = pad.detect(face_img)
    # NFC won't match (different person's card)
    _log_attempt(subject_id, "IMPOSTOR", score, pad_res.confidence, pad_res.is_live,
                 nfc_valid=False)


def _run_attack(attack_type: str, target_subject: str,
                camera, face_auth, pad, db: dict) -> None:
    """Record a print or replay attack presented to the camera."""
    if target_subject not in db:
        print(f"  Target {target_subject} not enrolled."); return
    template = db[target_subject]

    label = "PRINTED PHOTO" if attack_type == "PRINT_ATTACK" else "REPLAY VIDEO"
    print(f"\n  Present the {label} to the camera.")
    input("  Ready — press Enter to capture …")

    face_img = _capture_face(camera)
    if face_img is None:
        print("  No face detected in spoof sample."); return

    emb_res = face_auth.extract_embedding(face_img)
    if not emb_res.success:
        print(f"  Embedding failed: {emb_res.error_message}"); return

    score = float(np.dot(emb_res.embedding, template))
    pad_res = pad.detect(face_img)
    # NFC not cloned — impostor doesn't have the card
    _log_attempt(target_subject, attack_type, score, pad_res.confidence, pad_res.is_live,
                 nfc_valid=False)


# ── Metrics computation ───────────────────────────────────────────────────────

def _compute_metrics() -> None:
    if not _CSV_FILE.exists():
        print("  No data collected yet."); return

    rows = []
    with open(_CSV_FILE) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("  CSV is empty."); return

    genuine  = [r for r in rows if r["attempt_type"] == "GENUINE"]
    impostor = [r for r in rows if r["attempt_type"] == "IMPOSTOR"]
    print_at = [r for r in rows if r["attempt_type"] == "PRINT_ATTACK"]
    replay   = [r for r in rows if r["attempt_type"] == "REPLAY_ATTACK"]
    attacks  = print_at + replay

    def _far(rows_):
        if not rows_: return float("nan")
        accepted = sum(1 for r in rows_ if r["decision"] == "ACCEPT")
        return accepted / len(rows_)

    def _frr(rows_):
        if not rows_: return float("nan")
        rejected = sum(1 for r in rows_ if r["decision"] == "REJECT")
        return rejected / len(rows_)

    def _apcer(rows_):   # ISO 30107-3: attacks classified as genuine by system
        if not rows_: return float("nan")
        passed = sum(1 for r in rows_ if r["decision"] == "ACCEPT")
        return passed / len(rows_)

    def _bpcer(rows_):   # ISO 30107-3: genuine presentations rejected by system
        if not rows_: return float("nan")
        rejected = sum(1 for r in rows_ if r["decision"] == "REJECT")
        return rejected / len(rows_)

    far   = _far(impostor)
    frr   = _frr(genuine)
    apcer_print  = _apcer(print_at)
    apcer_replay = _apcer(replay)
    apcer        = _apcer(attacks)
    bpcer        = _bpcer(genuine)
    acer         = (apcer + bpcer) / 2 if not (
        float("nan") in (apcer, bpcer)) else float("nan")

    metrics = {
        "n_genuine":       len(genuine),
        "n_impostor":      len(impostor),
        "n_print_attack":  len(print_at),
        "n_replay_attack": len(replay),
        "FAR":             round(far, 4)   if far  == far  else None,
        "FRR":             round(frr, 4)   if frr  == frr  else None,
        "APCER_print":     round(apcer_print, 4)   if apcer_print == apcer_print else None,
        "APCER_replay":    round(apcer_replay, 4)  if apcer_replay == apcer_replay else None,
        "APCER_combined":  round(apcer, 4) if apcer == apcer else None,
        "BPCER":           round(bpcer, 4) if bpcer == bpcer else None,
        "ACER":            round(acer, 4)  if acer == acer  else None,
        "source":          "real_pilot",
        "csv":             str(_CSV_FILE),
    }

    print("\n  ══ Pilot Metrics ══════════════════════════════")
    print(f"  Genuine attempts :   {len(genuine)}")
    print(f"  Impostor attempts:   {len(impostor)}")
    print(f"  Print attacks    :   {len(print_at)}")
    print(f"  Replay attacks   :   {len(replay)}")
    print()
    print(f"  FAR              :   {far*100:.2f}%"   if far == far  else "  FAR: n/a")
    print(f"  FRR              :   {frr*100:.2f}%"   if frr == frr  else "  FRR: n/a")
    print(f"  APCER (print)    :   {apcer_print*100:.2f}%" if apcer_print==apcer_print else "  APCER(print): n/a")
    print(f"  APCER (replay)   :   {apcer_replay*100:.2f}%" if apcer_replay==apcer_replay else "  APCER(replay): n/a")
    print(f"  APCER combined   :   {apcer*100:.2f}%" if apcer==apcer else "  APCER: n/a")
    print(f"  BPCER            :   {bpcer*100:.2f}%" if bpcer==bpcer else "  BPCER: n/a")
    print(f"  ACER             :   {acer*100:.2f}%"  if acer==acer  else "  ACER: n/a")
    print("  ════════════════════════════════════════════════")

    _RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_FILE, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  Saved → {_RESULTS_FILE}")


def _show_csv_tail(n: int = 10) -> None:
    if not _CSV_FILE.exists():
        print("  No data yet."); return
    with open(_CSV_FILE) as f:
        lines = f.readlines()
    print(f"\n  Last {min(n, len(lines)-1)} entries from {_CSV_FILE}:")
    for line in lines[-n:]:
        print(" ", line.rstrip())


# ── Main menu ─────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 60)
    print("  TRIsecure V2 — Real-Data Pilot Collection")
    print("═" * 60)

    camera, face_auth, pad = _init_hardware()
    db = _load_enrollments()

    if db:
        print(f"\n  Enrolled subjects: {', '.join(sorted(db.keys()))}")
    else:
        print("\n  No subjects enrolled yet.")

    print(f"  CSV log: {_CSV_FILE}")

    while True:
        print("\n  ── Menu ──────────────────────────────────────────")
        print("  [E] Enrol new subject")
        print("  [1] Record GENUINE attempt")
        print("  [2] Record IMPOSTOR attempt")
        print("  [3] Record PRINT ATTACK (hold printed photo to camera)")
        print("  [4] Record REPLAY ATTACK (play video to camera)")
        print("  [M] Show pilot metrics")
        print("  [T] Show last 10 CSV entries")
        print("  [Q] Quit")
        print("  ──────────────────────────────────────────────────")

        choice = input("  Choice: ").strip().upper()

        if choice == "Q":
            break

        elif choice == "E":
            sid = input("  Subject ID (e.g. U01): ").strip()
            if sid:
                _enroll_subject(sid, camera, face_auth, db, n_frames=5)

        elif choice == "1":
            if not db:
                print("  Enrol at least one subject first.")
                continue
            print("  Enrolled:", ", ".join(sorted(db.keys())))
            sid = input("  Subject ID: ").strip()
            if sid in db:
                _run_genuine(sid, camera, face_auth, pad, db)
            else:
                print(f"  {sid} not enrolled.")

        elif choice == "2":
            if len(db) < 1:
                print("  Need at least one enrolled subject as target.")
                continue
            print("  Enrolled targets:", ", ".join(sorted(db.keys())))
            attacker = input("  Attacker ID (can be new): ").strip()
            target   = input("  Target (enrolled) subject ID: ").strip()
            if target in db:
                _run_impostor(attacker, target, camera, face_auth, pad, db)
            else:
                print(f"  {target} not enrolled.")

        elif choice == "3":
            if not db:
                print("  Enrol at least one subject first.")
                continue
            print("  Enrolled:", ", ".join(sorted(db.keys())))
            target = input("  Target subject ID (whose photo): ").strip()
            if target in db:
                _run_attack("PRINT_ATTACK", target, camera, face_auth, pad, db)
            else:
                print(f"  {target} not enrolled.")

        elif choice == "4":
            if not db:
                print("  Enrol at least one subject first.")
                continue
            print("  Enrolled:", ", ".join(sorted(db.keys())))
            target = input("  Target subject ID (whose video): ").strip()
            if target in db:
                _run_attack("REPLAY_ATTACK", target, camera, face_auth, pad, db)
            else:
                print(f"  {target} not enrolled.")

        elif choice == "M":
            _compute_metrics()

        elif choice == "T":
            _show_csv_tail(10)

        else:
            print("  Unknown option.")

    if camera:
        camera.release()
    face_auth.release()
    print("\n  Session ended. Run [M] next time to compute metrics.")
    print("═" * 60)


if __name__ == "__main__":
    main()
