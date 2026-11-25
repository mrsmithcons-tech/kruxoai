"""
plugins/presence_and_learner.py — Vision Tracking, User Presence & PC Activity Learning.

Provides two major autonomous capabilities:
1. EYE CONTACT & USER PRESENCE:
   - Uses OpenCV and your webcam to detect when you are in front of your PC.
   - Tracks your face coordinates and smoothly turns JARVIS's 3D avatar head to
     look directly at you as you move (using player.glance).
   - Detects when you step away and welcomes you back when you return ("Welcome back, Faisal").
2. WORKFLOW & PC HABIT LEARNING:
   - Observes active applications and window titles in the background.
   - Learns your daily habits, projects, and work patterns.
   - Saves persistent knowledge into memory/long_term.json so JARVIS remembers
     your workflow context permanently.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "memory"
ACTIVITY_LOG_FILE = MEMORY_DIR / "observed_activity.json"
LONG_TERM_FILE = MEMORY_DIR / "long_term.json"

PLUGIN = {
    "name": "presence_learning",
    "description": (
        "Check user presence status, face tracking state, or summarize what JARVIS "
        "has learned from observing your PC usage and habits."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "What to report: 'presence' (is user at PC), 'habits' (what JARVIS learned), or 'summary'.",
                "enum": ["presence", "habits", "summary"]
            }
        },
        "required": ["query"]
    }
}

# ── State Tracking ────────────────────────────────────────────────────────────

_USER_PRESENT = False
_LAST_SEEN_TIME = 0.0
_AWAY_NOTIFIED = False
_CAMERA_ACTIVE = True
_OBSERVED_APPS: dict[str, int] = {}  # app_name -> count
_LAST_WINDOW_TITLE = ""


def _get_player():
    """Retrieve active JarvisUI instance safely."""
    try:
        from ui import JarvisUI
        return JarvisUI.get_active()
    except Exception:
        return None


# ── Active Window Detection (Windows) ─────────────────────────────────────────

def _get_active_window() -> tuple[str, str]:
    """Retrieve the current active process name and window title."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", ""

        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()

        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        proc_name = ""
        try:
            import psutil
            if pid.value > 0:
                proc_name = psutil.Process(int(pid.value)).name()
        except Exception:
            pass

        return proc_name, title
    except Exception:
        return "", ""


# ── Activity Learning Loop ───────────────────────────────────────────────────

def _activity_learning_loop():
    """Periodically sample active applications and store workflow memory."""
    global _LAST_WINDOW_TITLE, _OBSERVED_APPS
    while True:
        try:
            time.sleep(10)
            proc_name, title = _get_active_window()
            if not proc_name and not title:
                continue

            # Skip JARVIS itself or idle
            if "jarvis" in title.lower() or proc_name.lower() in ("system idle process", ""):
                continue

            app_key = proc_name.lower().replace(".exe", "")
            if app_key:
                _OBSERVED_APPS[app_key] = _OBSERVED_APPS.get(app_key, 0) + 1

            if title and title != _LAST_WINDOW_TITLE:
                _LAST_WINDOW_TITLE = title
                # Log event
                _record_activity(proc_name, title)

        except Exception as e:
            time.sleep(5)


def _record_activity(proc: str, title: str):
    """Save activity event to memory."""
    try:
        events = []
        if ACTIVITY_LOG_FILE.exists():
            with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
                events = json.load(f)
        
        events.append({
            "timestamp": time.time(),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "process": proc,
            "title": title[:100]
        })
        # Keep last 150 events
        events = events[-150:]
        with open(ACTIVITY_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

        # Update long-term memory every 30 events
        if len(events) % 15 == 0:
            _sync_long_term_habits()
    except Exception:
        pass


def _sync_long_term_habits():
    """Extract top workflows and save to long_term.json for the system prompt."""
    try:
        top_apps = sorted(_OBSERVED_APPS.items(), key=lambda x: x[1], reverse=True)[:5]
        if not top_apps:
            return

        habits_summary = ", ".join(f"{name} ({count}x)" for name, count in top_apps)
        
        memory_data = {}
        if LONG_TERM_FILE.exists():
            with open(LONG_TERM_FILE, "r", encoding="utf-8") as f:
                memory_data = json.load(f)

        if not isinstance(memory_data, dict):
            memory_data = {}

        if "observed_habits" not in memory_data:
            memory_data["observed_habits"] = {}

        memory_data["observed_habits"]["frequent_applications"] = habits_summary
        memory_data["observed_habits"]["last_observed"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        with open(LONG_TERM_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ── Face Tracking & Eye Contact Loop ──────────────────────────────────────────

def _vision_presence_loop():
    """Use OpenCV webcam feed to track face gaze and user presence."""
    global _USER_PRESENT, _LAST_SEEN_TIME, _AWAY_NOTIFIED
    try:
        import cv2
    except ImportError:
        print("[Presence] OpenCV (cv2) not available — vision tracking disabled.")
        return

    cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    if not os.path.exists(cascade_path):
        return

    face_cascade = cv2.CascadeClassifier(cascade_path)
    cap = None

    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print("[Presence] Could not open webcam.")
            return
    except Exception as e:
        print(f"[Presence] Webcam initialization error: {e}")
        return

    print("[Presence] Vision Face-Tracking & Eye Contact active!")
    last_greet_time = 0.0

    while True:
        try:
            if not _CAMERA_ACTIVE:
                time.sleep(1)
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.5)
                continue

            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Fast low-CPU face detection on downscaled grayscale frame
            scale = 0.5
            small_gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
            faces_small = face_cascade.detectMultiScale(
                small_gray,
                scaleFactor=1.2,
                minNeighbors=4,
                minSize=(35, 35)
            )
            faces = [
                (int(fx / scale), int(fy / scale), int(fw / scale), int(fh / scale))
                for (fx, fy, fw, fh) in faces_small
            ]

            # Forward frame to Sleep & Room Sentinel
            try:
                from plugins import sleep_sentinel
                sleep_sentinel.on_video_frame(frame, gray, faces)
            except Exception:
                pass

            player = _get_player()
            now = time.time()

            if len(faces) > 0:
                _LAST_SEEN_TIME = now
                # Pick largest face
                largest = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = largest

                # Compute normalized gaze offset (-1.0 to 1.0)
                center_x = fx + fw / 2.0
                center_y = fy + fh / 2.0
                dx = (center_x - w / 2.0) / (w / 2.0)
                dy = (center_y - h / 2.0) / (h / 2.0)

                # Smooth eye-contact glance (inverted horizontal so it mirrors you)
                if player:
                    player.glance(-dx, dy, hold=0.35)

                # State transition: Returned from AWAY
                if not _USER_PRESENT:
                    _USER_PRESENT = True
                    _AWAY_NOTIFIED = False
                    if player:
                        player.write_log("👤 User is in front of the PC.")
                        # Welcome back greeting if away for more than 25 seconds
                        if now - last_greet_time > 30 and last_greet_time > 0:
                            if hasattr(player, "request_say") and callable(player.request_say):
                                player.request_say("Welcome back, Faisal.")
                        last_greet_time = now
            else:
                # No face detected
                if _USER_PRESENT and (now - _LAST_SEEN_TIME > 20):
                    _USER_PRESENT = False
                    if not _AWAY_NOTIFIED:
                        _AWAY_NOTIFIED = True
                        if player:
                            player.write_log("👤 User stepped away from PC.")

            # Dynamic throttling: 4 FPS when user is at PC, 1 FPS when idle/away to conserve CPU
            time.sleep(0.25 if _USER_PRESENT else 1.0)

        except Exception:
            time.sleep(1)

    if cap:
        cap.release()


# ── Launch Background Daemons Automatically ───────────────────────────────────

t_vision = threading.Thread(target=_vision_presence_loop, daemon=True, name="VisionPresenceThread")
t_vision.start()

t_activity = threading.Thread(target=_activity_learning_loop, daemon=True, name="ActivityLearnerThread")
t_activity.start()


# ── Plugin Run Handler ────────────────────────────────────────────────────────

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Handle voice query about presence or learned habits."""
    query = str(parameters.get("query", "summary")).strip().lower()
    
    presence_str = "You are currently in front of the PC." if _USER_PRESENT else "You are currently away from the PC."
    top_apps = sorted(_OBSERVED_APPS.items(), key=lambda x: x[1], reverse=True)[:4]
    habits_str = ", ".join(f"{name}" for name, _ in top_apps) if top_apps else "Still observing your workflow patterns."

    if query == "presence":
        return f"Presence status: {presence_str}"
    elif query == "habits":
        return f"From observing your PC usage, your most frequent applications are: {habits_str}."
    else:
        if player:
            player.show_content(
                "👤 Presence & Learning Status",
                f"### Vision & Activity Tracker\n\n"
                f"• **User Presence:** {'In Front of PC' if _USER_PRESENT else 'Away'}\n"
                f"• **Eye Contact Tracking:** Active (mirroring your face)\n"
                f"• **Learned Frequent Apps:** {habits_str}\n"
                f"• **Last Active Window:** `{_LAST_WINDOW_TITLE or 'None'}`\n"
            )
        return f"{presence_str} I have been tracking your workflow; your primary apps are {habits_str}."
