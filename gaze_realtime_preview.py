"""
Live OpenCV window: webcam + GazeTracking (pupil crosses on frame).

Uses the same camera logic as gaze_tracker.GazeSessionManager (config.json:
- gaze_camera_index
- gaze_opencv_dshow_first
- gaze_capture_width / height, 0 = native
- gaze_sample_interval_ms, gaze_smooth_alpha

Quit: focus the window and press Q.
"""

from __future__ import annotations

import sys

import cv2
import numpy as np
from gaze_tracking import GazeTracking

from config import (
    GAZE_CAMERA_INDEX,
    GAZE_CAPTURE_HEIGHT,
    GAZE_CAPTURE_WIDTH,
    GAZE_MIRROR_HORIZONTAL,
    GAZE_OPENCV_DSHOW_FIRST,
    GAZE_SAMPLE_INTERVAL_MS,
    GAZE_SMOOTH_ALPHA,
)
from gaze_tracker import GazeSessionManager


def main() -> int:
    idx = GAZE_CAMERA_INDEX
    helper = GazeSessionManager(
        enabled=True,
        camera_index=idx,
        sample_interval_ms=GAZE_SAMPLE_INTERVAL_MS,
        smooth_alpha=GAZE_SMOOTH_ALPHA,
        opencv_dshow_first=GAZE_OPENCV_DSHOW_FIRST,
        capture_width=GAZE_CAPTURE_WIDTH,
        capture_height=GAZE_CAPTURE_HEIGHT,
    )
    cap = helper._open_video_capture()
    if cap is None:
        print(
            f"Could not open camera index {idx}. Try gaze_camera_index or "
            "flip gaze_opencv_dshow_first in config.json.",
            file=sys.stderr,
        )
        return 1

    gaze = GazeTracking()
    win = "gaze preview — Q to quit"
    print(f"Camera index {idx} OK. {win}")
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frame = np.ascontiguousarray(np.copy(frame))
            if GAZE_MIRROR_HORIZONTAL:
                frame = np.ascontiguousarray(cv2.flip(frame, 1))
            gaze.refresh(frame)
            vis = gaze.annotated_frame()
            if gaze.pupils_located:
                try:
                    xl, yl = gaze.pupil_left_coords()
                    xr, yr = gaze.pupil_right_coords()
                    hr = gaze.horizontal_ratio()
                    vr = gaze.vertical_ratio()
                    line1 = f"L-pupil ({xl:.0f},{yl:.0f})  R-pupil ({xr:.0f},{yr:.0f})"
                    line2 = f"gaze ratios  h={hr:.2f}  v={vr:.2f}"
                    color = (0, 255, 0)
                except Exception:
                    line1 = "pupils OK (coords unavailable)"
                    line2 = ""
                    color = (0, 255, 0)
            else:
                line1 = "no face / pupils — face the camera"
                line2 = ""
                color = (0, 165, 255)
            cv2.putText(
                vis,
                line1,
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
                cv2.LINE_AA,
            )
            if line2:
                cv2.putText(
                    vis,
                    line2,
                    (10, 56),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    color,
                    2,
                    cv2.LINE_AA,
                )
            cv2.imshow(win, vis)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
