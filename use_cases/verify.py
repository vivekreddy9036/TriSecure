"""Verify face use-case: live webcam identification (no vote)."""

import logging
import time

logger = logging.getLogger(__name__)


class VerifyFaceUseCase:

    def __init__(self, voter_repo, face_threshold: float = 0.55,
                 camera_device: int = 0, headless: bool = False):
        self._voter_repo = voter_repo
        self._threshold = face_threshold
        self._device = camera_device
        self._headless = headless

    def execute(self) -> None:
        from use_cases._face_helpers import (
            load_templates, match_against_templates, init_camera_and_auth,
        )

        models = {}
        for v in self._voter_repo.find_all():
            templates = load_templates(v.id, v.name)
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

        camera, auth = init_camera_and_auth(self._device)
        COOLDOWN = 1.5
        last_capture = 0.0
        last_name = "Scanning…"
        last_sim = 0.0
        last_match = False
        last_loc = None

        window = "TRIsecure — Face Identification"
        show_gui = not self._headless
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
                        best_name, best_sim = "Unknown", -1.0
                        e = result.embedding
                        for vname, templates in models.items():
                            sim = match_against_templates(e, templates)
                            if sim > best_sim:
                                best_sim, best_name = sim, vname
                        is_match = best_sim >= self._threshold
                        last_name = best_name if is_match else "Unknown"
                        last_sim = best_sim
                        last_match = is_match
                        last_loc = detection.face_location
                        last_capture = now

                        status = "MATCH" if is_match else "NO MATCH"
                        logger.info(f"Identity: {last_name} | Similarity: {best_sim*100:.1f}% | {status}")

                if show_gui and display is not None:
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
                    break
        finally:
            if show_gui:
                cv2.destroyWindow(window)
            camera.release()
            auth.release()
