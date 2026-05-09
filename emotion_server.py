import cv2
import socket
import time
import logging
from deepface import DeepFace

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SERVER_IP = "127.0.0.1"
SERVER_PORT = 12345
SEND_INTERVAL = 1.0
EMOTION_MAP = {"happy": 10, "angry": 200, "sad": 200, "neutral": 100}
DEFAULT_LEVEL = 100

def connect_socket():
    """Keep trying to connect until successful."""
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_IP, SERVER_PORT))
            sock.settimeout(5.0)
            logging.info("Connected to C# game server")
            return sock
        except Exception as e:
            logging.error(f"Connection failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)

def get_emotion(frame):
    """Get dominant emotion, fallback to neutral on any error."""
    try:
        result = DeepFace.analyze(frame, actions=['emotion'], enforce_detection=False)
        return result[0]['dominant_emotion'] if result else "neutral"
    except Exception as e:
        logging.warning(f"Emotion detection error: {e}")
        return "neutral"

def main():
    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        logging.error("Cannot open webcam. Exiting.")
        return

    sock = connect_socket()
    last_send = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logging.warning("Failed to grab frame, retrying...")
                time.sleep(0.5)
                continue

            now = time.time()
            if now - last_send >= SEND_INTERVAL:
                emotion = get_emotion(frame)
                level = EMOTION_MAP.get(emotion, DEFAULT_LEVEL)
                logging.info(f"Emotion: {emotion} → Level: {level}")

                try:
                    sock.sendall(f"{level}\n".encode())
                except (socket.error, BrokenPipeError):
                    logging.warning("Connection lost. Reconnecting...")
                    sock.close()
                    sock = connect_socket()
                    continue

                last_send = now

            # Optional: show webcam preview (remove if unwanted)
            # cv2.putText(frame, f"Emotion: {emotion}", (10, 30),
            #             cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
            # cv2.imshow("Emotion Recognition", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        sock.close()

if __name__ == "__main__":
    main()