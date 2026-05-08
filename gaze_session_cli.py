"""
gaze_session_cli.py
-------------------
Sidecar entry point used by the C# WinForms GUI.

The C# app starts this process when a profile page opens and writes "stop" to
stdin when the profile session ends. This process records gaze samples, writes
per-user CSV/JSON files, generates a heatmap, and saves layout.json.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

_gaze_cap_note = (
    "Windows: DSHOW/MSMF order per gaze_opencv_dshow_first; native res unless gaze_capture_* set"
    if sys.platform == "win32"
    else "native resolution unless gaze_capture_width/height set"
)

from config import (
    GAZE_CAMERA_INDEX,
    GAZE_CAPTURE_HEIGHT,
    GAZE_CAPTURE_WIDTH,
    GAZE_DATA_DIR,
    GAZE_DEBUG_LOG,
    GAZE_HEATMAP_GRID_COLUMNS,
    GAZE_HEATMAP_GRID_ROWS,
    GAZE_LAYOUT_MARGIN_RATIO,
    GAZE_LAYOUT_MIN_DISTANCE,
    GAZE_MIN_SAMPLES,
    GAZE_MIRROR_HORIZONTAL,
    GAZE_OPENCV_DSHOW_FIRST,
    GAZE_PREVIEW_WINDOW,
    GAZE_SAMPLE_INTERVAL_MS,
    GAZE_SESSION_LOG_FILE,
    GAZE_SMOOTH_ALPHA,
)
from gaze_store import GazeProfileStore
from gaze_tracker import GazeSessionManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record one user's gaze session.")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--screen-width", type=int, required=True)
    parser.add_argument("--screen-height", type=int, required=True)
    parser.add_argument("--camera-index", type=int, default=GAZE_CAMERA_INDEX)
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Open external OpenCV window (separate process, same camera feed via JPEG pipe).",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable live window even if gaze_preview_window is true in config.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.no_preview:
        use_preview = False
    elif args.preview:
        use_preview = True
    else:
        use_preview = GAZE_PREVIEW_WINDOW
    store = GazeProfileStore(GAZE_DATA_DIR)

    log_fp = None
    if GAZE_DEBUG_LOG:
        try:
            os.makedirs(os.path.dirname(GAZE_SESSION_LOG_FILE) or ".", exist_ok=True)
            log_fp = open(GAZE_SESSION_LOG_FILE, "a", encoding="utf-8")
            log_fp.write(
                f"\n=== gaze_session start {time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"user={args.user_id} camera={args.camera_index} "
                f"({_gaze_cap_note}) ===\n"
            )
            log_fp.flush()
        except OSError as ex:
            print(f"[GazeCLI] Could not open gaze log {GAZE_SESSION_LOG_FILE}: {ex}", flush=True)

    def _ts() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def on_status(msg: str) -> None:
        # Always flush: C# reads stdout via RedirectStandardOutput + async lines.
        print(msg, flush=True)
        if log_fp:
            log_fp.write(f"{_ts()}  {msg}\n")
            log_fp.flush()

    def on_machine_line(line: str) -> None:
        # Machine protocol on stdout + stderr so the GUI never misses lines if one pipe stalls.
        print(line, flush=True)
        print(line, file=sys.stderr, flush=True)
        if log_fp:
            log_fp.write(f"{_ts()}  {line}\n")
            log_fp.flush()

    try:
        gaze = GazeSessionManager(
            enabled=True,
            camera_index=args.camera_index,
            sample_interval_ms=GAZE_SAMPLE_INTERVAL_MS,
            smooth_alpha=GAZE_SMOOTH_ALPHA,
            machine_status=True,
            opencv_dshow_first=GAZE_OPENCV_DSHOW_FIRST,
            capture_width=GAZE_CAPTURE_WIDTH,
            capture_height=GAZE_CAPTURE_HEIGHT,
            preview_window=use_preview,
            mirror_horizontal=GAZE_MIRROR_HORIZONTAL,
            on_status=on_status,
            on_machine_line=on_machine_line,
        )

        cli_intro = (
            f"[GazeCLI] Recording user {args.user_id} on camera {args.camera_index}."
        )
        print(cli_intro, flush=True)
        if log_fp:
            log_fp.write(f"{_ts()}  {cli_intro}\n")
            if GAZE_SESSION_LOG_FILE:
                log_fp.write(
                    f"{_ts()}  [GazeCLI] Debug log file: {GAZE_SESSION_LOG_FILE}\n"
                )
            log_fp.flush()

        try:
            gaze.start(args.user_id)
            try:
                for line in sys.stdin:
                    if line.strip().lower() in {"stop", "quit", "exit"}:
                        break
            except KeyboardInterrupt:
                pass
        finally:
            user_id, started_at, ended_at, samples = gaze.stop()
            if user_id is not None:
                result = store.finalize_session(
                    user_id=user_id,
                    started_at=started_at,
                    ended_at=ended_at or time.time(),
                    samples=samples,
                    screen_width=args.screen_width,
                    screen_height=args.screen_height,
                    camera_index=args.camera_index,
                    min_samples=GAZE_MIN_SAMPLES,
                    grid_columns=GAZE_HEATMAP_GRID_COLUMNS,
                    grid_rows=GAZE_HEATMAP_GRID_ROWS,
                    margin_ratio=GAZE_LAYOUT_MARGIN_RATIO,
                    min_distance=GAZE_LAYOUT_MIN_DISTANCE,
                )
                tail = f"[GazeCLI] Saved: {result}"
                print(tail, flush=True)
                if log_fp:
                    log_fp.write(f"{_ts()}  {tail}\n")
                    log_fp.write(f"{_ts()}  === gaze_session end ({len(samples)} samples) ===\n")
                    log_fp.flush()
    finally:
        if log_fp:
            try:
                log_fp.close()
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
