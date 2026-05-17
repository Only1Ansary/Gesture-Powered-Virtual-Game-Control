import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import time
from camera_manager import open_camera, CameraRole

# ── Configuration ─────────────────────────────────────────
SMOOTHING = 1

pyautogui.FAILSAFE = False

mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

screen_w, screen_h = pyautogui.size()

try:
    cap = open_camera(CameraRole.HAND, width=640, height=480)
except RuntimeError as _cam_err:
    print(f"[HandController] {_cam_err}")
    raise SystemExit(1)

cursor_buffer = []
last_log_time = time.time()

def smooth_cursor(x, y):
    cursor_buffer.append((x, y))
    if len(cursor_buffer) > SMOOTHING:
        cursor_buffer.pop(0)
    avg_x = int(np.mean([p[0] for p in cursor_buffer]))
    avg_y = int(np.mean([p[1] for p in cursor_buffer]))
    return avg_x, avg_y

with mp_hands.Hands(
    model_complexity=0,
    max_num_hands=1,
    min_detection_confidence=0.3,
    min_tracking_confidence=0.3,
) as hands:

    print("[HandController] Entered detection loop. Waiting for frames...", flush=True)
    last_status_time = time.time()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("[HandController] cap.read() returned False! Exiting loop.", flush=True)
            break

        if time.time() - last_status_time > 3.0:
            print(f"[HandController] Active stream ({frame.shape[1]}x{frame.shape[0]}), searching for hands...", flush=True)
            last_status_time = time.time()

        # frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:

                mp_drawing.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS
                )

                lm = hand_landmarks.landmark

                # Index fingertip
                idx_tip = lm[mp_hands.HandLandmark.INDEX_FINGER_TIP]

                ix_px = int(idx_tip.x * w)
                iy_px = int(idx_tip.y * h)

                # Map to screen
                mx = int(np.interp(idx_tip.x, [0.05, 0.95], [0, screen_w]))
                my = int(np.interp(idx_tip.y, [0.05, 0.95], [0, screen_h]))

                mx, my = smooth_cursor(mx, my)

                pyautogui.moveTo(mx, my, duration=0)

                if time.time() - last_log_time > 0.5:
                    print(f"Tracking Hand: screen ({mx}, {my}) normalized ({idx_tip.x:.2f}, {idx_tip.y:.2f})", flush=True)
                    last_log_time = time.time()

                # Draw pointer
                cv2.circle(frame, (ix_px, iy_px), 12, (0, 255, 0), -1)
                cv2.putText(frame, f"({mx},{my})",
                            (ix_px + 10, iy_px - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (255, 255, 255), 1)

        # cv2.imshow("Hand Mouse Control (Move Only)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()