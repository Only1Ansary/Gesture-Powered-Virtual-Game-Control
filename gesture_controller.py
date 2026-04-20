from __future__ import annotations
import math
import threading
import time
from typing import Optional
import cv2
import mediapipe as mp

try:
    from config import (
        CAMERA_INDEX,
        VR_LEFT_MARKER,
        VR_RIGHT_MARKER,
    )
except ImportError:
    CAMERA_INDEX    = 0
    VR_LEFT_MARKER  = 0
    VR_RIGHT_MARKER = 1

_TARGET_FPS        = 60
_CAMERA_OPEN_TRIES = 10
_CAMERA_RETRY_S    = 0.3

_GRIP_CLOSE_THRESH = 0.06
_GRIP_OPEN_THRESH  = 0.10


class GestureController:
    """
    Captures webcam frames, runs MediaPipe Hands inference, and pushes
    hand-pose updates into a VRBridge instance at up to TARGET_FPS Hz.
    """

    def __init__(self, bridge):
        self.bridge      = bridge
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._accumulated_angle: dict[int, float] = {}
        self._last_raw_angle:    dict[int, float] = {}
        self._grip_active:       dict[int, bool]  = {}

    # ── public API ────────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="GestureController"
        )
        self._thread.start()
        print("[Gesture] Worker thread started.")

    def stop(self, timeout: float = 3.0):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                print("[Gesture] WARNING: worker thread did not exit cleanly.")
        print("[Gesture] Stopped.")

    # ── worker thread ─────────────────────────────────────────────────────────

    def _loop(self):
        cap = self._open_camera()
        if cap is None:
            print("[Gesture] ERROR: could not open camera — aborting.")
            return

        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[Gesture] Camera {CAMERA_INDEX} opened at {frame_w}×{frame_h}.")

        import os
        model_path = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")
        if not os.path.exists(model_path):
            print(f"[Gesture] ERROR: Model not found at {model_path}")
            return

        BaseOptions = mp.tasks.BaseOptions
        HandLandmarker = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            num_hands=2,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6,
            running_mode=VisionRunningMode.IMAGE
        )
        
        hands = HandLandmarker.create_from_options(options)

        interval = 1.0 / _TARGET_FPS

        try:
            while not self._stop_event.is_set():
                t0 = time.perf_counter()

                ret, frame = cap.read()
                if not ret:
                    print("[Gesture] Frame read failed — attempting recovery.")
                    cap.release()
                    cap = self._open_camera()
                    if cap is None:
                        break
                    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    continue

                # Pass the RAW (unflipped) frame to MediaPipe so its
                # handedness labels are correct without any swap logic.
                rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results  = hands.detect(mp_image)

                if results.hand_landmarks and results.handedness:
                    for hand_landmarks, handedness in zip(
                        results.hand_landmarks,
                        results.handedness,
                    ):
                        fid   = self._handedness_to_fid(handedness)
                        x, y  = self._get_position(hand_landmarks)
                        angle = self._get_stable_angle(
                            hand_landmarks, fid, frame_w, frame_h
                        )
                        grip  = self._update_grip(
                            hand_landmarks, fid, frame_w, frame_h
                        )
                        self.bridge.enqueue(fid, x, y, angle)

                elapsed = time.perf_counter() - t0
                sleep_t = interval - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)

        finally:
            hands.close()
            cap.release()
            print("[Gesture] Camera released.")

    # ── camera ────────────────────────────────────────────────────────────────

    @staticmethod
    def _open_camera() -> Optional[cv2.VideoCapture]:
        for attempt in range(_CAMERA_OPEN_TRIES):
            cap = cv2.VideoCapture(CAMERA_INDEX)
            if cap.isOpened():
                return cap
            cap.release()
            print(
                f"[Gesture] Camera {CAMERA_INDEX} not ready "
                f"(attempt {attempt + 1}/{_CAMERA_OPEN_TRIES}), "
                f"retrying in {_CAMERA_RETRY_S:.1f}s…"
            )
            time.sleep(_CAMERA_RETRY_S)
        return None

    # ── landmark helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _handedness_to_fid(handedness) -> int:
        """
        Map MediaPipe handedness to a VR controller fid.

        The frame is NOT flipped before inference, so MediaPipe's labels
        match the real world directly:
          "Left"  → user's left hand  → LEFT  controller
          "Right" → user's right hand → RIGHT controller
        """
        label = handedness[0].category_name
        return VR_LEFT_MARKER if label == "Left" else VR_RIGHT_MARKER

    @staticmethod
    def _get_position(hand) -> tuple[float, float]:
        """
        Return the corrected (x, y) position using the wrist landmark.

        The raw camera feed is a mirror: x=0 is the user's RIGHT side.
        We invert x here (once, and only here) so that moving right → x
        increases toward 1.0, matching SteamVR's coordinate convention.
        """
        wrist = hand[0]
        x = 1.0 - wrist.x   # correct mirror flip
        y = wrist.y
        return x, y

    def _get_stable_angle(
        self,
        hand,
        fid: int,
        frame_w: int,
        frame_h: int,
    ) -> float:
        """
        Aspect-ratio-corrected, wrap-safe accumulated hand orientation angle.

        dx is negated to stay consistent with the x = 1 - wrist.x correction
        applied in _get_position.
        """
        wrist = hand[0]
        mid   = hand[9]

        dx = -(mid.x - wrist.x) * frame_w   # negated to match corrected x
        dy =  (mid.y - wrist.y) * frame_h
        raw = math.atan2(dy, dx)

        if fid not in self._last_raw_angle:
            self._accumulated_angle[fid] = raw
            self._last_raw_angle[fid]    = raw
            return raw

        prev  = self._last_raw_angle[fid]
        delta = raw - prev
        while delta >  math.pi: delta -= 2 * math.pi
        while delta < -math.pi: delta += 2 * math.pi

        self._accumulated_angle[fid] += delta
        self._last_raw_angle[fid]     = raw
        return self._accumulated_angle[fid]

    def _update_grip(
        self,
        hand,
        fid: int,
        frame_w: int,
        frame_h: int,
    ) -> bool:
        """
        Hysteresis-based pinch/grip detection.
        """
        thumb = hand[4]
        index = hand[8]

        dx   = (thumb.x - index.x) * frame_w
        dy   = (thumb.y - index.y) * frame_h
        dist = math.hypot(dx, dy) / frame_w

        currently_gripping = self._grip_active.get(fid, False)

        if currently_gripping:
            self._grip_active[fid] = dist <= _GRIP_OPEN_THRESH
        else:
            self._grip_active[fid] = dist < _GRIP_CLOSE_THRESH

        return self._grip_active[fid]