import sys
import os
import time
import json

try:
    import cv2
    import face_recognition
    import numpy as np
except ImportError as e:
    print(f"ERROR: Missing dependency. Please run: pip install opencv-python face-recognition numpy")
    print(f"Details: {e}")
    sys.exit(1)

# Create face_data directory if it doesn't exist
DATA_DIR = "face_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except:
        return {}

def enroll(user_id, camera_index):
    print(f"ENROLL: Starting enrollment for User ID {user_id}...")
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"ERROR: Could not open camera {camera_index}")
        return False

    print("Look at the camera and wait for capture...")
    
    start_time = time.time()
    captured_encoding = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Display the frame
        display_frame = frame.copy()
        cv2.putText(display_frame, f"Enrolling User {user_id}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        cv2.putText(display_frame, "Center your face in the frame", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
        
        # Find faces
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        
        for (top, right, bottom, left) in face_locations:
            cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)

        cv2.imshow("Face ID Enrollment", display_frame)

        # Automatically capture after 3 seconds if a face is found
        if face_locations and time.time() - start_time > 3:
            encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            if encodings:
                captured_encoding = encodings[0]
                break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    if captured_encoding is not None:
        np.save(os.path.join(DATA_DIR, f"{user_id}.npy"), captured_encoding)
        print(f"SUCCESS: Face encoded for User {user_id}")
        return True
    else:
        print("FAILED: No face captured")
        return False

def verify(camera_index):
    print("VERIFY: Starting face login...")
    
    # Load all known faces
    known_encodings = []
    known_ids = []
    for file in os.listdir(DATA_DIR):
        if file.endswith(".npy"):
            uid = file.replace(".npy", "")
            encoding = np.load(os.path.join(DATA_DIR, file))
            known_encodings.append(encoding)
            known_ids.append(uid)

    if not known_encodings:
        print("ERROR: No faces registered yet.")
        return None

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"ERROR: Could not open camera {camera_index}")
        return None

    start_time = time.time()
    found_id = None

    while time.time() - start_time < 15: # 15 seconds timeout
        ret, frame = cap.read()
        if not ret:
            break

        display_frame = frame.copy()
        cv2.putText(display_frame, "Face Login - Searching...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
            
            if True in matches:
                first_match_index = matches.index(True)
                found_id = known_ids[first_match_index]
                cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(display_frame, f"Matched ID: {found_id}", (left, top-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                break
            else:
                cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 0, 255), 2)

        cv2.imshow("Face ID Login", display_frame)

        if found_id or (cv2.waitKey(1) & 0xFF == ord('q')):
            break

    cap.release()
    cv2.destroyAllWindows()

    if found_id:
        print(f"RESULT_ID:{found_id}")
        return found_id
    else:
        print("FAILED: No match found")
        return None

def delete_face(user_id):
    path = os.path.join(DATA_DIR, f"{user_id}.npy")
    if os.path.exists(path):
        os.remove(path)
        print(f"DELETED: Face data for User {user_id}")
        return True
    return False

if __name__ == "__main__":
    config = load_config()
    cam_idx = config.get("face_camera_index", 0)

    if len(sys.argv) < 2:
        print("Usage: face_manager.py --enroll <id> | --verify | --delete <id>")
        sys.exit(1)

    cmd = sys.argv[1]
    
    if cmd == "--enroll" and len(sys.argv) == 3:
        enroll(sys.argv[2], cam_idx)
    elif cmd == "--verify":
        verify(cam_idx)
    elif cmd == "--delete" and len(sys.argv) == 3:
        delete_face(sys.argv[2])
    else:
        print("Invalid command or missing ID")
