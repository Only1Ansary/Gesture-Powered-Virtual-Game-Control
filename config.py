"""
config.py
---------
Application configuration: loads config.json, discovers executables, and
exposes runtime constants used by the other modules.
"""

import json
import os
import sys

IS_WINDOWS = sys.platform == "win32"
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))

# ── Load config.json ──────────────────────────────────────────────────────────
_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
_CFG: dict = {}
if os.path.isfile(_CONFIG_FILE):
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as _f:
            _CFG = json.load(_f)
    except Exception as _e:
        print(f"[Config] Could not parse config.json: {_e}")
else:
    print(
        "[Config] No config.json found in the project root.\n"
        "         Copy config.json.example → config.json and set your paths.\n"
        "         The app will still run; reacTIVision/game paths may be wrong."
    )


def _find_reactvision() -> str:
    from_cfg = _CFG.get("reactvision_exe", "")
    if from_cfg:
        # Resolve relative paths against the project folder, not the cwd
        resolved = from_cfg if os.path.isabs(from_cfg) else os.path.join(BASE_DIR, from_cfg)
        if os.path.isfile(resolved):
            return os.path.normpath(resolved)
    exe_name = "reacTIVision.exe" if IS_WINDOWS else "reacTIVision"
    for sub in [
        ".",
        "reacTIVision",
        "reacTIVision-1.5.1-win64",
        "reacTIVision-1.5.1-win32",
        "reacTIVision-1.5.1-osx",
        "reacTIVision-1.5.1-linux",
    ]:
        candidate = os.path.normpath(os.path.join(BASE_DIR, sub, exe_name))
        if os.path.isfile(candidate):
            return candidate
    return ""


def _find_game() -> str:
    from_cfg = _CFG.get("game_exe", "")
    if from_cfg:
        # Resolve relative paths against the project folder, not the cwd
        resolved = from_cfg if os.path.isabs(from_cfg) else os.path.join(BASE_DIR, from_cfg)
        return os.path.normpath(resolved)  # keep raw string so the error message is useful
    return ""


REACTVISION_EXE    = _find_reactvision()
GAME_EXE           = _find_game()
TUIO_HOST          = _CFG.get("tuio_host", "0.0.0.0")
TUIO_PORT          = int(_CFG.get("tuio_port", 3333))
# Loopback TCP ports: C# GUI listens; Python sidecars connect. Keep all three distinct.
# Gaze heatmaps use stdout (no TCP today); tcp_gaze_port reserves a slot for a future stream.
TCP_LEVEL_PORT     = int(_CFG.get("tcp_level_port", 12345))
TCP_TOOL_PORT      = int(_CFG.get("tcp_tool_port", 12346))
TCP_GAZE_PORT      = int(_CFG.get("tcp_gaze_port", 12347))
ROTATION_THRESHOLD = float(_CFG.get("rotation_threshold", 0.5))  # rad/s angular velocity

_by_tcp: dict[int, list[str]] = {}
for _tn, _tp in (
    ("tcp_level_port", TCP_LEVEL_PORT),
    ("tcp_tool_port", TCP_TOOL_PORT),
    ("tcp_gaze_port", TCP_GAZE_PORT),
):
    _by_tcp.setdefault(_tp, []).append(_tn)
for _tp, _keys in _by_tcp.items():
    if len(_keys) > 1:
        print(
            f"[Config] WARNING: TCP port {_tp} is used by: {', '.join(_keys)} — "
            "assign a unique port per channel.",
            file=sys.stderr,
        )
# ── Camera layout ─────────────────────────────────────────────────────────────
# Main webcam (non-Iriun) : face-id / gaze / hand  — never simultaneously
# Iriun 1                 : emotion   (in-game)
# Iriun 2                 : YOLO      (in-game)
# Iriun 3                 : reacTIVision (always)
# Iriun 4                 : reserved for future use
#
# *_camera_index values below are fallbacks only when the pick flags are set.
# Actual indices are resolved at runtime from reacTIVision.exe -l output.
# ──────────────────────────────────────────────────────────────────────────────

REACTVISION_CAMERA_INDEX        = int(_CFG.get("reactvision_camera_index", 0))
REACTVISION_CAMERA_NAME_CONTAINS= str(_CFG.get("reactvision_camera_name_contains", "") or "").strip()
REACTVISION_DSHOW_IRIUN_NUMBER  = int(_CFG.get("reactvision_dshow_iriun_number", 3))

GAZE_CAMERA_INDEX               = int(_CFG.get("gaze_camera_index", 0))
GAZE_OPENCV_DSHOW_FIRST         = bool(_CFG.get("gaze_opencv_dshow_first", False))
GAZE_DSHOW_PICK_NON_IRIUN       = bool(_CFG.get("gaze_dshow_pick_non_iriun", True))
GAZE_CAMERA_NAME_CONTAINS       = str(_CFG.get("gaze_camera_name_contains", "") or "").strip()
GAZE_CAPTURE_WIDTH              = max(0, int(_CFG.get("gaze_capture_width", 0)))
GAZE_CAPTURE_HEIGHT             = max(0, int(_CFG.get("gaze_capture_height", 0)))

YOLO_CAMERA_INDEX               = int(_CFG.get("yolo_camera_index", 0))
YOLO_DSHOW_IRIUN_NUMBER         = int(_CFG.get("yolo_dshow_iriun_number", 2))
YOLO_CAMERA_NAME_CONTAINS       = str(_CFG.get("yolo_camera_name_contains", "") or "").strip()
# Legacy key — superceded by yolo_dshow_iriun_number but kept for old configs
YOLO_DSHOW_PICK_FIRST_IRIUN     = bool(_CFG.get("yolo_dshow_pick_first_iriun", False))

EMOTION_CAMERA_INDEX            = int(_CFG.get("emotion_camera_index", 0))
EMOTION_DSHOW_IRIUN_NUMBER      = int(_CFG.get("emotion_dshow_iriun_number", 1))
EMOTION_CAMERA_NAME_CONTAINS    = str(_CFG.get("emotion_camera_name_contains", "") or "").strip()

HAND_TRACKER_CAMERA_INDEX       = int(_CFG.get("hand_tracker_camera_index", 0))
HAND_DSHOW_PICK_NON_IRIUN       = bool(_CFG.get("hand_dshow_pick_non_iriun", True))
HAND_CAMERA_NAME_CONTAINS       = str(_CFG.get("hand_camera_name_contains", "") or "").strip()

FACE_CAMERA_INDEX               = int(_CFG.get("face_camera_index", 0))
FACE_DSHOW_PICK_NON_IRIUN       = bool(_CFG.get("face_dshow_pick_non_iriun", True))
FACE_CAMERA_NAME_CONTAINS       = str(_CFG.get("face_camera_name_contains", "") or "").strip()

# All five roles resolve to distinct physical devices at runtime via pick flags,
# so shared fallback indices (all 0) are expected and not a real conflict.

GAZE_ENABLED                 = bool(_CFG.get("gaze_enabled", False))
GAZE_SAMPLE_INTERVAL_MS      = int(_CFG.get("gaze_sample_interval_ms", 100))
GAZE_MIN_SAMPLES             = int(_CFG.get("gaze_min_samples", 30))
GAZE_SMOOTH_ALPHA            = float(_CFG.get("gaze_smooth_alpha", 0.35))
GAZE_DATA_DIR                = _CFG.get("gaze_data_dir", "gaze_data")
GAZE_HEATMAP_GRID_COLUMNS    = int(_CFG.get("gaze_heatmap_grid_columns", 8))
GAZE_HEATMAP_GRID_ROWS       = int(_CFG.get("gaze_heatmap_grid_rows", 6))
GAZE_LAYOUT_MARGIN_RATIO     = float(_CFG.get("gaze_layout_margin_ratio", 0.08))
GAZE_LAYOUT_MIN_DISTANCE     = float(_CFG.get("gaze_layout_min_distance", 0.22))
# Append timestamped gaze sidecar lines to a file (see gaze_session_cli / gaze_tracker).
GAZE_DEBUG_LOG = bool(_CFG.get("gaze_debug_log", False))
_gaze_log_rel = _CFG.get("gaze_session_log", "gaze_data/gaze_session.log")
GAZE_SESSION_LOG_FILE = (
    _gaze_log_rel
    if os.path.isabs(str(_gaze_log_rel))
    else os.path.join(BASE_DIR, str(_gaze_log_rel))
)
# OpenCV window alongside the WinForms GUI (pupil crosses + overlay text).
GAZE_PREVIEW_WINDOW = bool(_CFG.get("gaze_preview_window", False))
# Selfie-style webcams often mirror horizontally; flip frames before GazeTracking so
# gaze x and adaptive layout.json match the physical screen.
GAZE_MIRROR_HORIZONTAL = bool(_CFG.get("gaze_mirror_horizontal", False))

# ── Admin: Bluetooth + dedicated TUIO marker (no collision with users 0–3) ─────
# Unlock uses admin_bluetooth_name (Windows friendly name). admin_bluetooth_mac may stay in JSON but is not used.
ADMIN_TUIO_MARKER       = int(_CFG.get("admin_tuio_marker", 9))
ADMIN_BLUETOOTH_MAC     = str(_CFG.get("admin_bluetooth_mac", "")).strip()
ADMIN_BLUETOOTH_NAME    = str(_CFG.get("admin_bluetooth_name", "")).strip()
# Legacy: first entry of admin_bluetooth_names if admin_bluetooth_name is empty
_legacy_names = _CFG.get("admin_bluetooth_names", [])
if not ADMIN_BLUETOOTH_NAME and isinstance(_legacy_names, list) and _legacy_names:
    ADMIN_BLUETOOTH_NAME = str(_legacy_names[0]).strip()
ADMIN_BT_SCAN_SECONDS   = int(_CFG.get("admin_bluetooth_scan_seconds", 6))
ADMIN_BT_POLL_SECONDS   = float(_CFG.get("admin_bluetooth_poll_seconds", 3))
ADMIN_BT_TTL_SECONDS    = float(_CFG.get("admin_bluetooth_ttl_seconds", 45))
ADMIN_BLUETOOTH_FORCE   = bool(_CFG.get("admin_bluetooth_force", False))

# ── Circular TUIO menu (marker must differ from users 0–3 and admin) ───────────
MENU_TUIO_MARKER              = int(_CFG.get("menu_tuio_marker", 10))
MENU_MOTION_THRESHOLD           = float(_CFG.get("menu_motion_threshold", 0.04))
MENU_SMOOTH_ALPHA               = float(_CFG.get("menu_smooth_alpha", 0.4))
MENU_VOLUME_STEP                = float(_CFG.get("menu_volume_step", 0.045))
MENU_VOLUME_REPEAT_SECONDS      = float(_CFG.get("menu_volume_repeat_seconds", 0.25))
MENU_ACTION_COOLDOWN_SECONDS    = float(_CFG.get("menu_action_cooldown_seconds", 2.0))
MENU_CURSOR_GAIN                = float(_CFG.get("menu_cursor_gain", 520.0))
