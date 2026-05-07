import logging
import os
from pathlib import Path
import socket
import time

import cv2

try:
    from ultralytics import YOLO  # type: ignore[import-not-found]
except ImportError:
    YOLO = None

try:
    import pyautogui  # type: ignore[import-not-found]
except ImportError:
    pyautogui = None


LOG_PATH = Path(__file__).resolve().with_name("yolo_tracker.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
    ],
)

SERVER_IP = "127.0.0.1"
SERVER_PORT = 12346

CAMERA_INDEX = int(os.getenv("YOLO_CAMERA_INDEX", "3"))
DEFAULT_MODEL_NAME = "yolov8l-worldv2.pt"
MODEL_PATH = os.getenv("YOLO_MODEL_PATH", DEFAULT_MODEL_NAME)
CONFIDENCE_THRESHOLD = float(os.getenv("YOLO_CONFIDENCE", "0.015"))
YOLO_INFER_CONFIDENCE = float(os.getenv("YOLO_INFER_CONFIDENCE", "0.005"))
YOLO_IMAGE_SIZE = int(os.getenv("YOLO_IMAGE_SIZE", "1280"))
SEND_INTERVAL = float(os.getenv("YOLO_SEND_INTERVAL", "0.2"))
LOST_TIMEOUT = float(os.getenv("YOLO_LOST_TIMEOUT", "1.2"))
STABLE_FRAMES = int(os.getenv("YOLO_STABLE_FRAMES", "1"))
MOVE_MOUSE = os.getenv("YOLO_MOVE_MOUSE", "0") == "1"
MOUSE_SMOOTHING = float(os.getenv("YOLO_MOUSE_SMOOTHING", "0.65"))
MIRROR_X = os.getenv("YOLO_MIRROR_X", "1") == "1"
TARGET_CLASSES = [
    "stick",
    "wooden stick",
    "rod",
    "pole",
    "baton",
    "wand",
    "pointer",
    "pencil",
    "pen",
    "baseball bat",
    "ruler",
    "measuring ruler",
    "straight ruler",
    "scale ruler",
]

LABEL_TO_TOOL = {
    "stick": "sword",
    "wooden stick": "sword",
    "rod": "sword",
    "pole": "sword",
    "baton": "sword",
    "wand": "sword",
    "pointer": "sword",
    "pencil": "stick",
    "pen": "stick",
    "baseball bat": "sword",
    "ruler": "stick",
    "measuring ruler": "stick",
    "straight ruler": "stick",
    "scale ruler": "stick",
}


def resolve_model_path(model_path):
    path = Path(model_path)
    if path.is_absolute() and path.exists():
        return str(path)

    script_dir = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / model_path,
        script_dir / model_path,
        script_dir.parent / model_path,
        script_dir.parent.parent / model_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return model_path


def connect_socket():
    """Try to connect once so tracking can continue even if the game listener is late."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        sock.connect((SERVER_IP, SERVER_PORT))
        sock.settimeout(5.0)
        logging.info("Connected to C# tool listener")
        return sock
    except Exception as exc:
        logging.warning("Tool listener not ready: %s", exc)
        return None


def send_tool(sock, message):
    if sock is None:
        return None

    try:
        sock.sendall(f"{message}\n".encode("ascii"))
        return sock
    except (socket.error, BrokenPipeError, OSError):
        logging.warning("Tool listener connection lost.")
        try:
            sock.close()
        except OSError:
            pass
        return None


def normalize_label(label):
    return str(label).strip().lower().replace("_", " ")


def apply_coordinate_mapping(center):
    x, y = center
    if MIRROR_X:
        x = 1.0 - x
    return x, y


def move_mouse_from_detection(center, previous_mouse):
    if not MOVE_MOUSE or pyautogui is None:
        return previous_mouse

    screen_w, screen_h = pyautogui.size()
    target_x = center[0] * max(1, screen_w - 1)
    target_y = center[1] * max(1, screen_h - 1)

    if previous_mouse is None:
        next_x, next_y = target_x, target_y
    else:
        next_x = previous_mouse[0] + (target_x - previous_mouse[0]) * MOUSE_SMOOTHING
        next_y = previous_mouse[1] + (target_y - previous_mouse[1]) * MOUSE_SMOOTHING

    pyautogui.moveTo(int(next_x), int(next_y), duration=0)
    return next_x, next_y


def detect_tool(model, frame):
    results = model(frame, conf=YOLO_INFER_CONFIDENCE, imgsz=YOLO_IMAGE_SIZE, verbose=False)
    best_label = None
    best_conf = 0.0
    best_center = (0.5, 0.5)
    observed = []
    frame_h, frame_w = frame.shape[:2]

    for result in results:
        names = result.names
        for box in result.boxes:
            confidence = float(box.conf[0])
            cls_id = int(box.cls[0])
            label = normalize_label(names.get(cls_id, cls_id))
            observed.append(f"{label}:{confidence:.2f}")

            if confidence < CONFIDENCE_THRESHOLD or confidence <= best_conf:
                continue

            if label in LABEL_TO_TOOL:
                best_label = label
                best_conf = confidence
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                raw_center = (
                    max(0.0, min(1.0, ((x1 + x2) / 2.0) / frame_w)),
                    max(0.0, min(1.0, ((y1 + y2) / 2.0) / frame_h)),
                )
                best_center = apply_coordinate_mapping(raw_center)

    if best_label is None:
        return "none", 0.0, ", ".join(observed[:5]) if observed else "no boxes", best_center
    return LABEL_TO_TOOL[best_label], best_conf, best_label, best_center


def stable_tool(candidate, previous_candidate, candidate_count, current_tool, last_seen):
    now = time.time()
    if candidate == previous_candidate:
        candidate_count += 1
    else:
        previous_candidate = candidate
        candidate_count = 1

    if candidate != "none" and candidate_count >= STABLE_FRAMES:
        current_tool = candidate
        last_seen = now
    elif candidate == "none" and now - last_seen >= LOST_TIMEOUT:
        current_tool = "none"

    return previous_candidate, candidate_count, current_tool, last_seen


def main():
    if YOLO is None:
        logging.error("ultralytics is not installed. Install it with: pip install ultralytics")
        return

    resolved_model_path = resolve_model_path(MODEL_PATH)
    logging.info("Loading YOLO model: %s", resolved_model_path)
    model = YOLO(resolved_model_path)
    if hasattr(model, "set_classes"):
        model.set_classes(TARGET_CLASSES)
        logging.info("Configured YOLO-World classes: %s", ", ".join(TARGET_CLASSES))
    else:
        logging.warning("Model does not support set_classes(); detection depends on model's built-in labels.")

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        logging.error("Cannot open YOLO camera index %s. Exiting.", CAMERA_INDEX)
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    logging.info("YOLO camera opened on index %s", CAMERA_INDEX)

    sock = None
    last_connect_attempt = 0.0
    previous_candidate = "none"
    candidate_count = 0
    current_tool = "none"
    last_sent = None
    last_send_time = 0.0
    last_seen = 0.0
    last_confidence = 0.0
    last_candidate = "none"
    last_center = (0.5, 0.5)
    previous_mouse = None

    if MOVE_MOUSE and pyautogui is not None:
        pyautogui.FAILSAFE = False
        logging.info("YOLO mouse movement enabled")
    elif MOVE_MOUSE:
        logging.warning("pyautogui is not installed; YOLO will not move the Windows mouse")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logging.warning("Failed to grab YOLO frame, retrying...")
                time.sleep(0.2)
                continue

            candidate, confidence, observed, center = detect_tool(model, frame)
            if observed == "no boxes":
                height, width = frame.shape[:2]
                observed = f"no boxes frame={width}x{height}"
            previous_candidate, candidate_count, current_tool, last_seen = stable_tool(
                candidate,
                previous_candidate,
                candidate_count,
                current_tool,
                last_seen,
            )
            if candidate != "none":
                last_confidence = confidence
                last_candidate = observed
                last_center = center
                previous_mouse = move_mouse_from_detection(last_center, previous_mouse)
            elif current_tool == "none":
                last_confidence = 0.0
                last_candidate = observed
                last_center = (0.5, 0.5)
                previous_mouse = None

            now = time.time()
            message = f"{current_tool}|{last_confidence:.2f}|{last_candidate}|{last_center[0]:.3f}|{last_center[1]:.3f}"
            if sock is None and now - last_connect_attempt >= 2.0:
                sock = connect_socket()
                last_connect_attempt = now

            if message != last_sent or now - last_send_time >= SEND_INTERVAL:
                logging.info("Tool: %s candidate=%s confidence=%.2f observed=%s", current_tool, candidate, confidence, observed)
                sock = send_tool(sock, message)
                last_sent = message
                last_send_time = now

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        try:
            if sock is not None:
                sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()
