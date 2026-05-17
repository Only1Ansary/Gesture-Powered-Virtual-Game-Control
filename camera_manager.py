"""
camera_manager.py
-----------------
Single source of truth for every camera in the project.

All five OpenCV pipelines (gaze, emotion, yolo, hand, face) and the
reacTIVision DirectShow device are resolved here.  No other module should
call cv2.VideoCapture directly — import open_camera() instead.

Usage
-----
    from camera_manager import open_camera, CameraRole

    cap = open_camera(CameraRole.YOLO)          # returns cv2.VideoCapture
    cap = open_camera(CameraRole.GAZE)          # auto-resolves non-Iriun cam
    cap = open_camera(CameraRole.EMOTION)
    cap = open_camera(CameraRole.HAND)
    cap = open_camera(CameraRole.FACE)

All roles read their index / flags from config.json via config.py and
camera_resolve.py; there is no hard-coded index anywhere in this file.

Log file
--------
Every resolve + open attempt is written to ``camera_manager.log`` in the
project root so you can trace exactly which device each role used.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from enum import Enum, auto

import cv2

# ── File logger (camera_manager.log next to this file) ───────────────────────

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_manager.log")

_log = logging.getLogger("camera_manager")
_log.setLevel(logging.DEBUG)
if not _log.handlers:
    # File handler — full detail
    _fh = logging.FileHandler(_LOG_PATH, mode="a", encoding="utf-8")
    _fh.setLevel(logging.DEBUG)
    _fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                        datefmt="%Y-%m-%d %H:%M:%S"))
    _log.addHandler(_fh)
    # Console handler — INFO and above
    _ch = logging.StreamHandler()
    _ch.setLevel(logging.INFO)
    _ch.setFormatter(logging.Formatter("[CameraManager] %(message)s"))
    _log.addHandler(_ch)

_log.info("=" * 60)
_log.info("camera_manager loaded  (log: %s)", _LOG_PATH)

# ── Config imports (all camera settings live in config.py) ───────────────────
try:
    from config import (
        REACTVISION_EXE,
        # Gaze (main webcam)
        GAZE_CAMERA_INDEX,
        GAZE_OPENCV_DSHOW_FIRST,
        GAZE_DSHOW_PICK_NON_IRIUN,
        GAZE_CAMERA_NAME_CONTAINS,
        # Face (main webcam — same physical cam as gaze/hand)
        FACE_CAMERA_INDEX,
        FACE_DSHOW_PICK_NON_IRIUN,
        FACE_CAMERA_NAME_CONTAINS,
        # Hand (main webcam — same physical cam as gaze/face)
        HAND_TRACKER_CAMERA_INDEX,
        HAND_DSHOW_PICK_NON_IRIUN,
        HAND_CAMERA_NAME_CONTAINS,
        # Emotion → Iriun 1
        EMOTION_CAMERA_INDEX,
        EMOTION_DSHOW_IRIUN_NUMBER,
        EMOTION_CAMERA_NAME_CONTAINS,
        # YOLO → Iriun 2
        YOLO_CAMERA_INDEX,
        YOLO_DSHOW_IRIUN_NUMBER,
        YOLO_CAMERA_NAME_CONTAINS,
    )
    _log.info("config.py loaded OK")
except Exception as _e:
    _log.warning("Could not load config — using fallback indices. %s", _e)
    REACTVISION_EXE             = ""
    GAZE_CAMERA_INDEX           = 0
    GAZE_OPENCV_DSHOW_FIRST     = False
    GAZE_DSHOW_PICK_NON_IRIUN   = True
    GAZE_CAMERA_NAME_CONTAINS   = ""
    FACE_CAMERA_INDEX           = 0
    FACE_DSHOW_PICK_NON_IRIUN   = True
    FACE_CAMERA_NAME_CONTAINS   = ""
    HAND_TRACKER_CAMERA_INDEX   = 0
    HAND_DSHOW_PICK_NON_IRIUN   = True
    HAND_CAMERA_NAME_CONTAINS   = ""
    EMOTION_CAMERA_INDEX        = 0
    EMOTION_DSHOW_IRIUN_NUMBER  = 1
    EMOTION_CAMERA_NAME_CONTAINS= ""
    YOLO_CAMERA_INDEX           = 0
    YOLO_DSHOW_IRIUN_NUMBER     = 2
    YOLO_CAMERA_NAME_CONTAINS   = ""


# ── Camera roles ─────────────────────────────────────────────────────────────

class CameraRole(Enum):
    GAZE    = auto()   # eye-gaze tracker  → main webcam (non-Iriun), profile page only
    EMOTION = auto()   # DeepFace emotion   → Iriun 1, in-game only
    YOLO    = auto()   # YOLOv8 tracker     → Iriun 2, in-game only
    HAND    = auto()   # MediaPipe hands    → main webcam (non-Iriun), game only
    FACE    = auto()   # face enroll/verify → main webcam (non-Iriun), main menu only


# ── Internal: resolve the actual DirectShow/OpenCV index for each role ────────

def _resolve_index(role: CameraRole) -> tuple[int, bool]:
    """
    Return ``(opencv_index, force_dshow_only)``.

    Camera layout
    -------------
    Main webcam (non-Iriun) : FACE / GAZE / HAND  — never simultaneously
    Iriun 1                 : EMOTION   (in-game)
    Iriun 2                 : YOLO      (in-game)
    Iriun 3                 : reacTIVision (C# side only — not resolved here)

    ``force_dshow_only=True`` → caller must open with ``cv2.CAP_DSHOW``.
    """
    from camera_resolve import resolve_non_iriun_camera, resolve_nth_iriun_camera

    _log.debug("Resolving index for role=%s", role.name)

    # ── Main webcam roles (face / gaze / hand) ────────────────────────────────
    if role == CameraRole.FACE:
        if sys.platform == "win32" and (FACE_DSHOW_PICK_NON_IRIUN or FACE_CAMERA_NAME_CONTAINS):
            idx, force_dshow, msg = resolve_non_iriun_camera(
                reactvision_exe=REACTVISION_EXE,
                fallback_index=FACE_CAMERA_INDEX,
                name_contains=FACE_CAMERA_NAME_CONTAINS,
                label="Face",
            )
            _log.info("FACE  → resolved index=%d  force_dshow=%s  (%s)", idx, force_dshow, msg or "ok")
            return idx, force_dshow
        _log.info("FACE  → fallback index=%d  (no pick flag set)", FACE_CAMERA_INDEX)
        return FACE_CAMERA_INDEX, False

    if role == CameraRole.GAZE:
        if sys.platform == "win32" and (GAZE_DSHOW_PICK_NON_IRIUN or GAZE_CAMERA_NAME_CONTAINS):
            idx, force_dshow, msg = resolve_non_iriun_camera(
                reactvision_exe=REACTVISION_EXE,
                fallback_index=GAZE_CAMERA_INDEX,
                name_contains=GAZE_CAMERA_NAME_CONTAINS,
                label="Gaze",
            )
            _log.info("GAZE  → resolved index=%d  force_dshow=%s  (%s)", idx, force_dshow, msg or "ok")
            return idx, force_dshow
        _log.info("GAZE  → fallback index=%d  (no pick flag set)", GAZE_CAMERA_INDEX)
        return GAZE_CAMERA_INDEX, False

    if role == CameraRole.HAND:
        if sys.platform == "win32" and (HAND_DSHOW_PICK_NON_IRIUN or HAND_CAMERA_NAME_CONTAINS):
            idx, force_dshow, msg = resolve_non_iriun_camera(
                reactvision_exe=REACTVISION_EXE,
                fallback_index=HAND_TRACKER_CAMERA_INDEX,
                name_contains=HAND_CAMERA_NAME_CONTAINS,
                label="Hand",
            )
            _log.info("HAND  → resolved index=%d  force_dshow=%s  (%s)", idx, force_dshow, msg or "ok")
            return idx, force_dshow
        _log.info("HAND  → fallback index=%d  (no pick flag set)", HAND_TRACKER_CAMERA_INDEX)
        return HAND_TRACKER_CAMERA_INDEX, False

    # ── Iriun roles (emotion / yolo) ──────────────────────────────────────────
    if role == CameraRole.EMOTION:
        if sys.platform == "win32":
            idx, msg = resolve_nth_iriun_camera(
                reactvision_exe=REACTVISION_EXE,
                fallback_index=EMOTION_CAMERA_INDEX,
                iriun_number=EMOTION_DSHOW_IRIUN_NUMBER,
                name_contains=EMOTION_CAMERA_NAME_CONTAINS,
                label="Emotion",
            )
            _log.info("EMOTION → resolved index=%d  Iriun#%d  (%s)", idx, EMOTION_DSHOW_IRIUN_NUMBER, msg or "ok")
            return idx, True   # Iriun → always use CAP_DSHOW
        _log.info("EMOTION → fallback index=%d  (non-Windows)", EMOTION_CAMERA_INDEX)
        return EMOTION_CAMERA_INDEX, False

    if role == CameraRole.YOLO:
        if sys.platform == "win32":
            idx, msg = resolve_nth_iriun_camera(
                reactvision_exe=REACTVISION_EXE,
                fallback_index=YOLO_CAMERA_INDEX,
                iriun_number=YOLO_DSHOW_IRIUN_NUMBER,
                name_contains=YOLO_CAMERA_NAME_CONTAINS,
                label="YOLO",
            )
            _log.info("YOLO  → resolved index=%d  Iriun#%d  (%s)", idx, YOLO_DSHOW_IRIUN_NUMBER, msg or "ok")
            return idx, True   # Iriun → always use CAP_DSHOW
        _log.info("YOLO  → fallback index=%d  (non-Windows)", YOLO_CAMERA_INDEX)
        return YOLO_CAMERA_INDEX, False

    raise ValueError(f"Unknown CameraRole: {role}")


# ── Public API ────────────────────────────────────────────────────────────────

def get_camera_index(role: CameraRole) -> int:
    """Return only the resolved OpenCV index for *role* (no capture object)."""
    idx, _ = _resolve_index(role)
    return idx


def open_camera(
    role: CameraRole,
    width: int = 0,
    height: int = 0,
    warmup_frames: int = 5,
) -> cv2.VideoCapture:
    """
    Open and return a ``cv2.VideoCapture`` for *role*.

    Every attempt is written to ``camera_manager.log`` with full detail:
    role name, resolved index, backend tried, success/failure, and final
    resolution reported by the driver.

    Raises
    ------
    RuntimeError
        If the camera cannot be opened at all.
    """
    idx, force_dshow = _resolve_index(role)
    label = role.name

    _log.info("--- open_camera(%s) ---  index=%d  force_dshow=%s  request=%dx%d",
              label, idx, force_dshow, width, height)

    # ── Try to open ──────────────────────────────────────────────────────────
    cap: cv2.VideoCapture | None = None

    if sys.platform == "win32":
        if force_dshow:
            if role in (CameraRole.GAZE, CameraRole.HAND, CameraRole.FACE):
                # Main webcam roles: always try MSMF first — real webcams (e.g. ASUS FHD)
                # only stream reliably via MSMF. DSHOW on them reports 0fps / hangs.
                if role == CameraRole.GAZE and GAZE_OPENCV_DSHOW_FIRST:
                    _log.debug("  trying DSHOW then MSMF then default (gaze dshow_first path)")
                    cap = (
                        _try_open(idx, cv2.CAP_DSHOW, label)
                        or _try_open(idx, cv2.CAP_MSMF, label)
                        or _try_open(idx, None, label)
                    )
                else:
                    _log.debug("  trying DSHOW then MSMF then default (main webcam path)")
                    cap = (
                        _try_open(idx, cv2.CAP_DSHOW, label)
                        or _try_open(idx, cv2.CAP_MSMF, label)
                        or _try_open(idx, None, label)
                    )
            else:
                # Iriun roles (EMOTION, YOLO): strict DSHOW — Iriun requires DirectShow
                _log.debug("  trying CAP_DSHOW only (Iriun path)")
                cap = _try_open(idx, cv2.CAP_DSHOW, label)
        else:
            _log.debug("  trying default backend (no force_dshow)")
            cap = _try_open(idx, None, label)
    else:
        _log.debug("  trying default backend (non-Windows)")
        cap = _try_open(idx, None, label)

    if cap is None or not cap.isOpened():
        _log.error("FAILED to open %s camera at index %d  force_dshow=%s", label, idx, force_dshow)
        raise RuntimeError(
            f"[CameraManager] Cannot open {label} camera at index {idx}. "
            "Check that nothing else is using the device and that the index "
            "in config.json is correct."
        )

    # ── Optional resolution ──────────────────────────────────────────────────
    if width > 0 and height > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
        time.sleep(0.1)

    # ── Warmup: discard stale / black frames ─────────────────────────────────
    for _ in range(warmup_frames):
        cap.read()

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps      = cap.get(cv2.CAP_PROP_FPS)
    backend  = cap.getBackendName() if hasattr(cap, "getBackendName") else "?"

    _log.info("SUCCESS  %s  index=%d  backend=%s  resolution=%dx%d  fps=%.1f",
              label, idx, backend, actual_w, actual_h, fps)

    print(f"[CameraManager] {label} opened -> index={idx}  backend={backend}  {actual_w}x{actual_h}  fps={fps:.0f}")
    return cap


# ── Helpers ───────────────────────────────────────────────────────────────────

def _try_open(idx: int, api: int | None, label: str) -> cv2.VideoCapture | None:
    """Attempt one VideoCapture(idx[, api]); return None on failure."""
    api_name = {cv2.CAP_DSHOW: "DSHOW", cv2.CAP_MSMF: "MSMF"}.get(api, "default") if api else "default"
    _log.debug("  _try_open  index=%d  api=%s", idx, api_name)
    try:
        cap = cv2.VideoCapture(idx, api) if api is not None else cv2.VideoCapture(idx)
    except Exception as e:
        _log.debug("  _try_open  EXCEPTION  index=%d  api=%s  err=%s", idx, api_name, e)
        return None
    if cap.isOpened():
        _log.debug("  _try_open  OK  index=%d  api=%s", idx, api_name)
        return cap
    _log.debug("  _try_open  FAILED  index=%d  api=%s", idx, api_name)
    try:
        cap.release()
    except Exception:
        pass
    return None
