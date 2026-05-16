"""
camera_resolve.py
-----------------
Resolve OpenCV CAP_DSHOW camera indices from ``reacTIVision.exe -l`` device order.

Windows DirectShow numbering matches reacTIVision / typical OpenCV CAP_DSHOW
enumeration; it does **not** always match Media Foundation (CAP_MSMF) order.

Camera layout for this project
-------------------------------
  Main webcam (non-Iriun) → face-id / gaze / hand  (never simultaneously)
  Iriun 1                 → emotion
  Iriun 2                 → YOLO
  Iriun 3                 → reacTIVision
  Iriun 4                 → reserved for future use

Public API
----------
  parse_reactivision_camera_list(exe)          -> [(id, name), ...]
  resolve_non_iriun_camera(...)                -> (index, force_dshow, msg)
  resolve_nth_iriun_camera(...)                -> (index, msg)
  resolve_gaze_dshow_camera(...)               -> (index, force_dshow, msg)  [kept for compat]
  resolve_yolo_dshow_camera(...)               -> (index, msg)               [kept for compat]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_likely_audio_device_name(name: str) -> bool:
    """reacTIVision -l can append audio endpoints with the same id pattern."""
    n = name.casefold()
    return "midi mapper" in n or "wavetable synth" in n or "sound mapper (" in n


def parse_reactivision_camera_list(reactvision_exe: str) -> list[tuple[int, str]]:
    """Return [(device_id, friendly_name), ...] from ``reacTIVision.exe -l``."""
    exe = Path(reactvision_exe)
    if not exe.is_file():
        return []
    _cf = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        p = subprocess.run(
            [str(exe), "-l"],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=str(exe.parent),
            creationflags=_cf,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    merged = (p.stdout or "") + "\n" + (p.stderr or "")
    rx = re.compile(r"^\s*(\d+):\s*(.+)$", re.MULTILINE)
    out: list[tuple[int, str]] = []
    for m in rx.finditer(merged):
        try:
            name = m.group(2).strip()
            if _is_likely_audio_device_name(name):
                continue
            out.append((int(m.group(1)), name))
        except ValueError:
            continue
    return out


# ── Generic resolvers (used by camera_manager for all roles) ──────────────────

def resolve_non_iriun_camera(
    *,
    reactvision_exe: str,
    fallback_index: int,
    name_contains: str = "",
    label: str = "Camera",
) -> tuple[int, bool, str]:
    """
    Pick the first DirectShow device whose name does NOT contain 'Iriun'.
    This is the main physical webcam (face-id, gaze, hand all share it).

    Returns ``(opencv_index, force_cap_dshow_only, message)``.
    ``force_cap_dshow_only=True`` means open with CAP_DSHOW only.

    Preference: explicit ``name_contains`` match beats auto non-Iriun pick.
    """
    devices = parse_reactivision_camera_list(reactvision_exe)
    needle = name_contains.strip()

    if needle:
        if not devices:
            return (
                fallback_index, False,
                f"[{label}] name_contains set but no devices found "
                f"(missing reacTIVision.exe?). Using fallback index {fallback_index}.",
            )
        for dev_id, name in devices:
            if needle.casefold() in name.casefold():
                return (
                    dev_id, True,
                    f"[{label}] DirectShow #{dev_id} matched name_contains \"{needle}\" ({name})",
                )
        return (
            fallback_index, False,
            f'[{label}] name_contains "{needle}" matched nothing; '
            f"using fallback index {fallback_index}.",
        )

    if not devices:
        return fallback_index, False, ""

    non_iriun = [d for d in devices if "iriun" not in d[1].casefold()]
    if not non_iriun:
        iriun_hint = "; ".join(f"{did}:{nm}" for did, nm in devices) or "(empty)"
        return (
            fallback_index, False,
            f"[{label}] No non-Iriun device found; "
            f"fallback to index {fallback_index}. Devices: {iriun_hint}",
        )

    dev_id, name = non_iriun[0]
    return (
        dev_id, True,
        f"[{label}] DirectShow #{dev_id} -> main webcam (first non-Iriun: {name})",
    )


def resolve_nth_iriun_camera(
    *,
    reactvision_exe: str,
    fallback_index: int,
    iriun_number: int,
    name_contains: str = "",
    label: str = "Camera",
) -> tuple[int, str]:
    """
    Pick the Nth Iriun device (1-based).

      iriun_number=1  ->  Iriun 1  (emotion)
      iriun_number=2  ->  Iriun 2  (YOLO)
      iriun_number=3  ->  Iriun 3  (reacTIVision)

    Returns ``(opencv_index, message_for_logging)``.

    Preference: explicit ``name_contains`` match beats Nth-position pick.
    """
    devices = parse_reactivision_camera_list(reactvision_exe)
    needle = name_contains.strip()

    if needle:
        if not devices:
            return (
                fallback_index,
                f"[{label}] name_contains set but no devices found "
                f"(missing reacTIVision.exe?). Using fallback index {fallback_index}.",
            )
        for dev_id, name in devices:
            if needle.casefold() in name.casefold():
                return (
                    dev_id,
                    f'[{label}] DirectShow #{dev_id} matched name_contains "{needle}" ({name})',
                )
        return (
            fallback_index,
            f'[{label}] name_contains "{needle}" matched nothing; '
            f"using fallback index {fallback_index}.",
        )

    if not devices:
        return fallback_index, ""

    iriun_devices = [(did, nm) for did, nm in devices if "iriun" in nm.casefold()]
    if not iriun_devices:
        return (
            fallback_index,
            f"[{label}] No Iriun devices found at all; fallback to index {fallback_index}.",
        )

    idx_0based = iriun_number - 1
    if idx_0based >= len(iriun_devices):
        names = ", ".join(f"#{did}:{nm}" for did, nm in iriun_devices)
        return (
            fallback_index,
            f"[{label}] Iriun #{iriun_number} requested but only "
            f"{len(iriun_devices)} Iriun device(s) found ({names}); "
            f"fallback to index {fallback_index}.",
        )

    dev_id, name = iriun_devices[idx_0based]
    return (
        dev_id,
        f"[{label}] DirectShow #{dev_id} -> Iriun #{iriun_number} ({name})",
    )


# ── Legacy functions — kept for backward compatibility ────────────────────────

def resolve_gaze_dshow_camera(
    *,
    reactvision_exe: str,
    fallback_index: int,
    pick_non_iriun: bool,
    name_contains: str,
) -> tuple[int, bool, str]:
    """
    Legacy wrapper — use ``resolve_non_iriun_camera`` directly for new code.
    Returns ``(opencv_index, force_cap_dshow_only, message)``.
    """
    if pick_non_iriun or name_contains.strip():
        return resolve_non_iriun_camera(
            reactvision_exe=reactvision_exe,
            fallback_index=fallback_index,
            name_contains=name_contains,
            label="Gaze",
        )
    return fallback_index, False, ""


def resolve_yolo_dshow_camera(
    *,
    reactvision_exe: str,
    fallback_index: int,
    pick_first_iriun: bool,
    name_contains: str,
) -> tuple[int, str]:
    """
    Legacy wrapper — use ``resolve_nth_iriun_camera(iriun_number=2)`` for new code.
    Returns ``(index, message_for_logging)``.
    """
    if pick_first_iriun or name_contains.strip():
        return resolve_nth_iriun_camera(
            reactvision_exe=reactvision_exe,
            fallback_index=fallback_index,
            iriun_number=1,
            name_contains=name_contains,
            label="YOLO",
        )
    return fallback_index, ""


def sync_reactivision_xml() -> None:
    """Resolve reacTIVision index from config.json and write camera.xml."""
    import json
    import os
    try:
        cfg = json.load(open("config.json"))
        exe = cfg.get("reactvision_exe", "")
        if not exe or not os.path.isfile(exe):
            print("[CameraResolve] reacTIVision exe not found.")
            return
        num = int(cfg.get("reactvision_dshow_iriun_number", 3))
        idx, msg = resolve_nth_iriun_camera(
            reactvision_exe=exe,
            fallback_index=0,
            iriun_number=num,
            name_contains="",
            label="reacTIVision",
        )
        xml_path = os.path.join(os.path.dirname(exe), "camera.xml")
        body = (
            '<?xml version="1.0" encoding="ISO-8859-1" ?>\n'
            '<portvideo>\n'
            f'    <camera id="{idx}">\n'
            '        <capture width="640" height="480" fps="max" compress="true" />\n'
            '        <settings brightness="default" contrast="default" gain="default" shutter="default" exposure="default" sharpness="default" gamma="default" focus="default" />\n'
            '        <frame width="max" height="max" xoff="0" yoff="0" />\n'
            '    </camera>\n'
            '</portvideo>\n'
        )
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"[CameraResolve] Wrote {xml_path} -> device id {idx} ({msg})")
    except Exception as e:
        print(f"[CameraResolve] Failed to sync camera.xml: {e}")


if __name__ == "__main__":
    import sys
    if "--sync-reactivision" in sys.argv:
        sync_reactivision_xml()

