"""
gif_utils.py
------------
GIF loading, frame caching, and Tkinter animation helpers.

GifManager
  preload(paths_sizes)  – start background PIL decoding for a list of GIFs
  load(path, w, h)      – return (frames, delays) from cache or load on demand
  animate(...)          – cycle frames on a canvas image item

Standalone helpers
  load_avatar(path, size, border_color)  – bordered square thumbnail
  load_image(path, width, height)        – plain resized PhotoImage
"""

import threading
import tkinter as tk
from PIL import Image, ImageTk


class GifManager:
    """Pre-loads and caches animated GIF frames for smooth Tkinter playback."""

    def __init__(self, root: tk.Tk):
        self._root          = root
        self._gif_cache:     dict = {}   # (path, w, h) → (frames, delays)
        self._gif_pil_cache: dict = {}   # (path, w, h) → [(pil_img, delay), ...]

    # ── Pre-loading ───────────────────────────────────────────────────────────

    def preload(self, paths_sizes: list[tuple[str, int, int]]):
        """Decode + resize all GIF frames in a background thread, then
        convert PIL images → PhotoImage in small batches on the main thread."""

        def _bg():
            for path, w, h in paths_sizes:
                key = (path, w, h)
                if key in self._gif_cache or key in self._gif_pil_cache:
                    continue
                pil_frames: list = []
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
                    print(f"[GifManager] Pre-load failed ({path}): {exc}")
                if pil_frames:
                    self._gif_pil_cache[key] = pil_frames
            self._root.after(0, self._convert_batch)

        threading.Thread(target=_bg, daemon=True).start()

    def _convert_batch(self, pending=None, batch: int = 8):
        """Convert PIL frames → PhotoImage in small batches on the main thread
        to avoid freezing the UI."""
        if pending is None:
            pending = [
                (k, list(v))
                for k, v in self._gif_pil_cache.items()
                if k not in self._gif_cache
            ]
        if not pending:
            self._gif_pil_cache.clear()
            print("[GifManager] Pre-load complete.")
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
            pending[0] = (key, pil_list)
        else:
            pending.pop(0)

        self._root.after(5, lambda: self._convert_batch(pending, batch))

    # ── On-demand loading ─────────────────────────────────────────────────────

    def load(self, path: str, width: int, height: int) -> tuple[list, list]:
        """Return (frames, delays) from cache, or load synchronously if needed."""
        key = (path, width, height)

        if key in self._gif_cache:
            return self._gif_cache[key]

        # Pre-load may have finished PIL work but not the PhotoImage conversion
        if key in self._gif_pil_cache:
            pil_list = self._gif_pil_cache.pop(key)
            frames   = [ImageTk.PhotoImage(pf) for pf, _ in pil_list]
            delays   = [d for _, d in pil_list]
            self._gif_cache[key] = (frames, delays)
            return frames, delays

        # Full synchronous fallback (fires before pre-load finishes)
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
            print(f"[GifManager] Load failed ({path}): {exc}")
        if frames:
            self._gif_cache[key] = (frames, delays)
        return frames, delays

    # ── Animation ─────────────────────────────────────────────────────────────

    def animate(
        self,
        canvas: tk.Canvas,
        frames: list,
        delays: list,
        idx: int,
        item: int,
        is_alive,          # callable() → bool — return False to stop
    ):
        """Cycle animated GIF frames on a canvas image item.
        Stops automatically when is_alive() returns False or the canvas is gone.
        """
        if not is_alive():
            return
        try:
            canvas.itemconfig(item, image=frames[idx])
            nxt = (idx + 1) % len(frames)
            self._root.after(
                delays[idx],
                lambda: self.animate(canvas, frames, delays, nxt, item, is_alive),
            )
        except tk.TclError:
            pass


# ── Standalone image helpers ──────────────────────────────────────────────────

def load_avatar(path: str, size: int, border_color: str):
    """Load an image, add a solid-colour border, and return a PhotoImage."""
    try:
        img      = Image.open(path).resize((size - 6, size - 6), Image.LANCZOS)
        bordered = Image.new("RGB", (size, size), border_color)
        bordered.paste(img, (3, 3))
        return ImageTk.PhotoImage(bordered)
    except Exception as exc:
        print(f"[GifManager] Avatar load failed ({path}): {exc}")
        return None


def load_image(path: str, width: int, height: int):
    """Load and resize an image, return a PhotoImage (no border)."""
    try:
        img = Image.open(path).resize((width, height), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as exc:
        print(f"[GifManager] Image load failed ({path}): {exc}")
        return None
