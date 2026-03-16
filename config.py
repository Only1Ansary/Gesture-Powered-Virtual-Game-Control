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
        "[Config] No config.json found next to main.py.\n"
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
ROTATION_THRESHOLD = float(_CFG.get("rotation_threshold", 0.5))  # rad/s angular velocity

# ── VR bridge settings ────────────────────────────────────────────────────────
VR_BRIDGE_ENABLED  = bool(_CFG.get("vr_bridge_enabled", False))
VR_PLAY_WIDTH      = float(_CFG.get("vr_play_width", 2.0))          # metres
VR_PLAY_HEIGHT     = float(_CFG.get("vr_play_height", 2.0))         # metres
VR_DEPTH           = float(_CFG.get("vr_depth", 1.0))               # metres (Z into screen)
VR_Y_OFFSET        = float(_CFG.get("vr_y_offset", 1.2))            # metres (base height)
VR_GLOBAL_OFFSET   = list(_CFG.get("vr_global_offset", [0, 0, 0]))  # XYZ camera alignment
VR_GLOBAL_ROTATION = list(_CFG.get("vr_global_rotation", [0, 0, 0]))# Euler rotation
VR_LEFT_MARKER     = int(_CFG.get("vr_left_marker", 0))             # fiducial ID → left saber
VR_RIGHT_MARKER    = int(_CFG.get("vr_right_marker", 1))            # fiducial ID → right saber
VR_UPDATE_RATE     = int(_CFG.get("vr_update_rate", 60))             # Hz
