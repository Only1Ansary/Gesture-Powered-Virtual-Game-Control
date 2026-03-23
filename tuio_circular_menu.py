"""
tuio_circular_menu.py
---------------------
Fullscreen circular TUIO overlay: pointer direction from the **hub** maps to
wedges — volume up/down, exit game + GUI, minimize others + GUI, and on the
right side: right-up / right / right-down for game↔GUI window control.

TUIO uses normalized coords ~[0,1]; the hub is **(0.5, 0.5)** (camera center).
Mouse / touchscreen: **tap** a wedge to run its action once; motion only highlights.
TUIO: moving the marker **into** a wedge triggers once (leave and re-enter to repeat).

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

    TUIO: smoothed (x, y) with hub **(0.5, 0.5)**; **entering** a wedge fires its
    action once.  Mouse/touch: hub at pie center; **tap** fires, motion previews.
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
        self._vol_repeat = volume_repeat_s  # unused: global action cooldown applies instead
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
        self._sx: float | None = None
        self._sy: float | None = None
        self._last_sector: str = "center"
        # Separate timers: volume uses fast _vol_repeat; destructive edges use _act_cd.
        self._last_vol_time: float = 0.0
        # Global guard for destructive edge actions only (left/right/right_up/right_down).
        self._last_global_action: float = 0.0

        self._cx = 0
        self._cy = 0
        self._R = 200
        self._wedge_items: dict[str, int] = {}
        self._cursor_dot: int | None = None
        self._cursor_line: int | None = None

        # Smoothed mouse position (canvas px); absolute mode only.
        self._msx: float | None = None
        self._msy: float | None = None

    @property
    def is_active(self) -> bool:
        return self._top is not None and self._top.winfo_exists()

    def show(self) -> None:
        if self.is_active:
            return
        self._sx = self._sy = None
        self._msx = self._msy = None
        self._last_sector = "center"
        self._last_vol_time = 0.0
        self._last_global_action = 0.0

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
        top.update_idletasks()

        # Motion = highlight only; Button-1 = tap / touch to activate.
        cv.bind("<Motion>", self._on_canvas_pointer_motion)
        cv.bind("<B1-Motion>", self._on_canvas_pointer_motion)
        cv.bind("<Button-1>", self._on_canvas_touch)
        cv.bind("<Enter>", lambda e: cv.focus_set())

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
            text=(
                "Hover TUIO over a wedge to act. Tap with mouse/touch. "
                f"Actions have a {self._act_cd:g}s cooldown. "
                "Remove the menu TUIO marker to close."
            ),
            fill="#666688",
            font=tkfont.Font(family="Consolas", size=12),
        )

        top.lift()
        top.focus_force()
        cv.focus_set()

    def hide(self) -> None:
        top = self._top
        if top:
            try:
                top.destroy()
            except tk.TclError:
                pass
        self._top = None
        self._cv = None
        self._wedge_items.clear()
        self._cursor_dot = self._cursor_line = None
        self._sx = self._sy = None
        self._msx = self._msy = None

    def _on_canvas_pointer_motion(self, event: tk.Event) -> None:
        if not self.is_active or self._cv is None:
            return
        self.feed_pointer_motion_only(float(event.x), float(event.y))

    def _on_canvas_touch(self, event: tk.Event) -> None:
        """Mouse click or touchscreen tap — fire the wedge under the pointer once."""
        if not self.is_active or self._cv is None:
            return
        sector = self._sector_at_pixel(float(event.x), float(event.y))
        self._invoke_sector_touch(sector)
        raw_dx = float(event.x) - float(self._cx)
        raw_dy = float(event.y) - float(self._cy)
        self._update_visual_pixels(raw_dx, raw_dy, sector)

    def _sector_at_pixel(self, canvas_x: float, canvas_y: float) -> str:
        """Instant sector under (x,y); no smoothing."""
        dx = canvas_x - float(self._cx)
        dy = canvas_y - float(self._cy)
        if math.hypot(dx, dy) < self._inner_dead_radius_px():
            return "center"
        return self._sector_from_vector(dx, dy)

    def _global_cooldown_blocks(self) -> bool:
        """True if we must ignore another wedge action (within menu_action_cooldown_seconds)."""
        return (time.monotonic() - self._last_global_action) < self._act_cd

    def _stamp_global_action(self) -> None:
        self._last_global_action = time.monotonic()

    def _invoke_sector_touch(self, sector: str) -> None:
        """One-shot actions for pointer tap; shared cooldown between all wedges."""
        if sector == "center":
            return
        if self._global_cooldown_blocks():
            return
        fired = False
        if sector == "up" and self._on_vol_up:
            self._on_vol_up()
            fired = True
        elif sector == "down" and self._on_vol_down:
            self._on_vol_down()
            fired = True
        else:
            edge_map: dict[str, Callable[[], None] | None] = {
                "left": self._on_left,
                "right": self._on_right,
                "right_up": self._on_right_up,
                "right_down": self._on_right_down,
            }
            cb = edge_map.get(sector)
            if cb:
                cb()
                fired = True
        if fired:
            self._stamp_global_action()

    def _inner_dead_radius_px(self) -> float:
        """Ignore jitter near hub; scales with pie radius."""
        return float(max(24, min(72, self._R // 4)))

    def _sector_from_vector(self, dx: float, dy: float) -> str:
        """Wedge from direction only (no dead zone). y-down screen coords."""
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

    def feed_pointer_motion_only(self, canvas_x: float, canvas_y: float) -> None:
        """Mouse / pen move: highlight only (tap activates via _on_canvas_touch)."""
        if not self.is_active or self._cv is None:
            return

        a = self._alpha
        if self._msx is None:
            self._msx, self._msy = float(canvas_x), float(canvas_y)
        else:
            self._msx = a * self._msx + (1.0 - a) * float(canvas_x)
            self._msy = a * self._msy + (1.0 - a) * float(canvas_y)

        dx = self._msx - float(self._cx)
        dy = self._msy - float(self._cy)
        ir = self._inner_dead_radius_px()
        if math.hypot(dx, dy) < ir:
            sector = "center"
        else:
            sector = self._sector_from_vector(dx, dy)

        self._update_visual_pixels(dx, dy, sector)

    def feed_tuio(self, x: float, y: float) -> None:
        if not self.is_active or self._cv is None:
            return

        a = self._alpha
        if self._sx is None:
            self._sx, self._sy = float(x), float(y)
        else:
            self._sx = a * self._sx + (1.0 - a) * float(x)
            self._sy = a * self._sy + (1.0 - a) * float(y)

        # Hub at normalized center so “marker toward top of camera” = VOL +.
        dx = self._sx - 0.5
        dy = self._sy - 0.5

        sector = self._classify_tuio_delta(dx, dy)
        self._update_visual(dx, dy, sector)
        self._fire_actions(sector)

    def _classify_tuio_delta(self, dx: float, dy: float) -> str:
        """TUIO: radial dead zone around (0.5, 0.5), then angle buckets."""
        t = self._th
        if math.hypot(dx, dy) < max(t * 0.65, 0.018):
            return "center"
        return self._sector_from_vector(dx, dy)

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

    def _update_visual_pixels(self, dx: float, dy: float, sector: str) -> None:
        """Hub-and-spoke cursor from pie center; dx, dy in canvas pixels."""
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

        dist = math.hypot(dx, dy)
        max_r = float(self._R - 20)
        if dist < 1e-6:
            px = py = 0.0
        else:
            s = min(1.0, max_r / dist)
            px = dx * s
            py = dy * s
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
        callback: Callable[[], None] | None,
    ) -> None:
        if sector != tag:
            return
        if self._last_sector == tag:
            return
        if self._global_cooldown_blocks():
            return
        if callback:
            callback()
            self._stamp_global_action()

    def _fire_actions(self, sector: str) -> None:
        """TUIO: volume repeats while hovering (every vol_repeat seconds);
        destructive edges fire once on entry with the 2s cooldown."""
        now = time.monotonic()

        # Volume: fire continuously while marker stays in up/down wedge.
        if sector == "up" and self._on_vol_up:
            if now - self._last_vol_time >= self._vol_repeat:
                self._last_vol_time = now
                self._on_vol_up()
        elif sector == "down" and self._on_vol_down:
            if now - self._last_vol_time >= self._vol_repeat:
                self._last_vol_time = now
                self._on_vol_down()

        # Destructive edges: edge-triggered (enter only) + global cooldown.
        self._fire_edge_action(sector, "left", self._on_left)
        self._fire_edge_action(sector, "right", self._on_right)
        self._fire_edge_action(sector, "right_up", self._on_right_up)
        self._fire_edge_action(sector, "right_down", self._on_right_down)

        self._last_sector = sector
