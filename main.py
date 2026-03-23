#!/usr/bin/env python3
"""
Gesture-Powered Virtual Game Control
─────────────────────────────────────────────────────────────────────────────
Fullscreen Tkinter GUI driven by TUIO fiducial markers via reacTIVision.

  • Launches reacTIVision.exe in the background automatically.
  • Listens for TUIO OSC messages on UDP port 3333 (via python-osc).
  • Main menu waits for a marker → routes to the matching user's personal page.
  • Each user page has its own animated GIF background and colour theme.
  • Rotate the TUIO marker LEFT  → return to the main menu.
  • Rotate the TUIO marker RIGHT → launch the configured game.
  • Admin: Bluetooth + TUIO admin marker — on the admin page, move marker up/down to
    change selection, push right (displacement) to add a random user, rotate ► to
    remove selected, rotate ◄ to return to the main menu (no mouse required).
  • Circular menu: TUIO marker #10 (configurable) — move relative to neutral for
    volume / minimize others / exit game; remove marker to close the menu.

Keyboard shortcuts (for testing without hardware):
  0 / 1 / 2 / 3  – simulate placing / removing TUIO marker for that user
  9              – simulate admin marker (only if Bluetooth gate passes or force is on)
  M              – toggle circular menu overlay (no TUIO)
  ← Left arrow   – simulate rotating LEFT  (back to menu)
  → Right arrow  – simulate rotating RIGHT (launch game)
  ESC / Q        – exit
  F11            – toggle fullscreen
"""

import subprocess
import time
import tkinter as tk

from gesture_controller import GestureController
from bluetooth_admin import BluetoothAdminPresence
from character_map  import MAIN_BK_GIF, GAME_ICON
from config         import (
    ADMIN_BLUETOOTH_FORCE,
    ADMIN_BLUETOOTH_MAC,
    ADMIN_BLUETOOTH_NAME,
    ADMIN_BT_POLL_SECONDS,
    ADMIN_BT_SCAN_SECONDS,
    ADMIN_BT_TTL_SECONDS,
    ADMIN_TUIO_MARKER,
    IS_WINDOWS,
    MENU_ACTION_COOLDOWN_SECONDS,
    MENU_CURSOR_GAIN,
    MENU_MOTION_THRESHOLD,
    MENU_SMOOTH_ALPHA,
    MENU_TUIO_MARKER,
    MENU_VOLUME_REPEAT_SECONDS,
    MENU_VOLUME_STEP,
    REACTVISION_EXE,
    TUIO_HOST,
    TUIO_PORT,
    VR_BRIDGE_ENABLED,
)
from game_launcher  import game_running, get_tracked_game_pid, launch_game, terminate_game
from gif_utils      import GifManager, load_avatar, load_image
from tuio_circular_menu import CircularMenuController
from tuio_listener  import TUIOListener, OSC_AVAILABLE
from user_store     import (
    build_user_dict,
    load_users,
    next_free_marker_id,
    random_display_name,
    save_users,
)
import windows_controls
from vr_bridge      import VRBridge


class HCIApp(tk.Tk):
    """Root window – manages screen transitions and TUIO communication."""

    def __init__(self):
        super().__init__()
        self.title("Gesture-Powered Virtual Game Control")
        self.attributes("-fullscreen", True)
        self.configure(bg="#000000")

        self._gif   = GifManager(self)
        self._users = load_users()

        self._bt_admin = BluetoothAdminPresence(
            mac=ADMIN_BLUETOOTH_MAC,
            name=ADMIN_BLUETOOTH_NAME,
            scan_duration=ADMIN_BT_SCAN_SECONDS,
            poll_interval=ADMIN_BT_POLL_SECONDS,
            ttl_seconds=ADMIN_BT_TTL_SECONDS,
            force_connected=ADMIN_BLUETOOTH_FORCE,
        )

        # ── key bindings ──────────────────────────────────────────────────────
        self.bind("<Escape>", self._on_exit)
        self.bind("q",        self._on_exit)
        self.bind("<F11>",    lambda e: self.attributes(
            "-fullscreen", not self.attributes("-fullscreen")))
        for k in "0123":
            self.bind(k, lambda e, uid=int(k): self._simulate_tuio(uid))
        self.bind("9", self._simulate_admin_tuio)
        self.bind("m", self._simulate_menu_toggle)
        self.bind("<Left>",  lambda e: self._simulate_rotation("left"))
        self.bind("<Right>", lambda e: self._simulate_rotation("right"))
        self.bind("<Map>",   lambda e: self.attributes("-fullscreen", True))

        # ── state ─────────────────────────────────────────────────────────────
        self._current_user       = None
        self._screen             = None
        self._rotation_triggered = False
        self._tuio_light_cv      = None
        self._tuio_light_oval    = None
        self._u_theme            = None
        self._current_gif_key    = None
        self._admin_screen       = False
        self._admin_lb: tk.Listbox | None = None
        self._admin_tuio_neutral: tuple[float, float] | None = None
        self._admin_tuio_sx: float | None = None
        self._admin_tuio_sy: float | None = None
        self._admin_tuio_last_sector = "center"
        self._admin_tuio_last_ud_time = 0.0
        self._admin_tuio_last_add_time = 0.0
        self._admin_tuio_last_remove_time = 0.0
        self._reactivision_process = None

        self._menu_ctrl = CircularMenuController(
            self,
            motion_threshold=MENU_MOTION_THRESHOLD,
            smooth_alpha=MENU_SMOOTH_ALPHA,
            volume_repeat_s=MENU_VOLUME_REPEAT_SECONDS,
            action_cooldown_s=MENU_ACTION_COOLDOWN_SECONDS,
            cursor_gain=MENU_CURSOR_GAIN,
            on_volume_up=lambda: windows_controls.volume_step(MENU_VOLUME_STEP),
            on_volume_down=lambda: windows_controls.volume_step(-MENU_VOLUME_STEP),
            on_action_left=self._menu_action_left,
            on_action_right=self._menu_action_right,
            on_action_right_up=self._menu_action_right_up,
            on_action_right_down=self._menu_action_right_down,
        )

        # ── start ─────────────────────────────────────────────────────────────
        self._launch_reactivision()
        self._bt_admin.start()

        # ── VR bridge ─────────────────────────────────────────────────────────
        self._vr_bridge = VRBridge(dry_run=not VR_BRIDGE_ENABLED)
        self._gesture_controller = GestureController(self._vr_bridge)


        self._listener = TUIOListener(
            on_marker_detected=lambda fid:       self.after(0, lambda: self._on_marker_detected(fid)),
            on_marker_rotated= lambda d, fid:    self.after(0, lambda: self._on_marker_rotated(d, fid)),
            on_marker_removed= lambda fid:       self.after(0, lambda: self._on_marker_removed(fid)),
            on_marker_moved=   self._on_tuio_marker_moved,
            host=TUIO_HOST,
            port=TUIO_PORT,
        )
        self._listener.start()
        self._show_main_menu()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _on_exit(self, _event=None):
        self._bt_admin.stop()
        self._vr_bridge.stop()
        self._listener.stop()
        self.destroy()

    # ── reacTIVision ──────────────────────────────────────────────────────────

    def _launch_reactivision(self):
        if not REACTVISION_EXE:
            print("[WARN] reacTIVision not found")
            return
        try:
            self._reactivision_process = subprocess.Popen([REACTVISION_EXE])
            time.sleep(1.5)
            print("[INFO] reacTIVision launched.")
        except Exception as exc:
            print(f"[ERROR] Could not launch reacTIVision: {exc}")

    def _stop_reactivision(self):
        if self._reactivision_process:
            try:
                self._reactivision_process.terminate()
                self._reactivision_process.wait(timeout=3)
                print("[INFO] reacTIVision terminated.")
            except Exception:
                pass
            self._reactivision_process = None

    # ── TUIO callbacks (dispatched to main thread via after(0, ...)) ──────────

    def _on_tuio_marker_moved(self, fid: int, x: float, y: float, a: float):
        """Background thread — keep VR path synchronous; menu UI on main thread."""
        self._vr_bridge.enqueue(fid, x, y, a)
        if fid == MENU_TUIO_MARKER and self._menu_ctrl.is_active:
            self.after(0, lambda xx=x, yy=y: self._menu_ctrl.feed_tuio(xx, yy))
        if self._admin_screen and fid == ADMIN_TUIO_MARKER:
            self.after(0, lambda xx=x, yy=y: self._admin_feed_tuio_motion(xx, yy))

    def _on_marker_detected(self, fid: int):
        if fid == MENU_TUIO_MARKER:
            self._menu_ctrl.show()
            return
        if game_running.is_set():
            return
        if self._current_user is None and not self._admin_screen:
            if (
                fid == ADMIN_TUIO_MARKER
                and self._bt_admin.connected.is_set()
            ):
                self._show_admin_page()
                return
        if self._current_user is None and fid in self._users:
            self._current_user = fid
            self._show_user_page(fid)
        elif self._current_user == fid:
            self._set_tuio_light(True)
        elif self._admin_screen and fid == ADMIN_TUIO_MARKER:
            self._set_tuio_light(True)

    def _on_marker_removed(self, fid: int):
        if fid == MENU_TUIO_MARKER:
            self._menu_ctrl.hide()
            return
        if game_running.is_set():
            return
        if self._current_user == fid:
            self._set_tuio_light(False)
        if self._admin_screen and fid == ADMIN_TUIO_MARKER:
            self._set_tuio_light(False)

    def _on_marker_rotated(self, direction: str, fid: int):
        if self._menu_ctrl.is_active:
            return
        if game_running.is_set():
            return
        if self._admin_screen:
            if fid != ADMIN_TUIO_MARKER:
                return
            if direction == "left":
                if self._rotation_triggered:
                    return
                self._rotation_triggered = True
                self._show_main_menu()
                return
            if direction == "right":
                self._admin_tuio_remove_selected()
            return
        if self._current_user != fid or self._rotation_triggered:
            return
        self._rotation_triggered = True
        if direction == "left":
            self._current_user = None
            self._show_main_menu()
        else:
            self._do_launch_game()

    # ── keyboard simulation ───────────────────────────────────────────────────

    def _simulate_tuio(self, uid: int):
        if self._current_user is None and uid in self._users:
            self._current_user = uid
            self._show_user_page(uid)
        elif self._current_user == uid:
            self._current_user = None
            self._show_main_menu()

    def _simulate_rotation(self, direction: str):
        if self._menu_ctrl.is_active:
            return
        if game_running.is_set():
            return
        if self._admin_screen:
            if direction == "left":
                if self._rotation_triggered:
                    return
                self._rotation_triggered = True
                self._show_main_menu()
                return
            if direction == "right":
                self._admin_tuio_remove_selected()
            return
        if self._current_user is None or self._rotation_triggered:
            return
        self._rotation_triggered = True
        if direction == "left":
            self._current_user = None
            self._show_main_menu()
        else:
            self._do_launch_game()

    def _simulate_admin_tuio(self, _event=None):
        """Keyboard: open admin screen like holding the admin TUIO marker."""
        if game_running.is_set() or self._current_user is not None or self._admin_screen:
            return
        if not self._bt_admin.connected.is_set():
            return
        self._show_admin_page()

    def _simulate_menu_toggle(self, _event=None):
        """Keyboard: show/hide circular menu without the TUIO menu marker."""
        if self._menu_ctrl.is_active:
            self._menu_ctrl.hide()
        else:
            self._menu_ctrl.show()

    def _menu_action_left(self):
        """Exit tracked game process (if any) and return to fullscreen GUI."""
        terminate_game()
        windows_controls.restore_focus_fullscreen(self)

    def _menu_action_right(self):
        """Minimize other top-level windows, then fullscreen this app."""
        hwnd = windows_controls.tk_hwnd(self)
        windows_controls.minimize_other_windows(hwnd)
        windows_controls.restore_focus_fullscreen(self)

    def _menu_action_right_up(self):
        """
        If the tracked game is fullscreen/maximized: minimize game, fullscreen GUI.
        Only when a tracked .exe is running.
        """
        if not game_running.is_set():
            return
        pid = get_tracked_game_pid()
        if pid is None:
            return
        ghwnd = windows_controls.find_main_window_hwnd_for_pid(pid)
        if not ghwnd:
            return
        if not windows_controls.window_is_fullscreen_or_maximized(ghwnd):
            return
        windows_controls.minimize_window(ghwnd)
        windows_controls.restore_focus_fullscreen(self)

    def _menu_action_right_down(self):
        """
        If tracked game .exe is running: maximize/focus game and minimize this GUI.
        Closes the radial overlay so the game is visible; re-show marker to open menu.
        """
        if not game_running.is_set():
            return
        pid = get_tracked_game_pid()
        if pid is None:
            return
        ghwnd = windows_controls.find_main_window_hwnd_for_pid(pid)
        if not ghwnd:
            return
        self._menu_ctrl.hide()
        windows_controls.restore_maximize_and_foreground(ghwnd)
        windows_controls.minimize_tk_root(self)

    # ── screen helpers ────────────────────────────────────────────────────────

    def _clear_screen(self):
        self._admin_lb = None
        self._admin_tuio_neutral = None
        self._admin_tuio_sx = self._admin_tuio_sy = None
        self._admin_tuio_last_sector = "center"
        self._admin_screen       = False
        self._rotation_triggered = False
        self._tuio_light_cv      = None
        self._tuio_light_oval    = None
        if self._screen and self._screen.winfo_exists():
            self._screen.destroy()
        self._screen = None
        if self._current_gif_key:
            self._gif.evict(*self._current_gif_key)
            self._current_gif_key = None

    def _set_tuio_light(self, active: bool):
        if self._tuio_light_cv is None:
            return
        try:
            self._tuio_light_cv.itemconfig(
                self._tuio_light_oval, fill="#00ff00" if active else "#ff2222")
        except tk.TclError:
            pass

    # ── Admin page: TUIO-only list / add / remove (marker displacement + rotation) ─

    def _classify_admin_motion(self, dx: float, dy: float) -> str:
        th = MENU_MOTION_THRESHOLD
        if abs(dx) < th * 0.35 and abs(dy) < th * 0.35:
            return "center"
        if abs(dx) > abs(dy) and dx > th:
            return "m_right"
        if abs(dy) >= abs(dx) and dy < -th:
            return "up"
        if abs(dy) >= abs(dx) and dy > th:
            return "down"
        return "center"

    def _admin_move_selection(self, delta: int) -> None:
        lb = self._admin_lb
        if lb is None or not self._admin_screen:
            return
        try:
            n = lb.size()
            if n <= 0:
                return
            sel = lb.curselection()
            cur = int(sel[0]) if sel else 0
            new = max(0, min(n - 1, cur + delta))
            lb.selection_clear(0, tk.END)
            lb.selection_set(new)
            lb.activate(new)
            lb.see(new)
        except tk.TclError:
            pass

    def _admin_tuio_remove_selected(self) -> None:
        """Rotate marker right — remove highlighted user (cooldown)."""
        now = time.monotonic()
        if now - self._admin_tuio_last_remove_time < MENU_ACTION_COOLDOWN_SECONDS:
            return
        lb = self._admin_lb
        if lb is None or not self._admin_screen:
            return
        try:
            sel = lb.curselection()
            if not sel:
                return
            line = lb.get(sel[0])
            uid = int(line.split("\t", 1)[0])
        except (tk.TclError, ValueError, IndexError):
            return
        if uid not in self._users:
            return
        self._admin_tuio_last_remove_time = now
        self._users.pop(uid)
        save_users(self._users)
        self._users = load_users()
        self._show_admin_page()

    def _admin_tuio_trigger_add_random(self) -> None:
        """Displacement to the right (edge) — add user with random name."""
        now = time.monotonic()
        if now - self._admin_tuio_last_add_time < MENU_ACTION_COOLDOWN_SECONDS:
            return
        self._admin_tuio_last_add_time = now
        nid = next_free_marker_id(self._users)
        self._users[nid] = build_user_dict(nid, random_display_name())
        save_users(self._users)
        self._users = load_users()
        self._show_admin_page()

    def _admin_feed_tuio_motion(self, x: float, y: float) -> None:
        if not self._admin_screen or self._admin_lb is None:
            return
        lb = self._admin_lb
        try:
            if not lb.winfo_exists():
                return
        except tk.TclError:
            return

        if self._admin_tuio_neutral is None:
            self._admin_tuio_neutral = (float(x), float(y))
            self._admin_tuio_sx = float(x)
            self._admin_tuio_sy = float(y)
            return

        x0, y0 = self._admin_tuio_neutral
        a = MENU_SMOOTH_ALPHA
        self._admin_tuio_sx = a * self._admin_tuio_sx + (1.0 - a) * float(x)  # type: ignore[operator]
        self._admin_tuio_sy = a * self._admin_tuio_sy + (1.0 - a) * float(y)  # type: ignore[operator]
        dx = self._admin_tuio_sx - x0  # type: ignore[operator]
        dy = self._admin_tuio_sy - y0  # type: ignore[operator]

        sector = self._classify_admin_motion(dx, dy)
        now = time.monotonic()
        ud_gap = max(0.28, MENU_VOLUME_REPEAT_SECONDS)

        if sector == "up":
            if now - self._admin_tuio_last_ud_time >= ud_gap:
                self._admin_tuio_last_ud_time = now
                self._admin_move_selection(-1)
        elif sector == "down":
            if now - self._admin_tuio_last_ud_time >= ud_gap:
                self._admin_tuio_last_ud_time = now
                self._admin_move_selection(1)
        elif sector == "m_right" and self._admin_tuio_last_sector != "m_right":
            self._admin_tuio_trigger_add_random()

        self._admin_tuio_last_sector = sector

    def _sw(self) -> int:
        return self.winfo_screenwidth()

    def _sh(self) -> int:
        return self.winfo_screenheight()

    # ── GIF helpers ───────────────────────────────────────────────────────────

    def _start_gif(self, canvas: tk.Canvas, path: str, width: int, height: int, owner):
        """Load a GIF onto *canvas* and start its animation loop.
        Animation stops automatically when the owning screen changes."""
        self._current_gif_key = (path, width, height)
        frames, delays = self._gif.load(path, width, height)
        if not frames:
            return
        item = canvas.create_image(0, 0, anchor="nw", image=frames[0])
        canvas.gif_frames = frames   # prevent GC
        self._gif.animate(canvas, frames, delays, 0, item, lambda: self._screen is owner)

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN MENU
    # ══════════════════════════════════════════════════════════════════════════

    def _show_main_menu(self):
        self._clear_screen()
        sw, sh = self._sw(), self._sh()

        canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._screen = canvas

        # self._start_gif(canvas, MAIN_BK_GIF, sw, sh, canvas)

        canvas.create_rectangle(0, 0, sw, sh,
                                 fill="#000000", stipple="gray50", outline="")

        canvas.create_text(
            sw // 2, int(sh * 0.20),
            text="GESTURE-POWERED  VIRTUAL  GAME  CONTROL",
            font=("Bahnschrift", int(sh * 0.040), "bold"),
            fill="#ffffff",
        )

        lx = int(sw * 0.225)
        canvas.create_line(lx, int(sh * 0.29), sw - lx, int(sh * 0.29),
                           fill="#444444", width=2)

        canvas.create_text(sw // 2, int(sh * 0.37),
                           text="Welcome, User!",
                           font=("Bahnschrift", int(sh * 0.044), "bold"),
                           fill="#00b4d8")
        canvas.create_text(sw // 2, int(sh * 0.46),
                           text="Please sign in by holding a TUIO marker in front of the camera.",
                           font=("Bahnschrift", int(sh * 0.022)),
                           fill="#aaaaaa")

        canvas.create_text(sw // 2, int(sh * 0.565),
                           text="REGISTERED USERS",
                           font=("Consolas", int(sh * 0.014), "bold"),
                           fill="#555555")

        card_w   = int(sw  * 0.130)
        card_h   = int(sh  * 0.200)
        gap      = int(sw  * 0.020)
        total_w  = len(self._users) * card_w + (len(self._users) - 1) * gap
        start_x  = sw // 2 - total_w // 2
        card_top = int(sh * 0.595)
        av_sz    = int(card_h * 0.48)

        for i, (uid, user) in enumerate(self._users.items()):
            cx   = start_x + i * (card_w + gap)
            card = tk.Frame(canvas, bg=user["header_bg"],
                            width=card_w, height=card_h)
            card.pack_propagate(False)

            av = load_avatar(user["avatar"], av_sz, user["accent"])
            if av:
                av_lbl = tk.Label(card, image=av, bg=user["header_bg"], bd=0)
                av_lbl.image = av
                av_lbl.pack(pady=(int(card_h * 0.06), 4))

            tk.Label(card,
                     text=f"MARKER  #{uid}",
                     font=("Consolas", int(sh * 0.012), "bold"),
                     fg=user["accent"], bg=user["header_bg"]).pack()

            tk.Label(card,
                     text=user["name"],
                     font=("Bahnschrift", int(sh * 0.020), "bold"),
                     fg=user["fg"], bg=user["header_bg"]).pack()

            stripe = tk.Canvas(card, height=5, bg=user["header_bg"],
                               highlightthickness=0)
            stripe.pack(fill="x", side="bottom")
            stripe.bind("<Configure>",
                        lambda e, c=stripe, col=user["accent"]:
                            c.create_rectangle(0, 0, e.width, 5, fill=col))

            canvas.create_window(cx, card_top, anchor="nw",
                                 window=card, width=card_w, height=card_h)

        blink_lbl = tk.Label(canvas,
                             text="●  LISTENING FOR TUIO",
                             font=("Consolas", int(sh * 0.017)),
                             bg="#000000")
        canvas.create_window(sw // 2, int(sh * 0.875),
                             anchor="center", window=blink_lbl)
        self._blink(blink_lbl, canvas, green=True)

    def _blink(self, label: tk.Label, owner, green: bool = True):
        if self._screen is not owner:
            return
        try:
            label.config(fg="#00ff00" if green else "#004400")
            self.after(650, lambda: self._blink(label, owner, not green))
        except tk.TclError:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  USER PAGE
    # ══════════════════════════════════════════════════════════════════════════

    def _show_user_page(self, user_id: int):
        self._clear_screen()
        u  = self._users[user_id]
        sw = self._sw()
        sh = self._sh()

        frame = tk.Frame(self, bg=u["bg"])
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._screen  = frame
        self._u_theme = u

        # ── header bar ────────────────────────────────────────────────────────
        hdr_h  = int(sh * 0.10)
        header = tk.Frame(frame, bg=u["header_bg"], height=hdr_h)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header,
                 text="  GESTURE-POWERED  VIRTUAL  GAME  CONTROL",
                 font=("Bahnschrift", int(sh * 0.022), "bold"),
                 fg=u["accent"], bg=u["header_bg"]).pack(
                     side="left", padx=int(sw * 0.022), pady=int(hdr_h * 0.25))

        dot_sz  = int(hdr_h * 0.36)
        ind_frm = tk.Frame(header, bg=u["header_bg"])
        ind_frm.pack(side="right", padx=int(sw * 0.030))

        dot_cv = tk.Canvas(ind_frm, width=dot_sz, height=dot_sz,
                           bg=u["header_bg"], highlightthickness=0)
        dot_cv.pack(side="left", pady=(hdr_h - dot_sz) // 2)
        dot_oval = dot_cv.create_oval(0, 0, dot_sz, dot_sz,
                                      fill="#00ff00", outline="#005500", width=2)
        tk.Label(ind_frm, text="TUIO READING",
                 font=("Consolas", int(sh * 0.016), "bold"),
                 fg="#aaaaaa", bg=u["header_bg"]).pack(side="left", padx=(8, 0))
        self._tuio_light_cv   = dot_cv
        self._tuio_light_oval = dot_oval

        # ── game bar (bottom panel) ────────────────────────────────────────────
        bar_h    = int(sh * 0.22)
        game_bar = tk.Frame(frame, bg=u["header_bg"], height=bar_h)
        game_bar.pack(fill="x", side="bottom")
        game_bar.pack_propagate(False)

        hints     = tk.Frame(game_bar, bg=u["header_bg"])
        hints.pack(side="left", padx=int(sw * 0.035), expand=True, fill="both")

        btn_pad_y = int(bar_h * 0.14)
        btn_pad_x = int(sw  * 0.010)

        # ◄ Left button
        left_box = tk.Frame(hints, bg=u["bg"],
                            highlightthickness=2,
                            highlightbackground=u["accent"])
        left_box.pack(side="left", expand=True, fill="both",
                      padx=btn_pad_x, pady=btn_pad_y)
        tk.Canvas(left_box, height=5, bg=u["accent"],
                  highlightthickness=0).pack(fill="x")
        l_body = tk.Frame(left_box, bg=u["bg"])
        l_body.pack(expand=True, fill="both", padx=16)
        l_row = tk.Frame(l_body, bg=u["bg"])
        l_row.pack(expand=True, anchor="center")
        tk.Label(l_row, text="◄",
                 font=("Bahnschrift", int(sh * 0.034), "bold"),
                 fg=u["accent"], bg=u["bg"]).pack(side="left", padx=(0, 8))
        tk.Label(l_row, text="ROTATE LEFT",
                 font=("Bahnschrift", int(sh * 0.028), "bold"),
                 fg="#ffffff", bg=u["bg"]).pack(side="left")
        tk.Label(l_body, text="Back to Main Menu",
                 font=("Consolas", int(sh * 0.014)),
                 fg="#aaaaaa", bg=u["bg"]).pack(pady=(2, 6))
        tk.Canvas(left_box, height=2, bg=u["accent"],
                  highlightthickness=0).pack(fill="x", side="bottom")

        # ► Right button
        right_box = tk.Frame(hints, bg=u["glow"], highlightthickness=0)
        right_box.pack(side="left", expand=True, fill="both",
                       padx=btn_pad_x, pady=btn_pad_y)
        tk.Canvas(right_box, height=5, bg=u["accent"],
                  highlightthickness=0).pack(fill="x")
        r_body = tk.Frame(right_box, bg=u["glow"])
        r_body.pack(expand=True, fill="both", padx=16)
        r_row = tk.Frame(r_body, bg=u["glow"])
        r_row.pack(expand=True, anchor="center")
        tk.Label(r_row, text="ROTATE RIGHT",
                 font=("Bahnschrift", int(sh * 0.028), "bold"),
                 fg=u["header_bg"], bg=u["glow"]).pack(side="left")
        tk.Label(r_row, text="  ►",
                 font=("Bahnschrift", int(sh * 0.034), "bold"),
                 fg=u["header_bg"], bg=u["glow"]).pack(side="left")
        tk.Label(r_body, text="Launch Ninja Fruit",
                 font=("Consolas", int(sh * 0.014)),
                 fg=u["bg"], bg=u["glow"]).pack(pady=(2, 6))
        tk.Canvas(right_box, height=2, bg=u["header_bg"],
                  highlightthickness=0).pack(fill="x", side="bottom")

        # Ninja Fruit icon
        border     = 4
        icon_sz    = int(bar_h * 0.62)
        icon_pad_y = (bar_h - icon_sz - border * 2) // 2
        icon_photo = load_image(GAME_ICON, icon_sz, icon_sz)

        icon_wrapper = tk.Frame(game_bar, bg=u["header_bg"])
        icon_wrapper.pack(side="right", padx=int(sw * 0.032), pady=icon_pad_y)
        tk.Label(icon_wrapper, text="NINJA FRUIT",
                 font=("Bahnschrift", int(sh * 0.022), "bold"),
                 fg=u["accent"], bg=u["header_bg"]).pack()
        icon_frame = tk.Frame(icon_wrapper, bg=u["accent"],
                              padx=border, pady=border)
        icon_frame.pack()
        icon_lbl = tk.Label(icon_frame, image=icon_photo,
                            bg=u["header_bg"], bd=0)
        icon_lbl.image = icon_photo
        icon_lbl.pack()

        # ── body canvas — animated GIF with text ──────────────────────────────
        body_h  = sh - hdr_h - bar_h
        body_cv = tk.Canvas(frame, width=sw, height=body_h,
                            bg=u["bg"], highlightthickness=0)
        body_cv.pack(fill="both", expand=True)

        # self._start_gif(body_cv, u["gif"], sw, body_h, frame)

        body_cv.create_rectangle(0, 0, sw, body_h,
                                  fill="#000000", stipple="gray25", outline="")

        av_sz = int(body_h * 0.38)
        av    = load_avatar(u["avatar"], av_sz, u["accent"])
        if av:
            body_cv.create_image(sw // 2, int(body_h * 0.22),
                                 anchor="center", image=av)
            body_cv.av_photo = av   # prevent GC

        body_cv.create_text(sw // 2, int(body_h * 0.47),
                            text="Welcome,",
                            font=("Bahnschrift", int(sh * 0.038)),
                            fill=u["fg"])
        body_cv.create_text(sw // 2, int(body_h * 0.615),
                            text=u["name"],
                            font=("Impact", int(sh * 0.095), "bold"),
                            fill=u["accent"])
        body_cv.create_text(sw // 2, int(body_h * 0.76),
                            text=f"TUIO marker  #{user_id}  recognised",
                            font=("Consolas", int(sh * 0.016)),
                            fill=u["glow"])

        div_w = int(sw * 0.40)
        div_x = sw // 2 - div_w // 2
        div_y = int(body_h * 0.855)
        body_cv.create_rectangle(div_x, div_y, div_x + div_w, div_y + 4,
                                  fill=u["accent"], outline="")

    # ══════════════════════════════════════════════════════════════════════════
    #  ADMIN PAGE (Bluetooth + TUIO marker #9 on main menu)
    # ══════════════════════════════════════════════════════════════════════════

    def _show_admin_page(self):
        self._clear_screen()
        self._admin_screen = True
        self._current_user = None

        bg = "#16213e"
        hdr = "#0f3460"
        accent = "#e94560"
        fg = "#eaeaea"
        sw, sh = self._sw(), self._sh()

        frame = tk.Frame(self, bg=bg)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._screen = frame
        self._u_theme = {
            "bg": bg,
            "header_bg": hdr,
            "accent": accent,
            "fg": fg,
        }

        hdr_h = int(sh * 0.10)
        header = tk.Frame(frame, bg=hdr, height=hdr_h)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="  ADMIN — USER MANAGEMENT",
            font=("Bahnschrift", int(sh * 0.026), "bold"),
            fg=accent,
            bg=hdr,
        ).pack(side="left", padx=int(sw * 0.022), pady=int(hdr_h * 0.22))

        dot_sz = int(hdr_h * 0.36)
        ind_frm = tk.Frame(header, bg=hdr)
        ind_frm.pack(side="right", padx=int(sw * 0.030))
        dot_cv = tk.Canvas(
            ind_frm, width=dot_sz, height=dot_sz, bg=hdr, highlightthickness=0
        )
        dot_cv.pack(side="left", pady=(hdr_h - dot_sz) // 2)
        dot_oval = dot_cv.create_oval(
            0, 0, dot_sz, dot_sz, fill="#ff2222", outline="#550000", width=2
        )
        tk.Label(
            ind_frm,
            text="TUIO READING",
            font=("Consolas", int(sh * 0.016), "bold"),
            fg="#aaaaaa",
            bg=hdr,
        ).pack(side="left", padx=(8, 0))
        self._tuio_light_cv = dot_cv
        self._tuio_light_oval = dot_oval

        body = tk.Frame(frame, bg=bg)
        body.pack(fill="both", expand=True, padx=int(sw * 0.06), pady=int(sh * 0.04))

        tk.Label(
            body,
            text=(
                f"TUIO only — marker #{ADMIN_TUIO_MARKER}.  "
                "Move UP / DOWN on the table to change selection • "
                "Push marker RIGHT (displacement) once to add a random user • "
                "Rotate marker ► to remove the selected user • "
                "Rotate ◄ to main menu.  (Phone must satisfy Bluetooth gate.)"
            ),
            font=("Bahnschrift", int(sh * 0.017)),
            fg=fg,
            bg=bg,
            wraplength=int(sw * 0.88),
            justify="center",
        ).pack(pady=(0, int(sh * 0.02)))

        list_frame = tk.Frame(body, bg=bg)
        list_frame.pack(fill="both", expand=True)

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side="right", fill="y")
        lb = tk.Listbox(
            list_frame,
            font=("Consolas", int(sh * 0.020)),
            bg="#1f2b47",
            fg=fg,
            selectbackground=accent,
            highlightthickness=0,
            yscrollcommand=scroll.set,
            activestyle="none",
        )
        lb.pack(side="left", fill="both", expand=True)
        scroll.config(command=lb.yview)

        for uid in sorted(self._users.keys()):
            u = self._users[uid]
            lb.insert(tk.END, f"{uid}\t{u['name']}")

        self._admin_lb = lb
        if lb.size() > 0:
            lb.selection_set(0)
            lb.activate(0)

    # ── game launch ───────────────────────────────────────────────────────────

    # Users whose game input comes from TUIO markers via the VR bridge.
    # All other users fall back to MediaPipe (gesture_controller).
    _TUIO_CONTROL_USERS = {0, 1}     # Omar Hassan, Youssef Ali

    def _on_game_exit(self):
        self.after(0, self._check_game_exit)


    def _do_launch_game(self):
        name = self._users[self._current_user]["name"] \
            if self._current_user is not None else ""

        # Decide control method based on the logged-in user
        use_tuio = self._current_user in self._TUIO_CONTROL_USERS
        self._use_tuio_control = use_tuio

        if use_tuio:
            # TUIO users — keep reacTIVision running (markers drive the sabers)
            if VR_BRIDGE_ENABLED and not self._vr_bridge.is_running:
                self._vr_bridge.start()
            print(f"[INFO] Launching with TUIO controllers for {name}")
        else:
            # MediaPipe users — stop reacTIVision to free the webcam
            self._stop_reactivision()
            self._gesture_controller.start()
            print(f"[INFO] Launching with MediaPipe controllers for {name}")

        success, error_msg = launch_game(
            character_name=name,
            on_exit=self._on_game_exit
        )

        if success:
            self.attributes("-fullscreen", False)
            self.iconify()
            self._rotation_triggered = False

            self.after(1000, self._check_game_exit)

        else:
            self._show_error(error_msg)


    def _check_game_exit(self):
        if game_running.is_set():
            self.after(1000, self._check_game_exit)
            return

        print("[INFO] Game exited → restoring system")

        # 🔴 STOP whichever controller was active
        if getattr(self, '_use_tuio_control', False):
            self._vr_bridge.stop()
        else:
            self._gesture_controller.stop()

        # 🟢 RESTART reacTIVision (MediaPipe path stopped it; TUIO path is a no-op if already running)
        self._launch_reactivision()

        # 🟢 Restore UI
        self.deiconify()
        self.attributes("-fullscreen", True)

    def _show_error(self, message: str):
        if not (self._screen and self._screen.winfo_exists()):
            return
        u       = self._u_theme
        overlay = tk.Frame(self._screen, bg=u["bg"])
        overlay.place(relx=0.1, rely=0.35, relwidth=0.8, relheight=0.25)
        tk.Label(
            overlay,
            text=f"⚠  {message}",
            font=("Courier New", int(self._sh() * 0.020)),
            fg="#ff5555", bg=u["bg"],
            wraplength=int(self._sw() * 0.70),
            justify="center",
        ).pack(expand=True)


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not OSC_AVAILABLE:
        print(
            "\n[WARN] python-osc is not installed.\n"
            "       Install it with:  pip install python-osc\n"
            "       The app will still run but TUIO hardware will not work.\n"
            "       Use keys 0–3 for users; 9 for admin; M toggles circular menu.\n"
        )
    app = HCIApp()
    app.mainloop()
