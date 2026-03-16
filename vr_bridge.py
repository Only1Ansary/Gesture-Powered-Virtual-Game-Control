"""
vr_bridge.py
────────────
Reads TUIO marker positions from a thread-safe queue and feeds them into
SteamVR as virtual-controller poses via OpenVR-InputEmulator, so that
Beat Saber sabers track the physical TUIO markers in real-time.

Architecture
────────────
  reacTIVision ─► TUIOListener (OSC) ─► queue.Queue ─► VRBridge (this module)
                                                            │
                                                  pyopenvrinputemu
                                                            │
                                                      SteamVR / Beat Saber

The bridge is **decoupled** from the GUI: any data source (TUIO, gesture,
object-detection) can push ``MarkerUpdate`` named-tuples into the queue.

Usage
─────
  # Standalone dry-run (no SteamVR needed):
  python vr_bridge.py --dry-run

  # Programmatic:
  from vr_bridge import VRBridge
  bridge = VRBridge(dry_run=False)
  bridge.start()
  bridge.enqueue(fid=0, x=0.5, y=0.5, angle=0.0)   # continuous stream
  bridge.stop()
"""

from __future__ import annotations

import math
import queue
import sys
import threading
import time
from collections import namedtuple
from typing import Dict, Optional, Tuple

# ── project imports ────────────────────────────────────────────────────────────
from config import (
    VR_BRIDGE_ENABLED,
    VR_DEPTH,
    VR_GLOBAL_OFFSET,
    VR_GLOBAL_ROTATION,
    VR_LEFT_MARKER,
    VR_PLAY_HEIGHT,
    VR_PLAY_WIDTH,
    VR_RIGHT_MARKER,
    VR_UPDATE_RATE,
    VR_Y_OFFSET,
)

# ── optional VR imports ───────────────────────────────────────────────────────
try:
    from pyopenvrinputemu import VRInputSystem
    VR_EMU_AVAILABLE = True
except ImportError:
    VR_EMU_AVAILABLE = False

# ── data structures ────────────────────────────────────────────────────────────
MarkerUpdate = namedtuple("MarkerUpdate", ["fid", "x", "y", "angle"])
"""
fid   – fiducial marker ID (int)
x     – normalised horizontal position [0..1]  (left → right)
y     – normalised vertical position  [0..1]  (top → bottom)
angle – orientation in radians (CW from 12-o'clock)
"""


def _angle_to_quaternion(angle: float) -> Tuple[float, float, float, float]:
    """Convert a TUIO angle (radians, CW from 12 o'clock in the XY plane)
    into a quaternion that rotates the saber around its long axis.

    SteamVR convention:
      • Sabers point along -Z by default.
      • We rotate around the Z-axis so the saber tilts in the player's view.

    Returns (qw, qx, qy, qz).
    """
    # TUIO angle is CW from top; negate to get CCW for right-hand rule
    half = -angle / 2.0
    return (math.cos(half), 0.0, 0.0, math.sin(half))


def _tuio_to_vr(
    x: float,
    y: float,
    play_width: float,
    play_height: float,
    depth: float,
    y_offset: float,
) -> Tuple[float, float, float]:
    """Map normalised TUIO coordinates to SteamVR world metres.

    TUIO  (0,0) = top-left of camera frame, (1,1) = bottom-right.
    SteamVR  X = right, Y = up, Z = towards player (positive).

    Returns (vr_x, vr_y, vr_z).
    """
    vr_x = (x - 0.5) * play_width
    vr_y = -(y - 0.5) * play_height + y_offset   # invert Y + lift
    vr_z = -depth                                  # in front of the player
    return (vr_x, vr_y, vr_z)


class VRBridge:
    """Background-thread bridge that translates TUIO → SteamVR controller poses."""

    def __init__(
        self,
        dry_run: bool = False,
        play_width: float = VR_PLAY_WIDTH,
        play_height: float = VR_PLAY_HEIGHT,
        depth: float = VR_DEPTH,
        y_offset: float = VR_Y_OFFSET,
        global_offset: list = VR_GLOBAL_OFFSET,
        global_rotation: list = VR_GLOBAL_ROTATION,
        left_marker: int = VR_LEFT_MARKER,
        right_marker: int = VR_RIGHT_MARKER,
        update_rate: int = VR_UPDATE_RATE,
    ):
        self.dry_run = dry_run
        self.play_width = play_width
        self.play_height = play_height
        self.depth = depth
        self.y_offset = y_offset
        self.global_offset = list(global_offset)
        self.global_rotation = list(global_rotation)
        self.left_marker = left_marker
        self.right_marker = right_marker
        self.update_rate = max(1, update_rate)

        self._queue: queue.Queue[MarkerUpdate] = queue.Queue(maxsize=256)
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # VR state (populated in _init_vr)
        self._vr_input = None
        self._trackers: Dict[str, object] = {}   # "left" / "right" → VirtualTracker
        self._last_pose: Dict[str, Tuple] = {}   # "left" / "right" → (x, y, z, qw, qx, qy, qz)

    # ── public API ────────────────────────────────────────────────────────────

    def start(self):
        """Initialise VR (unless dry-run) and start the background loop."""
        if self._running:
            return
        if not self.dry_run:
            if not VR_EMU_AVAILABLE:
                print(
                    "[VRBridge] ERROR: pyopenvrinputemu is not available.\n"
                    "           Extract the PyOpenVRInputEmulator release zip into\n"
                    "           the project root so that 'pyopenvrinputemu/' is importable."
                )
                return
            self._init_vr()
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="VRBridge"
        )
        self._thread.start()
        mode = "DRY-RUN" if self.dry_run else "LIVE"
        print(
            f"[VRBridge] Started ({mode}) – "
            f"L=marker {self.left_marker}, R=marker {self.right_marker}, "
            f"{self.update_rate} Hz"
        )

    def stop(self):
        """Signal the loop to exit and join the thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        print("[VRBridge] Stopped.")

    def enqueue(self, fid: int, x: float, y: float, angle: float):
        """Push a marker update into the bridge (called from any thread)."""
        try:
            self._queue.put_nowait(MarkerUpdate(fid, x, y, angle))
        except queue.Full:
            pass  # drop oldest-ish; non-blocking is more important than lossless

    @property
    def is_running(self) -> bool:
        return self._running

    # ── VR initialisation ─────────────────────────────────────────────────────

    def _init_vr(self):
        """Create the VRInputSystem connection and add two virtual trackers."""
        try:
            self._vr_input = VRInputSystem(
                global_offset=self.global_offset,
                global_rotation=self.global_rotation,
            )
            self._trackers["left"] = self._vr_input.add_tracker("tuio_left_saber")
            self._trackers["right"] = self._vr_input.add_tracker("tuio_right_saber")
            print(
                f"[VRBridge] VR initialised – "
                f"{self._vr_input.tracker_count()} virtual device(s) registered."
            )
        except Exception as exc:
            print(f"[VRBridge] ERROR initialising VR: {exc}")
            self._vr_input = None

    # ── background loop ───────────────────────────────────────────────────────

    def _loop(self):
        """Drain the queue, compute poses, and push them to SteamVR at *update_rate* Hz."""
        interval = 1.0 / self.update_rate
        while self._running:
            t0 = time.perf_counter()

            # Drain all pending updates (keep only the latest per marker)
            latest: Dict[int, MarkerUpdate] = {}
            while True:
                try:
                    upd = self._queue.get_nowait()
                    latest[upd.fid] = upd
                except queue.Empty:
                    break

            # Process each updated marker
            for fid, upd in latest.items():
                side = self._fid_to_side(fid)
                if side is None:
                    continue  # not assigned to a saber

                vr_x, vr_y, vr_z = _tuio_to_vr(
                    upd.x, upd.y,
                    self.play_width, self.play_height,
                    self.depth, self.y_offset,
                )
                qw, qx, qy, qz = _angle_to_quaternion(upd.angle)

                self._last_pose[side] = (vr_x, vr_y, vr_z, qw, qx, qy, qz)

                if self.dry_run:
                    print(
                        f"  [{side.upper():5s}] fid={fid}  "
                        f"tuio=({upd.x:.3f}, {upd.y:.3f}, {upd.angle:.2f})  →  "
                        f"vr=({vr_x:+.3f}, {vr_y:+.3f}, {vr_z:+.3f})  "
                        f"q=({qw:.3f}, {qx:.3f}, {qy:.3f}, {qz:.3f})"
                    )
                else:
                    tracker = self._trackers.get(side)
                    if tracker and self._vr_input:
                        try:
                            self._vr_input.update_tracker(
                                tracker.device_id,
                                vr_x, vr_y, vr_z,
                                qw, qx, qy, qz,
                            )
                        except Exception as exc:
                            print(f"[VRBridge] Pose update error ({side}): {exc}")

            # Sleep the remainder of the interval
            elapsed = time.perf_counter() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _fid_to_side(self, fid: int) -> Optional[str]:
        """Map a fiducial ID to 'left' or 'right', or None if unassigned."""
        if fid == self.left_marker:
            return "left"
        if fid == self.right_marker:
            return "right"
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Standalone dry-run
# ══════════════════════════════════════════════════════════════════════════════

def _demo_dry_run():
    """Simulate two markers oscillating and print the computed VR poses."""
    bridge = VRBridge(dry_run=True)
    bridge.start()

    print("\n── Dry-run: simulating 5 seconds of marker movement ──\n")
    t_start = time.time()
    try:
        while time.time() - t_start < 5.0:
            t = time.time() - t_start
            # Left marker (ID 0): oscillates horizontally
            bridge.enqueue(
                fid=bridge.left_marker,
                x=0.3 + 0.2 * math.sin(t * 2),
                y=0.5,
                angle=math.sin(t) * 0.5,
            )
            # Right marker (ID 1): oscillates vertically
            bridge.enqueue(
                fid=bridge.right_marker,
                x=0.7,
                y=0.3 + 0.2 * math.cos(t * 2),
                angle=-math.sin(t) * 0.5,
            )
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        pass

    bridge.stop()
    print("\n── Dry-run complete ──")


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        _demo_dry_run()
    else:
        print(
            "Usage:  python vr_bridge.py --dry-run\n"
            "\n"
            "  Runs a 5-second simulation printing computed SteamVR poses.\n"
            "  For real use, the bridge is started by the main application.\n"
        )
