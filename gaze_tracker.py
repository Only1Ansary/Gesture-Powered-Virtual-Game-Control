"""
gaze_tracker.py
---------------
Runtime wrapper around antoinelame/GazeTracking.

The tracker uses a dedicated camera and records normalized screen gaze points.
It fails closed: if dlib/GazeTracking/camera setup is unavailable, the app keeps
running with the existing TUIO controls.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import queue
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class GazeSample:
    x: float
    y: float
    t: float


class GazeSessionManager:
    """Starts/stops per-user gaze sampling on a background thread."""

    def __init__(
        self,
        *,
        enabled: bool,
        camera_index: int,
        sample_interval_ms: int,
        smooth_alpha: float,
        on_status: Callable[[str], None] | None = None,
        on_machine_line: Callable[[str], None] | None = None,
        machine_status: bool = False,
        opencv_dshow_first: bool = False,
        force_opencv_dshow_only: bool = False,
        capture_width: int = 0,
        capture_height: int = 0,
        preview_window: bool = False,
        mirror_horizontal: bool = False,
    ):
        self.enabled = enabled
        self.camera_index = camera_index
        self.sample_interval_s = max(0.03, sample_interval_ms / 1000.0)
        self.smooth_alpha = min(0.95, max(0.0, smooth_alpha))
        self.on_status = on_status
        self.on_machine_line = on_machine_line
        self.machine_status = machine_status
        self._opencv_dshow_first = bool(opencv_dshow_first)
        self._force_opencv_dshow_only = bool(force_opencv_dshow_only)
        self._capture_w = max(0, int(capture_width))
        self._capture_h = max(0, int(capture_height))
        self._preview_window = bool(preview_window)
        self._mirror_horizontal = bool(mirror_horizontal)

        self.active_user_id: int | None = None
        self.started_at: float | None = None
        self.samples: list[dict[str, float]] = []

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._available = True
        self._sx: float | None = None
        self._sy: float | None = None
        self._preview_pipe_proc: subprocess.Popen | None = None
        self._preview_queue: queue.Queue[bytes] | None = None
        self._preview_sender_stop = threading.Event()
        self._preview_sender_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, user_id: int) -> None:
        if not self.enabled:
            return
        if self.is_running and self.active_user_id == user_id:
            return
        self.stop()
        if not self._available:
            return

        with self._lock:
            self.active_user_id = user_id
            self.started_at = time.time()
            self.samples = []
            self._sx = None
            self._sy = None

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"GazeTrackerUser{user_id}",
            daemon=True,
        )
        self._thread.start()
        self._emit(f"[Gaze] Started session for user {user_id}.")

    def stop(self) -> tuple[int | None, float | None, float, list[dict[str, float]]]:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.5)

        with self._lock:
            user_id = self.active_user_id
            started_at = self.started_at
            samples = list(self.samples)
            self.active_user_id = None
            self.started_at = None
            self.samples = []
            self._sx = None
            self._sy = None

        self._thread = None
        ended_at = time.time()
        if user_id is not None:
            self._emit(f"[Gaze] Stopped session for user {user_id} ({len(samples)} samples).")
        return user_id, started_at, ended_at, samples

    def _capture_loop(self) -> None:
        cap = None
        try:
            import cv2
            from gaze_tracking import GazeTracking

            gaze = GazeTracking()
            cap = self._open_video_capture()
            if cap is None:
                self._machine("FAIL", "camera_open")
                print(
                    f"\nCRITICAL ERROR: Camera {self.camera_index} failed to open or pass warmup!\n",
                    flush=True,
                )
                self._emit(
                    f"[Gaze] Camera index {self.camera_index} could not be opened "
                    f"or did not deliver frames (try another index, close other apps using "
                    f"the webcam, and allow Python in Windows camera privacy settings)."
                )
                return

            self._machine("CAMERA_OK")
            if self._preview_window:
                self._start_preview_pipe_viewer()
                if self._preview_pipe_proc is not None:
                    self._emit(
                        "[Gaze] External OpenCV preview running (separate process from sidecar/GUI)."
                    )
                else:
                    self._emit("[Gaze] External preview unavailable; recording continues without it.")
            if self._mirror_horizontal:
                self._emit(
                    "[Gaze] gaze_mirror_horizontal on — frames flipped before tracking to match screen left/right."
                )
            _no_pupil_hint_sent = False
            _frames_without_pupil = 0
            _pupils_status_last = 0.0

            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None or getattr(frame, "size", 0) <= 0:
                    time.sleep(self.sample_interval_s)
                    continue

                # VideoCapture often reuses one buffer; GazeTracking keeps self.frame = frame.
                # Without a copy, the next read() overwrites pixels while dlib state still
                # reflects the previous frame — pupils rarely lock and GAZE_STATUS PUPILS never fires.
                frame = np.ascontiguousarray(np.copy(frame))
                if self._mirror_horizontal:
                    frame = np.ascontiguousarray(cv2.flip(frame, 1))
                gaze.refresh(frame)
                if gaze.pupils_located:
                    _frames_without_pupil = 0
                    # UI "green" needs recent status lines; SAMPLES only fires when ratios exist.
                    # PUPILS heartbeat so the health dot turns green once the landmarks lock.
                    if self.machine_status:
                        now_t = time.time()
                        if now_t - _pupils_status_last >= 0.35:
                            self._machine("PUPILS")
                            _pupils_status_last = now_t
                    sample = self._sample_from_gaze(gaze)
                    if sample is not None:
                        with self._lock:
                            self.samples.append(asdict(sample))
                            sample_count = len(self.samples)
                        if self.machine_status and (
                            sample_count == 1 or sample_count % 5 == 0
                        ):
                            self._machine("SAMPLES", str(sample_count))
                else:
                    _frames_without_pupil += 1
                    if (
                        self.machine_status
                        and not _no_pupil_hint_sent
                        and _frames_without_pupil >= 45
                    ):
                        self._machine(
                            "HINT",
                            "no_pupils_face_the_camera_check_lighting",
                        )
                        _no_pupil_hint_sent = True

                if self._preview_window:
                    self._show_preview_frame(gaze)

                time.sleep(self.sample_interval_s)
        except Exception as exc:
            self._machine("FAIL", "capture")
            self._emit(f"[Gaze] Capture stopped after error: {exc}")
        finally:
            self._close_preview_pipe_viewer()
            if cap is not None:
                cap.release()

    def _viewer_interpreter(self) -> str:
        exe = Path(sys.executable)
        if sys.platform == "win32" and exe.name.lower() in ("python.exe", "python3.exe"):
            pw = exe.with_name("pythonw.exe")
            if pw.is_file():
                return str(pw)
        return sys.executable

    def _start_preview_pipe_viewer(self) -> None:
        script = Path(__file__).resolve().parent / "gaze_preview_pipe_viewer.py"
        if not script.is_file():
            self._emit("[Gaze] gaze_preview_pipe_viewer.py not found.")
            return
        uid = self.active_user_id
        title = "Gaze live view" if uid is None else f"Gaze live view — user {uid}"
        try:
            self._preview_pipe_proc = subprocess.Popen(
                [self._viewer_interpreter(), str(script), title],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._preview_pipe_proc = None
            self._emit(f"[Gaze] External preview process failed to start: {exc}")
            return

        self._preview_sender_stop.clear()
        self._preview_queue = queue.Queue(maxsize=2)
        self._preview_sender_thread = threading.Thread(
            target=self._preview_sender_loop,
            name="GazePreviewPipeSend",
            daemon=True,
        )
        self._preview_sender_thread.start()

    def _preview_sender_loop(self) -> None:
        """Drain JPEG packets to the viewer so the capture thread never blocks on a full pipe."""
        while not self._preview_sender_stop.is_set():
            proc = self._preview_pipe_proc
            if proc is None or proc.poll() is not None:
                break
            q = self._preview_queue
            if q is None:
                break
            try:
                packet = q.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                stdin = proc.stdin
                if stdin is None:
                    break
                stdin.write(packet)
                stdin.flush()
            except (BrokenPipeError, OSError):
                break

    def _close_preview_pipe_viewer(self) -> None:
        self._preview_sender_stop.set()
        sender = self._preview_sender_thread
        self._preview_sender_thread = None
        self._preview_queue = None
        if sender is not None and sender.is_alive():
            sender.join(timeout=1.8)

        proc = self._preview_pipe_proc
        self._preview_pipe_proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=2.5)
        except subprocess.TimeoutExpired:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass

    def _show_preview_frame(self, gaze) -> None:
        """Enqueue one annotated JPEG for the external viewer (non-blocking for capture)."""
        import cv2

        if self._preview_pipe_proc is None or self._preview_queue is None:
            return
        if self._preview_pipe_proc.poll() is not None:
            return

        vis = gaze.annotated_frame()
        if gaze.pupils_located:
            try:
                xl, yl = gaze.pupil_left_coords()
                xr, yr = gaze.pupil_right_coords()
                hr = gaze.horizontal_ratio()
                vr = gaze.vertical_ratio()
                line1 = f"L ({xl:.0f},{yl:.0f})  R ({xr:.0f},{yr:.0f})"
                line2 = f"ratios  h={hr:.2f}  v={vr:.2f}"
                color = (0, 255, 0)
            except Exception:
                line1 = "pupils OK"
                line2 = ""
                color = (0, 255, 0)
        else:
            line1 = "no face / pupils"
            line2 = ""
            color = (0, 165, 255)
        cv2.putText(
            vis,
            line1,
            (10, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            color,
            2,
            cv2.LINE_AA,
        )
        if line2:
            cv2.putText(
                vis,
                line2,
                (10, 52),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                color,
                2,
                cv2.LINE_AA,
            )
        ok, buf = cv2.imencode(
            ".jpg", vis, [int(cv2.IMWRITE_JPEG_QUALITY), 82]
        )
        if not ok or buf is None:
            return
        payload = buf.tobytes()
        packet = struct.pack(">I", len(payload)) + payload
        q = self._preview_queue
        if q is None:
            return
        try:
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
            q.put_nowait(packet)
        except queue.Full:
            try:
                q.get_nowait()
                q.put_nowait(packet)
            except (queue.Empty, queue.Full):
                pass

    def _warmup_read(self, cap, *, consecutive: int = 3, max_tries: int = 90) -> bool:
        """Require several consecutive good frames before declaring the camera ready.

        A single failed read is tolerated; only a full streak is accepted.
        Each read is wrapped in try/except so a corrupted frame (e.g. after a
        failed MSMF stream negotiation) cannot abort the probe loop.
        """
        streak = 0
        for _ in range(max_tries):
            try:
                ok, frame = cap.read()
                if ok and frame is not None and getattr(frame, "size", 0) > 0:
                    streak += 1
                    if streak >= consecutive:
                        return True
                else:
                    streak = 0
            except Exception:
                streak = 0
            time.sleep(0.03)
        return False

    def _apply_capture_extras(self, cap) -> None:
        import cv2

        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        time.sleep(0.05)
        try:
            if hasattr(cv2, "CAP_PROP_HW_ACCELERATION") and hasattr(
                cv2, "VIDEO_ACCELERATION_NONE"
            ):
                cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE)
        except Exception:
            pass

    def _try_preferred_resolution(self, cap) -> bool:
        """After a working stream, optionally set W×H; return False if frames break."""
        if self._capture_w <= 0 or self._capture_h <= 0:
            return True
        import cv2

        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._capture_w))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._capture_h))
        except Exception:
            return False
        time.sleep(0.2)
        return self._warmup_read(cap, consecutive=2, max_tries=50)

    def _open_capture_backend(
        self,
        idx: int,
        label: str,
        api: int | None,
    ):
        """Try one backend; optionally retry at native resolution if requested size fails."""
        import cv2

        def _open() -> object | None:
            cap_local = (
                cv2.VideoCapture(idx, api)
                if api is not None
                else cv2.VideoCapture(idx)
            )
            if not cap_local.isOpened():
                try:
                    cap_local.release()
                except Exception:
                    pass
                return None
            time.sleep(0.45)
            self._apply_capture_extras(cap_local)
            if not self._warmup_read(cap_local):
                try:
                    cap_local.release()
                except Exception:
                    pass
                return None
            return cap_local

        cap = _open()
        if cap is None:
            return None

        if self._capture_w > 0 and self._capture_h > 0:
            if not self._try_preferred_resolution(cap):
                self._emit(
                    "[Gaze] gaze_capture_width/height not supported here; "
                    "using native resolution on this backend."
                )
                try:
                    cap.release()
                except Exception:
                    pass
                cap = _open()
                if cap is None:
                    return None

        aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._emit(
            f"[Gaze] Opened camera index {idx} ({label}) at {aw}×{ah}, frames OK."
        )
        return cap

    def _open_video_capture(self):
        """Open ``gaze_camera_index`` using the configured backend order.

        Uses native resolution by default — forcing HD breaks many laptop and virtual cameras.
        Set ``gaze_capture_width`` / ``gaze_capture_height`` in config only if the device supports it.
        """
        import cv2

        idx = self.camera_index
        if sys.platform == "win32":
            if self._force_opencv_dshow_only:
                import cv2

                cap = self._open_capture_backend(idx, "CAP_DSHOW", cv2.CAP_DSHOW)
                if cap is not None:
                    return cap
                self._emit(
                    f"[Gaze] force CAP_DSHOW only index {idx} failed (see gaze_dshow_pick_non_iriun / gaze_camera_name_contains)."
                )
                return None
            if self._opencv_dshow_first:
                api_order: list[tuple[str, int | None]] = [
                    ("CAP_DSHOW", cv2.CAP_DSHOW),
                    ("CAP_MSMF", cv2.CAP_MSMF),
                    ("default", None),
                ]
            else:
                api_order = [
                    ("CAP_MSMF", cv2.CAP_MSMF),
                    ("CAP_DSHOW", cv2.CAP_DSHOW),
                    ("default", None),
                ]
            for label, api in api_order:
                cap = self._open_capture_backend(idx, label, api)
                if cap is not None:
                    return cap
            return None

        cap = self._open_capture_backend(idx, "default", None)
        return cap

    def _sample_from_gaze(self, gaze) -> GazeSample | None:
        h_ratio = gaze.horizontal_ratio()
        v_ratio = gaze.vertical_ratio()
        if h_ratio is None or v_ratio is None:
            return None

        # GazeTracking defines horizontal 0=right and 1=left; UI x is 0=left.
        raw_x = 1.0 - float(h_ratio)
        raw_y = float(v_ratio)
        raw_x = max(0.0, min(1.0, raw_x))
        raw_y = max(0.0, min(1.0, raw_y))

        if self._sx is None or self._sy is None:
            self._sx, self._sy = raw_x, raw_y
        else:
            alpha = self.smooth_alpha
            self._sx = alpha * self._sx + (1.0 - alpha) * raw_x
            self._sy = alpha * self._sy + (1.0 - alpha) * raw_y

        return GazeSample(x=self._sx, y=self._sy, t=time.time())

    def _emit(self, message: str) -> None:
        if self.on_status is not None:
            self.on_status(message)
        else:
            print(message, flush=True)

    def _machine(self, kind: str, detail: str = "") -> None:
        if not self.machine_status:
            return
        line = (
            f"GAZE_STATUS {kind} {detail}"
            if detail
            else f"GAZE_STATUS {kind}"
        )
        if self.on_machine_line is not None:
            self.on_machine_line(line)
        else:
            print(line, flush=True)
