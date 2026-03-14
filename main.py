#!/usr/bin/env python3
"""
Gesture-Powered Virtual Game Control
─────────────────────────────────────────────────────────────────────────────
Fullscreen Tkinter GUI driven by TUIO fiducial markers via reacTIVision.

  • Launches reacTIVision.exe in the background automatically.
  • Listens for TUIO OSC messages on UDP port 3333.
  • Main menu waits for a marker → routes to the matching user's personal page.
  • Each user page has its own animated GIF background and colour theme.
  • Rotate the TUIO marker LEFT  → return to the main menu.
  • Rotate the TUIO marker RIGHT → launch Beat Saber immediately.

Keyboard shortcuts (for testing without hardware):
  0 / 1 / 2 / 3  – simulate placing / removing TUIO marker for that user
  ← Left arrow   – simulate rotating LEFT  (back to menu)
  → Right arrow  – simulate rotating RIGHT (launch game)
  ESC / Q        – exit
  F11            – toggle fullscreen
"""

import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from PIL import Image, ImageTk

# ── OSC / TUIO library ────────────────────────────────────────────────────────
try:
    from pythonosc import dispatcher as osc_dispatcher
    from pythonosc.osc_server import BlockingOSCUDPServer
    OSC_AVAILABLE = True
except ImportError:
    OSC_AVAILABLE = False

# ═════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  ← edit the paths below to match your setup
# ═════════════════════════════════════════════════════════════════════════════

REACTVISION_EXE = r"D:\HCI\reacTIVision-1.5.1-win64\reacTIVision.exe"
GAME_EXE        = r"D:\DeskDump\Minecraft Launcher\Content\Minecraft.exe"

TUIO_HOST          = "0.0.0.0"
TUIO_PORT          = 3333
ROTATION_THRESHOLD = 0.5   # rad/s — increase to reduce accidental triggers

# ── Asset paths ───────────────────────────────────────────────────────────────
_A          = os.path.join(os.path.dirname(__file__), "Assests")
MAIN_BK_GIF = os.path.join(_A, "bk gifs",    "main bk.gif")
GAME_ICON   = os.path.join(_A, "game icons", "Beat_Saber_logo.jpg")

# ── Users ─────────────────────────────────────────────────────────────────────
# Each user is bound to the TUIO fiducial marker whose class-ID matches the key.
USERS = {
    0: {
        "name":      "Alex",
        "bg":        "#0d1b2a",
        "header_bg": "#03045e",
        "accent":    "#00b4d8",
        "glow":      "#90e0ef",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "blue animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "blue user.jpg"),
    },
    1: {
        "name":      "Blake",
        "bg":        "#1b4332",
        "header_bg": "#081c15",
        "accent":    "#52b788",
        "glow":      "#d8f3dc",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "green animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "green user.jpg"),
    },
    2: {
        "name":      "Casey",
        "bg":        "#370617",
        "header_bg": "#03071e",
        "accent":    "#f48c06",
        "glow":      "#ffba08",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "orange animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "orange user.jpg"),
    },
    3: {
        "name":      "Dana",
        "bg":        "#240046",
        "header_bg": "#10002b",
        "accent":    "#c77dff",
        "glow":      "#e0aaff",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "purple animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "purple user.jpg"),
    },
}

# ═════════════════════════════════════════════════════════════════════════════


class HCIApp(tk.Tk):
    """Root window – manages screen transitions and TUIO communication."""

    def __init__(self):
        super().__init__()
        self.title("Gesture-Powered Virtual Game Control")
        self.attributes("-fullscreen", True)
        self.configure(bg="#000000")

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
        self._event_q            = queue.Queue()
        self._active_objs        = {}
        self._current_user       = None
        self._screen             = None
        self._osc_server         = None
        self._rotation_triggered = False
        self._tuio_light_cv      = None
        self._tuio_light_oval    = None
        self._gif_cache     = {}   # (path,w,h) → (frames, delays)
        self._gif_pil_cache = {}   # (path,w,h) → [(pil_img, delay), ...]  (bg thread)

        # ── start ─────────────────────────────────────────────────────────────
        self._launch_reactivision()
        self._show_main_menu()
        self._start_tuio_listener()
        self._poll_events()
        # Pre-load all GIFs in background so switching screens is instant
        self.after(300, self._preload_gifs_start)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _on_exit(self, _event=None):
        if self._osc_server:
            try:
                self._osc_server.shutdown()
            except Exception:
                pass
        self.destroy()

    # ── reacTIVision ──────────────────────────────────────────────────────────

    def _launch_reactivision(self):
        if not os.path.exists(REACTVISION_EXE):
            print(f"[WARN] reacTIVision not found: {REACTVISION_EXE}")
            return
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags    |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
            subprocess.Popen(
                [REACTVISION_EXE],
                cwd=os.path.dirname(REACTVISION_EXE),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=si,
            )
            time.sleep(1.5)
            print("[INFO] reacTIVision launched (minimised).")
        except Exception as exc:
            print(f"[ERROR] Could not launch reacTIVision: {exc}")

    # ── TUIO / OSC ────────────────────────────────────────────────────────────

    def _start_tuio_listener(self):
        if not OSC_AVAILABLE:
            print("[WARN] python-osc not installed. Press 0-3 to simulate markers.")
            return
        d = osc_dispatcher.Dispatcher()
        d.map("/tuio/2Dobj", self._osc_2dobj)
        d.set_default_handler(lambda *a: None)

        def _serve():
            try:
                self._osc_server = BlockingOSCUDPServer((TUIO_HOST, TUIO_PORT), d)
                print(f"[INFO] TUIO listener on port {TUIO_PORT}.")
                self._osc_server.serve_forever()
            except Exception as exc:
                print(f"[ERROR] OSC server: {exc}")

        threading.Thread(target=_serve, daemon=True).start()

    def _osc_2dobj(self, _address, *args):
        if not args:
            return
        msg_type = args[0]

        if msg_type == "set" and len(args) >= 3:
            session_id = args[1]
            class_id   = int(args[2])
            va         = float(args[8]) if len(args) > 8 else 0.0

            if session_id not in self._active_objs:
                self._active_objs[session_id] = class_id
                self._event_q.put(("added", class_id))
            elif not self._rotation_triggered and self._current_user == class_id:
                if va > ROTATION_THRESHOLD:
                    self._rotation_triggered = True
                    self._event_q.put(("rotate_right", class_id))
                elif va < -ROTATION_THRESHOLD:
                    self._rotation_triggered = True
                    self._event_q.put(("rotate_left", class_id))

        elif msg_type == "alive":
            alive = set(args[1:])
            for sid in list(self._active_objs.keys()):
                if sid not in alive:
                    cid = self._active_objs.pop(sid)
                    self._event_q.put(("removed", cid))

    def _poll_events(self):
        try:
            while True:
                kind, class_id = self._event_q.get_nowait()

                if kind == "added" and class_id in USERS:
                    if self._current_user is None:
                        self._current_user = class_id
                        self._show_user_page(class_id)
                    elif self._current_user == class_id:
                        self._set_tuio_light(True)

                elif kind == "removed" and self._current_user == class_id:
                    self._set_tuio_light(False)

                elif kind == "rotate_left" and self._current_user == class_id:
                    self._current_user = None
                    self._show_main_menu()

                elif kind == "rotate_right" and self._current_user == class_id:
                    self._launch_game()

        except queue.Empty:
            pass
        self.after(50, self._poll_events)

    def _simulate_tuio(self, class_id):
        if self._current_user is None and class_id in USERS:
            self._current_user = class_id
            self._show_user_page(class_id)
        elif self._current_user == class_id:
            self._current_user = None
            self._show_main_menu()

    def _simulate_rotation(self, direction):
        if self._current_user is None or self._rotation_triggered:
            return
        self._rotation_triggered = True
        if direction == "left":
            self._current_user = None
            self._show_main_menu()
        else:
            self._launch_game()

    # ── screen helpers ────────────────────────────────────────────────────────

    def _clear_screen(self):
        self._rotation_triggered = False
        self._tuio_light_cv      = None
        self._tuio_light_oval    = None
        if self._screen and self._screen.winfo_exists():
            self._screen.destroy()
        self._screen = None

    def _set_tuio_light(self, active: bool):
        if self._tuio_light_cv is None:
            return
        try:
            color = "#00ff00" if active else "#ff2222"
            self._tuio_light_cv.itemconfig(self._tuio_light_oval, fill=color)
        except tk.TclError:
            pass

    def _sw(self):
        return self.winfo_screenwidth()

    def _sh(self):
        return self.winfo_screenheight()

    # ── GIF helpers ───────────────────────────────────────────────────────────

    # ── GIF pre-loader ────────────────────────────────────────────────────────

    def _preload_gifs_start(self):
        """Step 1 — decode + resize all GIF frames in a background thread (PIL only)."""
        sw, sh   = self._sw(), self._sh()
        body_h   = sh - int(sh * 0.10) - int(sh * 0.22)
        to_load  = [(MAIN_BK_GIF, sw, sh)] + [
            (u["gif"], sw, body_h) for u in USERS.values()
        ]

        def _bg():
            for path, w, h in to_load:
                key = (path, w, h)
                if key in self._gif_cache or key in self._gif_pil_cache:
                    continue
                pil_frames = []
                try:
                    gif = Image.open(path)
                    while True:
                        pil_frames.append((
                            gif.copy().resize((w, h), Image.BILINEAR),
                            gif.info.get("duration", 50),
                        ))
                        gif.seek(gif.tell() + 1)
                except EOFError:
                    pass
                except Exception as exc:
                    print(f"[WARN] GIF pre-load failed ({path}): {exc}")
                if pil_frames:
                    self._gif_pil_cache[key] = pil_frames
            # All PIL work done — schedule PhotoImage conversion on main thread
            self.after(0, self._preload_gifs_convert)

        threading.Thread(target=_bg, daemon=True).start()

    def _preload_gifs_convert(self, pending=None, batch=8):
        """Step 2 — convert PIL frames → PhotoImage in small batches (main thread)."""
        if pending is None:
            pending = [
                (k, list(v))
                for k, v in self._gif_pil_cache.items()
                if k not in self._gif_cache
            ]
        if not pending:
            self._gif_pil_cache.clear()
            print("[INFO] GIF pre-load complete.")
            return

        key, pil_list = pending[0]
        frames, delays = self._gif_cache.get(key, ([], []))
        converted = 0
        while pil_list and converted < batch:
            pf, d = pil_list.pop(0)
            frames.append(ImageTk.PhotoImage(pf))
            delays.append(d)
            converted += 1
        self._gif_cache[key] = (frames, delays)

        if pil_list:
            pending[0] = (key, pil_list)   # still frames left for this GIF
        else:
            pending.pop(0)

        self.after(5, lambda: self._preload_gifs_convert(pending, batch))

    # ── GIF load (on-demand, uses cache if pre-load finished) ─────────────────

    def _load_gif_frames(self, path, width, height):
        """Return cached frames, or load synchronously if not pre-loaded yet."""
        key = (path, width, height)
        if key in self._gif_cache:
            return self._gif_cache[key]

        # Pre-load may have finished the PIL work but not the conversion yet
        if key in self._gif_pil_cache:
            pil_list = self._gif_pil_cache.pop(key)
            frames  = [ImageTk.PhotoImage(pf) for pf, _ in pil_list]
            delays  = [d for _, d in pil_list]
            self._gif_cache[key] = (frames, delays)
            return frames, delays

        # Full synchronous fallback (first run before pre-load finishes)
        frames, delays = [], []
        try:
            gif = Image.open(path)
            while True:
                frames.append(ImageTk.PhotoImage(
                    gif.copy().resize((width, height), Image.BILINEAR)
                ))
                delays.append(gif.info.get("duration", 50))
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        except Exception as exc:
            print(f"[WARN] GIF load failed ({path}): {exc}")
        if frames:
            self._gif_cache[key] = (frames, delays)
        return frames, delays

    def _animate_gif(self, canvas, frames, delays, idx, item, owner):
        """Cycle animated GIF frames on a canvas image item."""
        if self._screen is not owner:
            return
        try:
            canvas.itemconfig(item, image=frames[idx])
            nxt = (idx + 1) % len(frames)
            self.after(delays[idx],
                       lambda: self._animate_gif(canvas, frames, delays, nxt, item, owner))
        except tk.TclError:
            pass

    def _load_avatar(self, path, size, border_color):
        """Load an image, add a coloured border, return PhotoImage."""
        try:
            img = Image.open(path).resize((size - 6, size - 6), Image.LANCZOS)
            bordered = Image.new("RGB", (size, size), border_color)
            bordered.paste(img, (3, 3))
            return ImageTk.PhotoImage(bordered)
        except Exception as exc:
            print(f"[WARN] Avatar load failed ({path}): {exc}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN MENU
    # ══════════════════════════════════════════════════════════════════════════

    def _show_main_menu(self):
        self._clear_screen()
        sw, sh = self._sw(), self._sh()

        # Root canvas — the screen itself
        canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._screen = canvas

        # ── animated GIF background ───────────────────────────────────────────
        frames, delays = self._load_gif_frames(MAIN_BK_GIF, sw, sh)
        if frames:
            bg_item = canvas.create_image(0, 0, anchor="nw", image=frames[0])
            canvas.gif_frames = frames       # prevent GC
            self._animate_gif(canvas, frames, delays, 0, bg_item, canvas)

        # Semi-transparent dark overlay so text stays readable
        canvas.create_rectangle(0, 0, sw, sh,
                                 fill="#000000", stipple="gray50", outline="")

        # ── title ─────────────────────────────────────────────────────────────
        canvas.create_text(
            sw // 2, int(sh * 0.20),
            text="GESTURE-POWERED  VIRTUAL  GAME  CONTROL",
            font=("Bahnschrift", int(sh * 0.040), "bold"),
            fill="#ffffff",
        )

        # separator line
        lx = int(sw * 0.225)
        canvas.create_line(lx, int(sh * 0.29), sw - lx, int(sh * 0.29),
                           fill="#444444", width=2)

        # ── welcome / instructions ─────────────────────────────────────────────
        canvas.create_text(
            sw // 2, int(sh * 0.37),
            text="Welcome, User!",
            font=("Bahnschrift", int(sh * 0.044), "bold"),
            fill="#00b4d8",
        )
        canvas.create_text(
            sw // 2, int(sh * 0.46),
            text="Please sign in by holding a TUIO marker in front of the camera.",
            font=("Bahnschrift", int(sh * 0.022)),
            fill="#aaaaaa",
        )

        # ── user cards row ────────────────────────────────────────────────────
        canvas.create_text(
            sw // 2, int(sh * 0.565),
            text="REGISTERED USERS",
            font=("Consolas", int(sh * 0.014), "bold"),
            fill="#555555",
        )

        card_w   = int(sw  * 0.130)
        card_h   = int(sh  * 0.200)
        gap      = int(sw  * 0.020)
        total_w  = len(USERS) * card_w + (len(USERS) - 1) * gap
        start_x  = sw // 2 - total_w // 2
        card_top = int(sh * 0.595)
        av_sz    = int(card_h * 0.48)

        for i, (uid, user) in enumerate(USERS.items()):
            cx = start_x + i * (card_w + gap)

            card = tk.Frame(canvas, bg=user["header_bg"],
                            width=card_w, height=card_h)
            card.pack_propagate(False)

            # Avatar thumbnail
            av = self._load_avatar(user["avatar"], av_sz, user["accent"])
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

        # ── listening blinker ─────────────────────────────────────────────────
        blink_lbl = tk.Label(canvas,
                             text="●  LISTENING FOR TUIO",
                             font=("Consolas", int(sh * 0.017)),
                             bg="#000000")
        canvas.create_window(sw // 2, int(sh * 0.875),
                             anchor="center", window=blink_lbl)
        self._blink(blink_lbl, canvas, green=True)

    def _blink(self, label, owner, green=True):
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

    def _show_user_page(self, user_id):
        self._clear_screen()
        u  = USERS[user_id]
        sw = self._sw()
        sh = self._sh()

        frame = tk.Frame(self, bg=u["bg"])
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._screen = frame

        # ── header bar (opaque dark panel) ────────────────────────────────────
        hdr_h = int(sh * 0.10)
        header = tk.Frame(frame, bg=u["header_bg"], height=hdr_h)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="  GESTURE-POWERED  VIRTUAL  GAME  CONTROL",
            font=("Bahnschrift", int(sh * 0.022), "bold"),
            fg=u["accent"], bg=u["header_bg"],
        ).pack(side="left", padx=int(sw * 0.022), pady=int(hdr_h * 0.25))

        # TUIO status dot — right side of header
        dot_sz  = int(hdr_h * 0.36)
        ind_frm = tk.Frame(header, bg=u["header_bg"])
        ind_frm.pack(side="right", padx=int(sw * 0.030))

        dot_cv = tk.Canvas(ind_frm, width=dot_sz, height=dot_sz,
                           bg=u["header_bg"], highlightthickness=0)
        dot_cv.pack(side="left", pady=(hdr_h - dot_sz) // 2)
        dot_oval = dot_cv.create_oval(0, 0, dot_sz, dot_sz,
                                      fill="#00ff00", outline="#005500", width=2)
        tk.Label(ind_frm,
                 text="TUIO READING",
                 font=("Consolas", int(sh * 0.016), "bold"),
                 fg="#aaaaaa", bg=u["header_bg"]).pack(side="left", padx=(8, 0))
        self._tuio_light_cv   = dot_cv
        self._tuio_light_oval = dot_oval

        # ── game bar (opaque dark panel at bottom) ─────────────────────────────
        bar_h    = int(sh * 0.22)
        game_bar = tk.Frame(frame, bg=u["header_bg"], height=bar_h)
        game_bar.pack(fill="x", side="bottom")
        game_bar.pack_propagate(False)

        # Beat Saber icon inside an accent-coloured frame
        border   = 4
        icon_sz  = int(bar_h * 0.72)
        icon_pad_y = (bar_h - icon_sz - border * 2) // 2
        try:
            pil_icon   = Image.open(GAME_ICON).resize((icon_sz, icon_sz), Image.LANCZOS)
            icon_photo = ImageTk.PhotoImage(pil_icon)
        except Exception as exc:
            print(f"[WARN] Game icon load failed: {exc}")
            icon_photo = None

        icon_frame = tk.Frame(game_bar, bg=u["accent"],
                              padx=border, pady=border)
        icon_frame.pack(side="left", padx=int(sw * 0.028), pady=icon_pad_y)

        icon_lbl = tk.Label(icon_frame, image=icon_photo,
                            bg=u["header_bg"], bd=0)
        icon_lbl.image = icon_photo
        icon_lbl.pack()

        # Game label
        lbl_blk = tk.Frame(game_bar, bg=u["header_bg"])
        lbl_blk.pack(side="left", padx=int(sw * 0.006))
        tk.Label(lbl_blk, text="BEAT SABER",
                 font=("Bahnschrift", int(sh * 0.032), "bold"),
                 fg=u["accent"], bg=u["header_bg"]).pack(anchor="w")
        tk.Label(lbl_blk, text="Beat Saber",
                 font=("Consolas", int(sh * 0.013)),
                 fg="#777777", bg=u["header_bg"]).pack(anchor="w")

        # Rotation hints
        hints   = tk.Frame(game_bar, bg=u["header_bg"])
        hints.pack(side="right", padx=int(sw * 0.035), expand=True, fill="both")
        pad_y   = int(bar_h * 0.18)

        btn_pad_y = int(bar_h * 0.14)
        btn_pad_x = int(sw * 0.010)

        # ◄ Left button
        left_box = tk.Frame(hints, bg=u["bg"],
                            highlightthickness=2,
                            highlightbackground=u["accent"])
        left_box.pack(side="left", expand=True, fill="both",
                      padx=btn_pad_x, pady=btn_pad_y)
        # top glow strip
        top_l = tk.Canvas(left_box, height=3, bg=u["accent"], highlightthickness=0)
        top_l.pack(fill="x")
        tk.Label(left_box, text="◄   ROTATE LEFT",
                 font=("Bahnschrift", int(sh * 0.024), "bold"),
                 fg=u["accent"], bg=u["bg"]).pack(expand=True, pady=(6, 2))
        tk.Label(left_box, text="Back to Main Menu",
                 font=("Consolas", int(sh * 0.013)),
                 fg="#999999", bg=u["bg"]).pack(pady=(0, int(sh * 0.010)))

        # Right button ►
        right_box = tk.Frame(hints, bg=u["bg"],
                             highlightthickness=2,
                             highlightbackground=u["glow"])
        right_box.pack(side="right", expand=True, fill="both",
                       padx=btn_pad_x, pady=btn_pad_y)
        # top glow strip
        top_r = tk.Canvas(right_box, height=3, bg=u["glow"], highlightthickness=0)
        top_r.pack(fill="x")
        tk.Label(right_box, text="ROTATE RIGHT   ►",
                 font=("Bahnschrift", int(sh * 0.024), "bold"),
                 fg=u["glow"], bg=u["bg"]).pack(expand=True, pady=(6, 2))
        tk.Label(right_box, text="Launch Beat Saber",
                 font=("Consolas", int(sh * 0.013)),
                 fg="#999999", bg=u["bg"]).pack(pady=(0, int(sh * 0.010)))

        # ── body canvas — animated GIF with text drawn on top ─────────────────
        body_h = sh - hdr_h - bar_h
        body_cv = tk.Canvas(frame, width=sw, height=body_h,
                            bg=u["bg"], highlightthickness=0)
        body_cv.pack(fill="both", expand=True)

        frames, delays = self._load_gif_frames(u["gif"], sw, body_h)
        if frames:
            gif_item = body_cv.create_image(0, 0, anchor="nw", image=frames[0])
            body_cv.gif_frames = frames
            self._animate_gif(body_cv, frames, delays, 0, gif_item, frame)

        # Dark overlay on body for readability
        body_cv.create_rectangle(0, 0, sw, body_h,
                                  fill="#000000", stipple="gray25", outline="")

        # User avatar
        av_sz = int(body_h * 0.38)
        av    = self._load_avatar(u["avatar"], av_sz, u["accent"])
        if av:
            av_item = body_cv.create_image(sw // 2, int(body_h * 0.22),
                                           anchor="center", image=av)
            body_cv.av_photo = av    # prevent GC

        # Welcome text
        body_cv.create_text(
            sw // 2, int(body_h * 0.47),
            text="Welcome,",
            font=("Bahnschrift", int(sh * 0.038)),
            fill=u["fg"],
        )
        body_cv.create_text(
            sw // 2, int(body_h * 0.615),
            text=u["name"],
            font=("Impact", int(sh * 0.095), "bold"),
            fill=u["accent"],
        )
        body_cv.create_text(
            sw // 2, int(body_h * 0.76),
            text=f"TUIO marker  #{user_id}  recognised",
            font=("Consolas", int(sh * 0.016)),
            fill=u["glow"],
        )

        # Accent divider
        div_w = int(sw * 0.40)
        div_x = sw // 2 - div_w // 2
        div_y = int(body_h * 0.855)
        body_cv.create_rectangle(div_x, div_y, div_x + div_w, div_y + 4,
                                  fill=u["accent"], outline="")

        self._u_theme = u

    # ── game launch ───────────────────────────────────────────────────────────

    def _launch_game(self):
        if os.path.exists(GAME_EXE):
            try:
                subprocess.Popen([GAME_EXE], cwd=os.path.dirname(GAME_EXE))
                print(f"[INFO] Game launched: {GAME_EXE}")
                self.attributes("-fullscreen", False)
                self.iconify()
                self._rotation_triggered = False
            except Exception as exc:
                print(f"[ERROR] Could not launch game: {exc}")
                self._show_error(f"Launch failed:\n{exc}")
        else:
            print(f"[WARN] Game exe not found at: {GAME_EXE}")
            self._show_error(
                f"Game executable not found.\n\nSet GAME_EXE in main.py:\n{GAME_EXE}"
            )

    def _show_error(self, message):
        if not (self._screen and self._screen.winfo_exists()):
            return
        u = self._u_theme
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


# ═════════════════════════════════════════════════════════════════════════════

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
