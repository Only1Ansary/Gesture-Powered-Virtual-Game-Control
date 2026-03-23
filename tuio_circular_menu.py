"""
tuio_circular_menu.py
---------------------
Fullscreen circular TUIO overlay: motion relative to a neutral point maps to
wedges — volume up/down, exit game + GUI, minimize others + GUI, and on the
right side: right-up / right / right-down for game↔GUI window control.

The overlay is destroyed when the menu marker leaves the camera (handled by the app).
"""

from __future__ import annotations

import math
import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable


# Tk pie slices (0° = 3 o'clock, extent CCW). See _classify() for matching sectors.
_WEDGE_SPECS: list[tuple[str, float, float, str, str]] = [
    ("right_down", 292.5, 45, "#2a3555", "#7eb8ff"),
    ("right", 337.5, 45, "#1a2a4a", "#5b8cff"),
    ("right_up", 22.5, 45, "#2a3d5a", "#6ec0ff"),
    ("up", 67.5, 45, "#1a3d2e", "#2ee59d"),
    ("left", 112.5, 135, "#3d1a2a", "#ff5b8c"),
    ("down", 247.5, 45, "#3d2a1a", "#ffb020"),
]


class CircularMenuController:
    """
    Manages a Toplevel circular menu and TUIO motion → actions.

    TUIO coordinates are assumed normalized ~[0, 1].  On first motion after show,
    neutral (x0, y0) is captured.  Displacement dy < 0 is “up” on camera when
    y grows downward.  Sectors use atan2(-dy, dx) in degrees (0 = east/right).
    """

    def __init__(
        self,
        master: tk.Tk,
        *,
        motion_threshold: float = 0.04,
        smooth_alpha: float = 0.4,
        volume_repeat_s: float = 0.25,
        action_cooldown_s: float = 2.2,
        cursor_gain: float = 520.0,
        on_volume_up: Callable[[], None] | None = None,
        on_volume_down: Callable[[], None] | None = None,
        on_action_left: Callable[[], None] | None = None,
        on_action_right: Callable[[], None] | None = None,
        on_action_right_up: Callable[[], None] | None = None,
        on_action_right_down: Callable[[], None] | None = None,
    ):
        self._master = master
        self._th = motion_threshold
        self._alpha = min(0.95, max(0.05, smooth_alpha))
        self._vol_repeat = volume_repeat_s
        self._act_cd = action_cooldown_s
        self._cursor_gain = cursor_gain
        self._on_vol_up = on_volume_up
        self._on_vol_down = on_volume_down
        self._on_left = on_action_left
        self._on_right = on_action_right
        self._on_right_up = on_action_right_up
        self._on_right_down = on_action_right_down

        self._top: tk.Toplevel | None = None
        self._cv: tk.Canvas | None = None
        self._neutral: tuple[float, float] | None = None
        self._sx: float | None = None
        self._sy: float | None = None
        self._last_sector: str = "center"
        self._last_vol_time: float = 0.0
        self._last_left_time: float = 0.0
        self._last_right_time: float = 0.0
        self._last_right_up_time: float = 0.0
        self._last_right_down_time: float = 0.0

        self._cx = 0
        self._cy = 0
        self._R = 200
        self._wedge_items: dict[str, int] = {}
        self._cursor_dot: int | None = None
        self._cursor_line: int | None = None

    @property
    def is_active(self) -> bool:
        return self._top is not None and self._top.winfo_exists()

    def show(self) -> None:
        if self.is_active:
            return
        self._neutral = None
        self._sx = self._sy = None
        self._last_sector = "center"
        self._last_vol_time = 0.0

        top = tk.Toplevel(self._master)
        self._top = top
        top.title("TUIO radial menu")
        top.configure(bg="#07070f")
        top.attributes("-fullscreen", True)
        top.attributes("-topmost", True)
        top.protocol("WM_DELETE_WINDOW", lambda: None)

        sw = top.winfo_screenwidth()
        sh = top.winfo_screenheight()
        self._cx, self._cy = sw // 2, sh // 2
        self._R = int(min(sw, sh) * 0.28)

        cv = tk.Canvas(
            top,
            width=sw,
            height=sh,
            bg="#07070f",
            highlightthickness=0,
        )
        cv.pack(fill="both", expand=True)
        self._cv = cv

        cv.create_oval(
            self._cx - self._R - 40,
            self._cy - self._R - 40,
            self._cx + self._R + 40,
            self._cy + self._R + 40,
            outline="#2a2a44",
            width=3,
        )

        for name, start, extent, dim, _bright in _WEDGE_SPECS:
            aid = cv.create_arc(
                self._cx - self._R,
                self._cy - self._R,
                self._cx + self._R,
                self._cy + self._R,
                start=start,
                extent=extent,
                fill=dim,
                outline="#444466",
                width=2,
                style=tk.PIESLICE,
                tags=("wedge", name),
            )
            self._wedge_items[name] = aid

        fz = max(12, min(20, self._R // 11))
        font = tkfont.Font(family="Bahnschrift", size=fz, weight="bold")
        small = tkfont.Font(family="Bahnschrift", size=max(10, fz - 2))

        # Label positions (approximate bisectors)
        labels: list[tuple[int, int, str, tkfont.Font]] = [
            (int(self._cx + self._R * 0.62), int(self._cy + self._R * 0.62),
             "GAME →\nGUI\n(fullscr)", small),
            (int(self._cx + self._R * 0.85), int(self._cy),
             "MIN OTHERS\n+ GUI", font),
            (int(self._cx + self._R * 0.62), int(self._cy - self._R * 0.62),
             "GUI\n(full)\nif game FS", small),
            (int(self._cx), int(self._cy - self._R - 48), "VOL +", font),
            (int(self._cx - self._R - 52), int(self._cy), "EXIT GAME\n+ GUI", font),
            (int(self._cx), int(self._cy + self._R + 48), "VOL −", font),
        ]
        for lx, ly, text, fnt in labels:
            cv.create_text(lx, ly, text=text, fill="#cccccc", font=fnt, justify="center")

        self._cursor_line = cv.create_line(
            self._cx, self._cy, self._cx, self._cy, fill="#ffffff", width=3
        )
        self._cursor_dot = cv.create_oval(
            self._cx - 14,
            self._cy - 14,
            self._cx + 14,
            self._cy + 14,
            fill="#ffffff",
            outline="#00fff7",
            width=3,
        )

        cv.create_text(
            self._cx,
            sh - 60,
            text="Remove the menu TUIO marker from the camera to close this menu.",
            fill="#666688",
            font=tkfont.Font(family="Consolas", size=12),
        )

        top.lift()
        top.focus_force()

    def hide(self) -> None:
        if self._top:
            try:
                self._top.destroy()
            except tk.TclError:
                pass
        self._top = None
        self._cv = None
        self._wedge_items.clear()
        self._cursor_dot = self._cursor_line = None
        self._neutral = None
        self._sx = self._sy = None

    def feed_tuio(self, x: float, y: float) -> None:
        if not self.is_active or self._cv is None:
            return

        if self._neutral is None:
            self._neutral = (float(x), float(y))
            self._sx, self._sy = float(x), float(y)
            return

        x0, y0 = self._neutral
        a = self._alpha
        self._sx = a * self._sx + (1.0 - a) * float(x)  # type: ignore[operator]
        self._sy = a * self._sy + (1.0 - a) * float(y)  # type: ignore[operator]
        dx = self._sx - x0  # type: ignore[operator]
        dy = self._sy - y0  # type: ignore[operator]

        sector = self._classify(dx, dy)
        self._update_visual(dx, dy, sector)
        self._fire_actions(sector)

    def _classify(self, dx: float, dy: float) -> str:
        t = self._th
        if abs(dx) < t * 0.35 and abs(dy) < t * 0.35:
            return "center"
        ang = math.degrees(math.atan2(-dy, dx))
        while ang <= -180:
            ang += 360
        while ang > 180:
            ang -= 360
        if -22.5 < ang <= 22.5:
            return "right"
        if 22.5 < ang <= 67.5:
            return "right_up"
        if 67.5 < ang <= 112.5:
            return "up"
        if 112.5 < ang <= 180 or -180 <= ang < -112.5:
            return "left"
        if -112.5 <= ang <= -67.5:
            return "down"
        if -67.5 < ang <= -22.5:
            return "right_down"
        return "center"

    def _update_visual(self, dx: float, dy: float, sector: str) -> None:
        cv = self._cv
        if cv is None:
            return

        bright_map = {s[0]: s[4] for s in _WEDGE_SPECS}
        dim_map = {s[0]: s[3] for s in _WEDGE_SPECS}

        for name, wid in self._wedge_items.items():
            cv.itemconfig(
                wid,
                fill=bright_map[name] if sector == name else dim_map[name],
            )

        px = dx * self._cursor_gain
        py = dy * self._cursor_gain
        dist = math.hypot(px, py)
        if dist > self._R - 20 and dist > 1e-6:
            scale = (self._R - 20) / dist
            px *= scale
            py *= scale
        cx2 = self._cx + px
        cy2 = self._cy + py

        if self._cursor_line:
            cv.coords(self._cursor_line, self._cx, self._cy, cx2, cy2)
        if self._cursor_dot:
            cv.coords(
                self._cursor_dot,
                cx2 - 14,
                cy2 - 14,
                cx2 + 14,
                cy2 + 14,
            )

    def _fire_edge_action(
        self,
        sector: str,
        tag: str,
        last_time_attr: str,
        callback: Callable[[], None] | None,
    ) -> None:
        now = time.monotonic()
        if sector != tag:
            return
        if self._last_sector == tag:
            return
        last = getattr(self, last_time_attr)
        if now - last < self._act_cd:
            return
        setattr(self, last_time_attr, now)
        if callback:
            callback()

    def _fire_actions(self, sector: str) -> None:
        now = time.monotonic()

        if sector in ("up", "down"):
            if now - self._last_vol_time >= self._vol_repeat:
                self._last_vol_time = now
                if sector == "up" and self._on_vol_up:
                    self._on_vol_up()
                elif sector == "down" and self._on_vol_down:
                    self._on_vol_down()

        self._fire_edge_action(sector, "left", "_last_left_time", self._on_left)
        self._fire_edge_action(sector, "right", "_last_right_time", self._on_right)
        self._fire_edge_action(sector, "right_up", "_last_right_up_time", self._on_right_up)
        self._fire_edge_action(
            sector, "right_down", "_last_right_down_time", self._on_right_down
        )

        self._last_sector = sector
