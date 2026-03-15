"""
tuio_listener.py
----------------
TUIO Listener Module for the Gesture Beat Saber Login System.

This module implements a raw OSC/UDP TUIO client that listens for messages
from the reacTIVision engine on localhost:3333.  It uses only the Python
standard library (socket + threading) so there is no third-party dependency.

How it works:
  reacTIVision → OSC/UDP messages → port 3333
  → TUIOListener thread decodes /tuio/2Dobj messages
  → calls on_marker_detected(fiducial_id) callback when a new marker appears
"""

import socket
import struct
import threading
import time


# ---------------------------------------------------------------------------
# Minimal OSC parser (standard-library-only)
# ---------------------------------------------------------------------------

def _read_string(data, offset):
    """Read a null-terminated, 4-byte-padded OSC string from *data* at *offset*.
    Returns (string, new_offset)."""
    end = data.index(b'\x00', offset)
    s = data[offset:end].decode('utf-8', errors='replace')
    # Pad to next 4-byte boundary
    padded = end + 1
    remainder = padded % 4
    if remainder:
        padded += (4 - remainder)
    return s, padded


def _read_int32(data, offset):
    return struct.unpack_from('>i', data, offset)[0], offset + 4


def _read_float32(data, offset):
    return struct.unpack_from('>f', data, offset)[0], offset + 4


def _parse_osc_message(data, offset=0):
    """Parse a single OSC message starting at *offset*.
    Returns (address, args_list) or None on error."""
    try:
        address, offset = _read_string(data, offset)
        if not data[offset:offset + 1] == b',':
            return address, []
        type_tag_str, offset = _read_string(data, offset)
        type_tags = type_tag_str[1:]  # strip leading ','
        args = []
        for tag in type_tags:
            if tag == 'i':
                v, offset = _read_int32(data, offset)
                args.append(v)
            elif tag == 'f':
                v, offset = _read_float32(data, offset)
                args.append(v)
            elif tag == 's':
                v, offset = _read_string(data, offset)
                args.append(v)
            elif tag in ('T', 'F', 'N', 'I'):
                args.append({'T': True, 'F': False, 'N': None, 'I': float('inf')}[tag])
            # skip unknown tags
        return address, args
    except Exception:
        return None, []


def _parse_osc_bundle(data, offset=0):
    """Recursively parse an OSC bundle.  Returns list of (address, args)."""
    results = []
    # '#bundle\0' at offset 0, then time-tag (8 bytes)
    offset += 16  # skip '#bundle\0' + timetag
    while offset < len(data):
        size = struct.unpack_from('>i', data, offset)[0]
        offset += 4
        element = data[offset:offset + size]
        offset += size
        if element[:8] == b'#bundle\x00':
            results.extend(_parse_osc_bundle(element, 0))
        else:
            addr, args = _parse_osc_message(element, 0)
            if addr:
                results.append((addr, args))
    return results


def _parse_packet(data):
    """Parse a UDP datagram and return list of (address, args)."""
    if data[:8] == b'#bundle\x00':
        return _parse_osc_bundle(data, 0)
    else:
        addr, args = _parse_osc_message(data, 0)
        return [(addr, args)] if addr else []


# ---------------------------------------------------------------------------
# TUIO Listener class
# ---------------------------------------------------------------------------

class TUIOListener:
    """
    Listens for TUIO 1.1 messages from reacTIVision (UDP / OSC on port 3333).

    Usage:
        listener = TUIOListener(on_marker_detected=my_callback)
        listener.start()
        ...
        listener.stop()

    The *on_marker_detected(fiducial_id: int)* callback is invoked (from a
    background thread) whenever a NEW fiducial marker (TuioObject) appears.
    """

    TUIO_PORT = 3333
    # Debounce delay: ignore a repeated marker detection within this window (seconds).
    DEBOUNCE_SECONDS = 2.0

    def __init__(self, on_marker_detected=None, on_marker_rotated=None, on_marker_removed=None, host='0.0.0.0', port=TUIO_PORT):
        self.host = host
        self.port = port
        self.on_marker_detected = on_marker_detected  # callable(int)
        self.on_marker_rotated = on_marker_rotated    # callable(str, int)
        self.on_marker_removed = on_marker_removed    # callable(int)

        self._socket = None
        self._thread = None
        self._running = False

        # Track known session IDs so we only fire the callback on NEW adds.
        self._alive_session_ids: set = set()
        # Map session_id → fiducial_id for currently tracked objects.
        self._object_map: dict = {}

        # Debounce: track last time each fiducial_id was reported for rotation.
        self._last_detected: dict = {}
        self._last_rotated: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the background listening thread."""
        if self._running:
            return
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.settimeout(1.0)  # so stop() can unblock the recv call
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name='TUIOListener')
        self._thread.start()
        print(f"[TUIOListener] Listening on {self.host}:{self.port}")

    def stop(self):
        """Stop the background listening thread."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        print("[TUIOListener] Stopped.")

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _listen_loop(self):
        while self._running:
            try:
                data, _ = self._socket.recvfrom(65536)
                messages = _parse_packet(data)
                for address, args in messages:
                    if address == '/tuio/2Dobj':
                        self._handle_2dobj(args)
            except socket.timeout:
                continue
            except OSError:
                break  # socket was closed
            except Exception as exc:
                print(f"[TUIOListener] Error: {exc}")

    def _handle_2dobj(self, args):
        """Process a /tuio/2Dobj message."""
        if not args:
            return
        command = args[0]

        if command == 'set' and len(args) >= 3:
            # args: ['set', session_id(int), fiducial_id(int), x, y, angle, ...]
            session_id = int(args[1])
            fiducial_id = int(args[2])
            va = float(args[8]) if len(args) > 8 else 0.0

            is_new = session_id not in self._object_map
            self._object_map[session_id] = fiducial_id

            if is_new:
                self._fire_detected(fiducial_id)
            else:
                if va > 0.5:
                    self._fire_rotated("right", fiducial_id)
                elif va < -0.5:
                    self._fire_rotated("left", fiducial_id)

        elif command == 'alive':
            # args: ['alive', sid1, sid2, ...]
            new_alive = set(int(a) for a in args[1:])
            removed_sids = set(self._object_map.keys()) - new_alive
            for sid in removed_sids:
                fid = self._object_map.pop(sid, None)
                if fid is not None:
                    self._fire_removed(fid)

        elif command == 'fseq':
            pass  # frame sequence — nothing extra needed for our purpose

    def _fire_detected(self, fiducial_id: int):
        """Invoke the user callback (with debounce)."""
        now = time.monotonic()
        last = self._last_detected.get(fiducial_id, 0)
        if now - last < self.DEBOUNCE_SECONDS:
            return
        self._last_detected[fiducial_id] = now
        print(f"[TUIOListener] Detected marker ID={fiducial_id}")
        if callable(self.on_marker_detected):
            self.on_marker_detected(fiducial_id)

    def _fire_removed(self, fiducial_id: int):
        """Invoke the removed callback."""
        print(f"[TUIOListener] Marker ID={fiducial_id} removed")
        if callable(self.on_marker_removed):
            self.on_marker_removed(fiducial_id)

    def _fire_rotated(self, direction: str, fiducial_id: int):
        """Invoke the rotated callback (with debounce)."""
        now = time.monotonic()
        last = self._last_rotated.get(fiducial_id, 0)
        if now - last < 1.0: # 1 second debounce for rotation
            return
        self._last_rotated[fiducial_id] = now
        print(f"[TUIOListener] Marker ID={fiducial_id} rotated {direction}")
        if callable(self.on_marker_rotated):
            self.on_marker_rotated(direction, fiducial_id)
