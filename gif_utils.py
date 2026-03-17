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

    def _convert_batch(self, pending: list | None = None, batch: int = 8):
        """Convert PIL frames → PhotoImage in small batches on the main thread
        to avoid freezing the UI. This is called recursively via root.after()."""
        
        # 1. Initialize pending list if this is the start of a conversion cycle
        if pending is None:
            pending = [
                (k, list(v))
                for k, v in self._gif_pil_cache.items()
                if k not in self._gif_cache
            ]
            
        # 2. If no GIFs in current 'pending' list, or pending list is exhausted:
        if not pending:
            # Re-check PIL cache to see if background thread finished more work
            remaining_pil = [
                (k, list(v))
                for k, v in self._gif_pil_cache.items()
                if k not in self._gif_cache
            ]
            if remaining_pil:
                # Keep going with new items
                self._root.after(10, lambda: self._convert_batch(remaining_pil, batch))
                return
            
            # Truly finished
            self._gif_pil_cache.clear()
            print("[GifManager] Pre-load complete.")
            return

        # 3. Process first GIF in pending list
        key, pil_list = pending[0]
        frames, delays = self._gif_cache.get(key, ([], []))
        converted = 0
        while pil_list and converted < batch:
            pf, d = pil_list.pop(0)
            frames.append(ImageTk.PhotoImage(pf))
            delays.append(d)
            converted += 1
        self._gif_cache[key] = (frames, delays)

        # 4. Advance pending list and loop
        if not pil_list:
            pending.pop(0)
            
        self._root.after(5, lambda: self._convert_batch(pending, batch))

    def evict(self, path: str, width: int, height: int):
        """Remove a cached GIF from memory to free RAM."""
        key = (path, width, height)
        self._gif_cache.pop(key, None)
        self._gif_pil_cache.pop(key, None)

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


# ── Global image cache to avoid repeated slow PIL resizes ────────────────────
_image_cache: dict[tuple, ImageTk.PhotoImage] = {}


def load_avatar(path: str, size: int, border_color: str):
    """Load an image, add a solid-colour border, and return a PhotoImage.
    Uses a global cache to avoid redrawing/resizing on every screen swap."""
    key = (path, size, border_color, "avatar")
    if key in _image_cache:
        return _image_cache[key]

    try:
        img      = Image.open(path).resize((size - 6, size - 6), Image.LANCZOS)
        bordered = Image.new("RGB", (size, size), border_color)
        bordered.paste(img, (3, 3))
        photo = ImageTk.PhotoImage(bordered)
        _image_cache[key] = photo
        return photo
    except Exception as exc:
        print(f"[GifManager] Avatar load failed ({path}): {exc}")
        return None


def load_image(path: str, width: int, height: int):
    """Load and resize an image, return a PhotoImage (no border).
    Uses a global cache for performance."""
    key = (path, width, height, "plain")
    if key in _image_cache:
        return _image_cache[key]

    try:
        img   = Image.open(path).resize((width, height), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        _image_cache[key] = photo
        return photo
    except Exception as exc:
        print(f"[GifManager] Image load failed ({path}): {exc}")
        return None
