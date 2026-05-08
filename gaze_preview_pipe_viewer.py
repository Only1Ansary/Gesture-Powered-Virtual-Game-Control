"""
External OpenCV window for gaze_session_cli --preview.

Reads framed JPEG blobs from stdin (uint32 big-endian length, then bytes) and
shows them. Runs as a separate process so HighGUI lives on its own main thread
and is not tied to the WinForms / gaze sidecar process.
"""

from __future__ import annotations

import struct
import sys

import cv2
import numpy as np


def _read_exact(readable, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = readable.read(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else "Gaze live view"
    stdin = sys.stdin.buffer
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    try:
        while True:
            hdr = _read_exact(stdin, 4)
            if hdr is None or len(hdr) < 4:
                break
            (n,) = struct.unpack(">I", hdr)
            if n <= 0 or n > 50_000_000:
                break
            jpeg = _read_exact(stdin, n)
            if jpeg is None or len(jpeg) != n:
                break
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue
            cv2.imshow(title, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
