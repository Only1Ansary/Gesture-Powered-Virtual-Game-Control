"""
windows_controls.py
--------------------
Windows-only helpers: master volume (pycaw) and window minimize / focus.

On non-Windows platforms all functions no-op safely.
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"

_VOLUME_INTERFACE = None


def _audio_volume_interface():
    """
    Lazy-init IAudioEndpointVolume for the default playback device.

    Supports both the new pycaw API (>=20251023, AudioDevice.EndpointVolume)
    and the legacy API (AudioDevice.Activate) transparently.
    """
    global _VOLUME_INTERFACE
    if not IS_WINDOWS:
        return None
    if _VOLUME_INTERFACE is not None:
        return _VOLUME_INTERFACE
    try:
        from pycaw.pycaw import AudioUtilities

        dev = AudioUtilities.GetSpeakers()
        if dev is None:
            raise RuntimeError("GetSpeakers() returned None")

        # New pycaw (>=20251023): AudioDevice exposes .EndpointVolume directly.
        if hasattr(dev, "EndpointVolume") and dev.EndpointVolume is not None:
            _VOLUME_INTERFACE = dev.EndpointVolume
            return _VOLUME_INTERFACE

        # Legacy pycaw: use .Activate() + comtypes cast.
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume

        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _VOLUME_INTERFACE = cast(iface, POINTER(IAudioEndpointVolume))
        return _VOLUME_INTERFACE

    except Exception as exc:
        print(f"[windows_controls] Volume init failed: {exc}")
        return None


def volume_step(delta_scalar: float) -> bool:
    """
    Adjust master playback volume by *delta_scalar* (e.g. 0.045 = +4.5%).
    *delta_scalar* may be negative. Returns True if the call succeeded.
    """
    if not IS_WINDOWS:
        return False
    vol = _audio_volume_interface()
    if not vol:
        return False
    try:
        cur = vol.GetMasterVolumeLevelScalar()
        nxt = max(0.0, min(1.0, cur + delta_scalar))
        vol.SetMasterVolumeLevelScalar(nxt, None)
        print(f"[windows_controls] Volume {cur:.0%} -> {nxt:.0%}")
        return True
    except Exception as exc:
        print(f"[windows_controls] volume_step failed: {exc}")
        # Reset cached interface so next call retries init.
        global _VOLUME_INTERFACE
        _VOLUME_INTERFACE = None
        return False


def tk_hwnd(widget) -> int | None:
    """Best-effort HWND for a Tk widget (Windows)."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes

        widget.update_idletasks()
        wid = widget.winfo_id()
        user32 = ctypes.windll.user32
        GA_ROOT = 2
        hwnd = user32.GetAncestor(wid, GA_ROOT)
        return int(hwnd) if hwnd else None
    except Exception:
        return None


def minimize_other_windows(keep_hwnd: int | None) -> None:
    """
    Minimize visible top-level windows except *keep_hwnd*.
    Skips taskbar / desktop shell classes.
    """
    if not IS_WINDOWS or not keep_hwnd:
        return
    try:
        import win32con
        import win32gui
    except ImportError:
        print("[windows_controls] pywin32 required for minimize_other_windows.")
        return

    skip_classes = {"Shell_TrayWnd", "Progman", "WorkerW", "Button"}

    def cb(hwnd, _):
        if hwnd == keep_hwnd:
            return
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
            if cls in skip_classes:
                return
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(cb, None)
    except Exception as exc:
        print(f"[windows_controls] EnumWindows: {exc}")


def find_main_window_hwnd_for_pid(pid: int) -> int | None:
    """
    Largest visible top-level window belonging to *pid* (by client area).
    """
    if not IS_WINDOWS or pid is None or pid <= 0:
        return None
    try:
        import win32gui
    except ImportError:
        return None

    best_hwnd = None
    best_area = 0

    def cb(hwnd, _):
        nonlocal best_hwnd, best_area
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, found = win32gui.GetWindowThreadProcessId(hwnd)
            if found != pid:
                return
            if win32gui.GetParent(hwnd):
                return
            rect = win32gui.GetWindowRect(hwnd)
            w = max(0, rect[2] - rect[0])
            h = max(0, rect[3] - rect[1])
            area = w * h
            if area > best_area:
                best_area = area
                best_hwnd = hwnd
        except Exception:
            pass

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        return None
    return best_hwnd


def minimize_window(hwnd: int | None) -> None:
    if not IS_WINDOWS or not hwnd:
        return
    try:
        import win32con
        import win32gui

        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception as exc:
        print(f"[windows_controls] minimize_window: {exc}")


def window_is_fullscreen_or_maximized(hwnd: int | None) -> bool:
    """True if *hwnd* is maximized or covers ~≥85% of the primary monitor."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        import win32api
        import win32con
        import win32gui

        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            return True
        rect = win32gui.GetWindowRect(hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        sw = win32api.GetSystemMetrics(0)
        sh = win32api.GetSystemMetrics(1)
        return w >= int(sw * 0.85) and h >= int(sh * 0.85)
    except Exception:
        return False


def restore_maximize_and_foreground(hwnd: int | None) -> None:
    """Restore a window, maximize it, and try to focus it (typical “game to front”)."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        import win32con
        import win32gui

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
    except Exception as exc:
        print(f"[windows_controls] restore_maximize_and_foreground: {exc}")


def minimize_tk_root(root) -> None:
    """Iconify the Tk root window."""
    try:
        root.iconify()
    except Exception as exc:
        print(f"[windows_controls] minimize_tk_root: {exc}")


def restore_focus_fullscreen(root) -> None:
    """Restore, raise, fullscreen, and focus the Tk root window."""
    try:
        hwnd = tk_hwnd(root)
        if IS_WINDOWS and hwnd:
            import win32con
            import win32gui

            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
        root.deiconify()
        root.lift()
        root.attributes("-fullscreen", True)
        root.focus_force()
    except Exception as exc:
        print(f"[windows_controls] restore_focus_fullscreen: {exc}")
