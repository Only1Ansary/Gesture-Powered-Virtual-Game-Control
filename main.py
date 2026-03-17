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

Keyboard shortcuts (for testing without hardware):
  0 / 1 / 2 / 3  – simulate placing / removing TUIO marker for that user
  ← Left arrow   – simulate rotating LEFT  (back to menu)
  → Right arrow  – simulate rotating RIGHT (launch game)
  ESC / Q        – exit
  F11            – toggle fullscreen
"""

import subprocess
import time
import tkinter as tk

from character_map  import MAIN_BK_GIF, GAME_ICON, get_all_users
from config         import BASE_DIR, IS_WINDOWS, REACTVISION_EXE, TUIO_HOST, TUIO_PORT, VR_BRIDGE_ENABLED
from game_launcher  import launch_game
from gif_utils      import GifManager, load_avatar, load_image
from tuio_listener  import TUIOListener, OSC_AVAILABLE
from vr_bridge      import VRBridge


class HCIApp(tk.Tk):
    """Root window – manages screen transitions and TUIO communication."""

    def __init__(self):
        super().__init__()
        self.title("Gesture-Powered Virtual Game Control")
        self.attributes("-fullscreen", True)
        self.configure(bg="#000000")

        self._gif   = GifManager(self)
        self._users = get_all_users()

        # ── key bindings ──────────────────────────────────────────────────────
        self.bind("<Escape>", self._on_exit)
        self.bind("q",        self._on_exit)
        self.bind("<F11>",    lambda e: self.attributes(
            "-fullscreen", not self.attributes("-fullscreen")))
        for k in "0123":
            self.bind(k, lambda e, uid=int(k): self._simulate_tuio(uid))
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

        # ── start ─────────────────────────────────────────────────────────────
        self._launch_reactivision()

        # ── VR bridge ─────────────────────────────────────────────────────────
        self._vr_bridge = VRBridge(dry_run=not VR_BRIDGE_ENABLED)

        self._listener = TUIOListener(
            on_marker_detected=lambda fid:       self.after(0, lambda: self._on_marker_detected(fid)),
            on_marker_rotated= lambda d, fid:    self.after(0, lambda: self._on_marker_rotated(d, fid)),
            on_marker_removed= lambda fid:       self.after(0, lambda: self._on_marker_removed(fid)),
            on_marker_moved=   lambda fid, x, y, a: self._vr_bridge.enqueue(fid, x, y, a),
            host=TUIO_HOST,
            port=TUIO_PORT,
        )
        self._listener.start()
        self._show_main_menu()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _on_exit(self, _event=None):
        self._vr_bridge.stop()
        self._listener.stop()
        self.destroy()

    # ── reacTIVision ──────────────────────────────────────────────────────────

    def _launch_reactivision(self):
        if not REACTVISION_EXE:
            print("[WARN] reacTIVision not found — set 'reactvision_exe' in config.json")
            return
        try:
            kwargs: dict = {"cwd": __import__("os").path.dirname(REACTVISION_EXE)}
            if IS_WINDOWS:
                si = subprocess.STARTUPINFO()
                si.dwFlags    |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 7   # SW_SHOWMINNOACTIVE
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
                kwargs["startupinfo"]   = si
            subprocess.Popen([REACTVISION_EXE], **kwargs)
            time.sleep(1.5)
            print("[INFO] reacTIVision launched (minimised).")
        except Exception as exc:
            print(f"[ERROR] Could not launch reacTIVision: {exc}")

    # ── TUIO callbacks (dispatched to main thread via after(0, ...)) ──────────

    def _on_marker_detected(self, fid: int):
        if self._current_user is None and fid in self._users:
            self._current_user = fid
            self._show_user_page(fid)
        elif self._current_user == fid:
            self._set_tuio_light(True)

    def _on_marker_removed(self, fid: int):
        if self._current_user == fid:
            self._set_tuio_light(False)

    def _on_marker_rotated(self, direction: str, fid: int):
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
        if self._current_user is None or self._rotation_triggered:
            return
        self._rotation_triggered = True
        if direction == "left":
            self._current_user = None
            self._show_main_menu()
        else:
            self._do_launch_game()

    # ── screen helpers ────────────────────────────────────────────────────────

    def _clear_screen(self):
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

        self._start_gif(canvas, MAIN_BK_GIF, sw, sh, canvas)

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
        tk.Label(r_body, text="Launch Beat Saber",
                 font=("Consolas", int(sh * 0.014)),
                 fg=u["bg"], bg=u["glow"]).pack(pady=(2, 6))
        tk.Canvas(right_box, height=2, bg=u["header_bg"],
                  highlightthickness=0).pack(fill="x", side="bottom")

        # Beat Saber icon
        border     = 4
        icon_sz    = int(bar_h * 0.62)
        icon_pad_y = (bar_h - icon_sz - border * 2) // 2
        icon_photo = load_image(GAME_ICON, icon_sz, icon_sz)

        icon_wrapper = tk.Frame(game_bar, bg=u["header_bg"])
        icon_wrapper.pack(side="right", padx=int(sw * 0.032), pady=icon_pad_y)
        tk.Label(icon_wrapper, text="BEAT SABER",
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

        self._start_gif(body_cv, u["gif"], sw, body_h, frame)

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

    # ── game launch ───────────────────────────────────────────────────────────

    def _do_launch_game(self):
        name    = self._users[self._current_user]["name"] \
                  if self._current_user is not None else ""
        # Start the VR bridge when the game launches
        if VR_BRIDGE_ENABLED and not self._vr_bridge.is_running:
            self._vr_bridge.start()
        success, error_msg = launch_game(character_name=name)
        if success:
            self.attributes("-fullscreen", False)
            self.iconify()
            self._rotation_triggered = False
        else:
            self._show_error(error_msg)

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
            "       Use keyboard keys  0 / 1 / 2 / 3  to simulate markers.\n"
        )
    app = HCIApp()
    app.mainloop()
