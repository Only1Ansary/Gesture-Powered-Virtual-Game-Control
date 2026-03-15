"""
tuio_listener.py
----------------
TUIO listener backed by python-osc running on a background thread.

Rotation is detected using instantaneous angular velocity (va) from the
TUIO 2Dobj 'set' message (argument index 8).  The threshold is read from
config.json as 'rotation_threshold' (default 0.5 rad/s).

Callbacks (invoked from the background thread — use after(0, ...) in Tkinter
to dispatch safely to the main thread):
  on_marker_detected(fiducial_id: int)
  on_marker_rotated(direction: str, fiducial_id: int)   direction = 'left'|'right'
  on_marker_removed(fiducial_id: int)
"""

import threading
import time

try:
    from pythonosc import dispatcher as osc_dispatcher
    from pythonosc.osc_server import BlockingOSCUDPServer
    OSC_AVAILABLE = True
except ImportError:
    OSC_AVAILABLE = False

from config import ROTATION_THRESHOLD

ROTATION_COOLDOWN = 1.5   # seconds to ignore further rotation events after one fires


class TUIOListener:
    """Wraps python-osc in a background thread and emits clean TUIO callbacks."""

    def __init__(
        self,
        on_marker_detected=None,
        on_marker_rotated=None,
        on_marker_removed=None,
        host: str = "0.0.0.0",
        port: int = 3333,
    ):
        self.host = host
        self.port = port
        self.on_marker_detected = on_marker_detected   # callable(int)
        self.on_marker_rotated  = on_marker_rotated    # callable(str, int)
        self.on_marker_removed  = on_marker_removed    # callable(int)

        self._server  = None
        self._thread  = None
        self._running = False

        # session_id → fiducial_id for currently tracked objects
        self._object_map: dict = {}
        # fiducial_id → timestamp of last rotation event fired
        self._last_rotated: dict = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Bind the UDP socket and start the background listener thread."""
        if not OSC_AVAILABLE:
            print("[TUIOListener] python-osc not installed — hardware TUIO disabled.")
            return
        if self._running:
            return

        d = osc_dispatcher.Dispatcher()
        d.map("/tuio/2Dobj", self._handle_2dobj)
        d.set_default_handler(lambda *a: None)

        try:
            self._server = BlockingOSCUDPServer((self.host, self.port), d)
        except Exception as exc:
            print(f"[TUIOListener] Could not bind to {self.host}:{self.port}: {exc}")
            return

        self._running = True
        self._thread  = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="TUIOListener",
        )
        self._thread.start()
        print(f"[TUIOListener] Listening on {self.host}:{self.port}")

    def stop(self):
        """Shut down the OSC server and join the background thread."""
        self._running = False
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        print("[TUIOListener] Stopped.")

    # ── OSC handler ───────────────────────────────────────────────────────────

    def _handle_2dobj(self, _address, *args):
        """Process a /tuio/2Dobj message dispatched by python-osc."""
        if not args:
            return
        command = args[0]

        if command == "set" and len(args) >= 3:
            # args: ['set', session_id, fiducial_id, x, y, angle, X, Y, A, ...]
            #  index:   0        1           2        3  4    5    6  7  8
            session_id  = args[1]
            fiducial_id = int(args[2])
            va          = float(args[8]) if len(args) > 8 else 0.0

            if session_id not in self._object_map:
                self._object_map[session_id] = fiducial_id
                print(f"[TUIOListener] Detected marker ID={fiducial_id}")
                if callable(self.on_marker_detected):
                    self.on_marker_detected(fiducial_id)
            else:
                if va > ROTATION_THRESHOLD:
                    self._fire_rotated("right", fiducial_id, va)
                elif va < -ROTATION_THRESHOLD:
                    self._fire_rotated("left", fiducial_id, va)

        elif command == "alive":
            new_alive    = {args[i] for i in range(1, len(args))}
            removed_sids = set(self._object_map.keys()) - new_alive
            for sid in removed_sids:
                fid = self._object_map.pop(sid, None)
                if fid is not None:
                    self._last_rotated.pop(fid, None)   # reset cooldown for next placement
                    print(f"[TUIOListener] Marker ID={fid} removed")
                    if callable(self.on_marker_removed):
                        self.on_marker_removed(fid)

        # 'fseq' (frame sequence) is intentionally ignored

    def _fire_rotated(self, direction: str, fiducial_id: int, va: float):
        """Fire the rotation callback, suppressing repeats within ROTATION_COOLDOWN."""
        now  = time.monotonic()
        last = self._last_rotated.get(fiducial_id, 0)
        if now - last < ROTATION_COOLDOWN:
            return
        self._last_rotated[fiducial_id] = now
        print(f"[TUIOListener] Marker ID={fiducial_id} rotated {direction} (va={va:.2f})")
        if callable(self.on_marker_rotated):
            self.on_marker_rotated(direction, fiducial_id)
