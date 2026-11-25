import time
import cv2
import numpy as np

PLUGIN = {
    "name": "enhanced_presence_awareness",
    "description": "Uses OpenCV face and eye/head orientation tracking to determine if the user is actively looking at the screen, absent, or looking away, providing contextual presence awareness.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "duration_seconds": {
                "type": "INTEGER",
                "description": "Duration in seconds to monitor user presence (default: 5)."
            },
            "camera_index": {
                "type": "INTEGER",
                "description": "Index of the camera device to use (default: 0)."
            }
        },
        "required": []
    }
}

def analyze_presence(duration_seconds: int = 5, camera_index: int = 0, player=None) -> dict:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return {"status": "error", "message": f"Could not access camera at index {camera_index}."}

    start_time = time.time()
    total_frames = 0
    face_detected_frames = 0
    looking_at_screen_frames = 0

    try:
        while time.time() - start_time < duration_seconds:
            ret, frame = cap.read()
            if not ret:
                break

            total_frames += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

            if len(faces) > 0:
                face_detected_frames += 1
                # Grab the largest face detected
                (x, y, w, h) = max(faces, key=lambda b: b[2] * b[3])
                roi_gray = gray[y:y+h, x:x+w]
                
                # Detect eyes within the upper region of the face to confirm attention
                eyes = eye_cascade.detectMultiScale(roi_gray[0:int(h/2), :], scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))
                if len(eyes) >= 1:
                    looking_at_screen_frames += 1

            time.sleep(0.03) # Limit sample rate (~30fps max loop)

    finally:
        cap.release()

    if total_frames == 0:
        return {"status": "error", "message": "Failed to capture any frames from the camera."}

    face_presence_ratio = face_detected_frames / total_frames
    eye_contact_ratio = looking_at_screen_frames / total_frames

    if face_presence_ratio < 0.2:
        state = "absent"
        details = "The user does not appear to be present at the desk."
    elif eye_contact_ratio >= 0.35:
        state = "actively_looking"
        details = "The user is actively looking at the screen."
    else:
        state = "present_looking_away"
        details = "The user is present at the desk but looking away from the screen."

    return {
        "status": "success",
        "state": state,
        "details": details,
        "face_presence_ratio": round(face_presence_ratio, 2),
        "eye_contact_ratio": round(eye_contact_ratio, 2)
    }

def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        duration_seconds = parameters.get("duration_seconds", 5)
        camera_index = parameters.get("camera_index", 0)

        if player:
            player.write_log(f"[enhanced_presence_awareness] Monitoring presence for {duration_seconds}s on camera {camera_index}...")

        result = analyze_presence(duration_seconds=duration_seconds, camera_index=camera_index, player=player)

        if result.get("status") == "error":
            msg = f"Presence detection failed: {result.get('message')}"
            if player:
                player.write_log(f"[enhanced_presence_awareness] Error: {result.get('message')}")
            return msg

        state = result["state"]
        details = result["details"]
        summary = f"Presence Status: {state.replace('_', ' ').title()}. {details}"

        if session_memory is not None and hasattr(session_memory, "update"):
            session_memory.update({"user_presence": state, "presence_details": details})

        if player:
            player.show_content(
                "User Presence Status",
                f"State: {state.replace('_', ' ').title()}\n"
                f"Details: {details}\n"
                f"Face Presence Ratio: {result['face_presence_ratio']*100:.0f}%\n"
                f"Direct Attention Ratio: {result['eye_contact_ratio']*100:.0f}%"
            )
            player.write_log(f"[enhanced_presence_awareness] Assessment complete: {state}")

        if state == "actively_looking":
            return "The user is currently focused and looking directly at the screen."
        elif state == "present_looking_away":
            return "The user is present at their desk but currently looking away."
        else:
            return "The user does not appear to be in front of the screen."

    except Exception as e:
        error_msg = f"An error occurred while tracking presence: {str(e)}"
        if player:
            player.write_log(f"[enhanced_presence_awareness] Exception: {str(e)}")
        return error_msg