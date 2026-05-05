"""Shared face template utilities used by all use-cases."""

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

FACE_MODELS_DIR = Path("data/face_models")
FACE_MODELS_DIR.mkdir(parents=True, exist_ok=True)

_DUPLICATE_FACE_THRESHOLD = 0.68


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.flatten().astype(np.float32), b.flatten().astype(np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(np.dot(a / na, b / nb), -1.0, 1.0))


def voter_model_path(voter_id) -> Path:
    return FACE_MODELS_DIR / f"{voter_id}.npz"


def legacy_model_path(name: str) -> Path:
    return FACE_MODELS_DIR / f"{name.lower().replace(' ', '_')}.npy"


def save_templates(voter_id, embedding: np.ndarray, append: bool = True) -> Path:
    path = voter_model_path(voter_id)
    new_template = embedding.flatten().astype(np.float32).reshape(1, -1)

    if append and path.exists():
        try:
            existing = np.load(str(path))["templates"]
            if existing.ndim == 1:
                existing = existing.reshape(1, -1)
            if existing.shape[1] == new_template.shape[1]:
                templates = np.vstack([existing, new_template])
            else:
                logger.warning("Dimension mismatch in templates. Replacing.")
                templates = new_template
        except Exception as e:
            logger.warning(f"Failed to load existing templates, starting fresh: {e}")
            templates = new_template
    else:
        templates = new_template

    np.savez(str(path), templates=templates)
    return path


def load_templates(voter_id, voter_name: str = None) -> Optional[np.ndarray]:
    path = voter_model_path(voter_id)
    if path.exists():
        try:
            data = np.load(str(path))
            templates = data["templates"].astype(np.float32)
            if templates.ndim == 1:
                templates = templates.reshape(1, -1)
            return templates
        except Exception as e:
            logger.error(f"Corrupt template file {path}: {e}")

    if voter_name:
        legacy = legacy_model_path(voter_name)
        if legacy.exists():
            try:
                emb = np.load(str(legacy)).astype(np.float32)
                return emb.reshape(1, -1) if emb.ndim == 1 else emb
            except Exception as e:
                logger.error(f"Corrupt legacy model {legacy}: {e}")

    return None


def count_templates(voter_id) -> int:
    path = voter_model_path(voter_id)
    if not path.exists():
        return 0
    try:
        data = np.load(str(path))
        t = data["templates"]
        return t.shape[0] if t.ndim == 2 else 1
    except Exception:
        return 0


def match_against_templates(live_embedding: np.ndarray, templates: np.ndarray) -> float:
    if templates is None or len(templates) == 0:
        return -1.0
    best = -1.0
    for t in templates:
        sim = cosine_similarity(live_embedding, t)
        if sim > best:
            best = sim
    return best


def check_face_uniqueness(new_embedding, voter_repo, exclude_voter_id=None,
                           threshold: float = _DUPLICATE_FACE_THRESHOLD):
    best_name = None
    best_sim = -1.0

    for voter in voter_repo.find_all():
        if exclude_voter_id and str(voter.id) == str(exclude_voter_id):
            continue
        templates = load_templates(voter.id, voter.name)
        if templates is None or len(templates) == 0:
            continue
        sim = match_against_templates(new_embedding, templates)
        if sim > best_sim:
            best_sim = sim
            best_name = voter.name
        if best_sim >= threshold:
            break

    return best_sim >= threshold, best_name, best_sim


def init_camera_and_auth(device: int = 0):
    from hardware.camera.face_auth import FaceCamera, FaceAuthenticator
    camera = FaceCamera(device=device, width=320, height=240, fps=15)
    auth = FaceAuthenticator()
    camera.initialize()
    auth.initialize()
    return camera, auth


def capture_face_embedding(camera, authenticator, num_samples: int = 3,
                            prompt: str = "Capturing face",
                            headless: bool = False) -> Optional[np.ndarray]:
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not installed.")
        return None

    COOLDOWN = 2.0
    embeddings = []
    last_capture = 0.0
    show_gui = not headless

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
                                    (140, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
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
