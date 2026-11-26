"""
core/understanding.py — Expression & Understanding layer for Kruxo AI.

Answers one question: "what is Faisal feeling and doing right now — and
what should I do about it?"

It fuses three signals that already exist on the machine into ONE understood
state. Nothing here is a mind-reader, and the code is honest about that:

1. VOICE (real classifier, core/voice_emotion.py)
   3-second mic clip -> jitter / shimmer / HFER / pace / HNR ->
   emotional_state + stress_level_pct. Only runs when the mic is free;
   the live Gemini session owns the mic most of the time, so a failure
   just means "voice: unknown", never a guess.

2. FACE (geometry, NOT emotion recognition)
   There is no facial-emotion model in the repo — the plugin named
   "user_emotion_vision_recognition" is actually a code-execution tool.
   So this reads honest geometry from one webcam frame via MediaPipe
   FaceMesh (already a Kruxo dependency for 2FA):
     EAR (eye aspect ratio)  -> eyes open / narrowing / closing (tired?)
     MAR (mouth aspect ratio)-> mouth open (speaking / yawning?)
   It reports the raw numbers and a *cautious* reading ("eyes_narrowed"),
   never "happy" or "sad" — geometry cannot tell you that. Falls back to
   Haar face detection (face present / absent only) when MediaPipe is
   missing, and to "unknown" when the camera is busy or off.

3. CONTEXT (already in the living state)
   Time of day, minutes on the current app, which app (intent), sleep
   log if the sleep sentinel wrote one, who else is in the room.

Fused result (living_state["understanding"]):
    mood:       calm_focused | stressed | tired | tired_late | energized | unknown
    confidence: low | medium | high   (how many signals agreed)
    energy:     high | normal | low | unknown
    intent:     coding | outreach | research | watching | chatting | unknown
    face:       {present, ear, mar, reading, source}
    voice:      {emotional_state, stress_level_pct, source}
    style_hint: what Kruxo should do differently right now, e.g.
                "short_replies", "calm_tone", "stay_quiet", "suggest_rest"
    signals:    which sensors actually contributed (so "unknown" is visible)

Everything is local. Nothing is uploaded. A failed sensor is "unknown".
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT_DIR / "memory"
SLEEP_LOG = MEMORY_DIR / "sleep_tracker_log.json"

# MediaPipe FaceMesh landmarks (468-point mesh)
_LEFT_EYE = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE = (362, 385, 387, 263, 373, 380)
_MOUTH_UP, _MOUTH_LO, _MOUTH_L, _MOUTH_R = 13, 14, 61, 291


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def sense_face() -> Dict[str, Any]:
    """One webcam frame -> honest face geometry. Never raises, never guesses."""
    try:
        import cv2
    except Exception:
        return {"present": None, "reading": "unknown",
                "source": "no_camera_library", "detail": "OpenCV not available"}
    cap = None
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return {"present": None, "reading": "unknown",
                    "source": "camera_busy_or_off",
                    "detail": "Could not open camera — it may be in use or off"}
        ok, frame = cap.read()
        if not ok or frame is None:
            return {"present": None, "reading": "unknown",
                    "source": "camera_busy_or_off", "detail": "No frame from camera"}
        return _face_from_frame(frame)
    except Exception as e:
        return {"present": None, "reading": "unknown",
                "source": "error", "detail": str(e)}
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass


def _face_from_frame(frame) -> Dict[str, Any]:
    # Try MediaPipe geometry first (eye/mouth ratios).
    try:
        import mediapipe as mp
        import numpy as np
        rgb = frame[:, :, ::-1]  # BGR -> RGB without importing cv2 convert
        with mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True, max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5) as mesh:
            res = mesh.process(rgb)
        if not res.multi_face_landmarks:
            return {"present": False, "reading": "absent",
                    "source": "mediapipe", "detail": "No face in frame"}
        lm = [(p.x, p.y) for p in res.multi_face_landmarks[0].landmark]
        def ear(pts):
            p1, p2, p3, p4, p5, p6 = (lm[i] for i in pts)
            return (_dist(p2, p6) + _dist(p3, p5)) / (2.0 * _dist(p1, p4) + 1e-9)
        ear_v = round((ear(_LEFT_EYE) + ear(_RIGHT_EYE)) / 2.0, 3)
        mar_v = round(_dist(lm[_MOUTH_UP], lm[_MOUTH_LO]) /
                      (_dist(lm[_MOUTH_L], lm[_MOUTH_R]) + 1e-9), 3)
        if ear_v < 0.18:
            reading = "eyes_narrowed_or_closing"
        elif mar_v > 0.5:
            reading = "mouth_open_speaking_or_yawning"
        else:
            reading = "attentive"
        return {"present": True, "ear": ear_v, "mar": mar_v,
                "reading": reading, "source": "mediapipe",
                "detail": "Geometry only — not an emotion diagnosis"}
    except Exception:
        pass
    # Fallback: Haar — face present or not, nothing more.
    try:
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.1, 4)
        if len(faces) == 0:
            return {"present": False, "reading": "absent",
                    "source": "haar", "detail": "No face in frame"}
        return {"present": True, "reading": "present",
                "source": "haar", "detail": "Face present; expression not measured"}
    except Exception as e:
        return {"present": None, "reading": "unknown",
                "source": "error", "detail": str(e)}


def sense_voice(duration: float = 3.0) -> Dict[str, Any]:
    """Voice emotion via the real acoustic engine. Mic may be busy -> unknown."""
    try:
        from core.voice_emotion import analyze_vocal_emotion
        res = analyze_vocal_emotion(duration=duration)
        if not res.get("ok"):
            return {"emotional_state": "unknown", "stress_level_pct": None,
                    "source": "voice_emotion",
                    "detail": str(res.get("error", "no speech or mic busy"))}
        return {"emotional_state": res.get("emotional_state", "unknown"),
                "stress_level_pct": res.get("stress_level_pct"),
                "advice": res.get("advice", ""),
                "source": "voice_emotion", "detail": "Acoustic signals only"}
    except Exception as e:
        return {"emotional_state": "unknown", "stress_level_pct": None,
                "source": "error", "detail": str(e)}


def _intent_from_app(app: str, title: str) -> str:
    a = (app or "").lower()
    t = (title or "").lower()
    if a in ("code.exe", "devenv.exe", "idea64.exe", "notepad++.exe",
             "cursor.exe", "windsurf.exe"):
        return "coding"
    if "gmail" in t or "mail" in t or "outreach" in t:
        return "outreach"
    if a in ("chrome.exe", "brave.exe", "msedge.exe", "firefox.exe"):
        if any(k in t for k in ("youtube", "tiktok", "facebook", "reel")):
            return "watching"
        return "research"
    if a in ("whatsapp.exe", "telegram.exe", "slack.exe", "discord.exe"):
        return "chatting"
    return "unknown"


def _energy(hour: int, minutes_on_app: float, sleep_hours: Optional[float]) -> str:
    if hour >= 23 or hour < 6:
        return "low"
    if sleep_hours is not None and sleep_hours < 5.5:
        return "low"
    if minutes_on_app >= 120:
        return "low"
    if 9 <= hour <= 12:
        return "high"
    return "normal"


def _last_sleep_hours() -> Optional[float]:
    try:
        if not SLEEP_LOG.exists():
            return None
        data = json.loads(SLEEP_LOG.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else data.get("nights", [])
        if not entries:
            return None
        last = entries[-1]
        hours = last.get("hours") or last.get("sleep_hours") or last.get("duration_h")
        return float(hours) if hours is not None else None
    except Exception:
        return None


def fuse_understanding(state: Dict[str, Any], face=None, voice=None) -> Dict[str, Any]:
    """Combine face + voice + context into one understood state."""
    face = face if face is not None else {"reading": "unknown"}
    voice = voice if voice is not None else {"emotional_state": "unknown"}
    app = (state.get("app") or {})
    hour = datetime.now().hour
    minutes = float(state.get("minutes_on_current_app") or 0)
    stress = voice.get("stress_level_pct")
    face_reading = face.get("reading", "unknown")
    voice_state = str(voice.get("emotional_state", "unknown")).lower()

    signals = []
    if face_reading not in ("unknown",):
        signals.append("face")
    if voice_state not in ("unknown",):
        signals.append("voice")
    signals.append("context")

    mood = "unknown"
    if stress is not None and stress >= 65:
        mood = "stressed"
    elif face_reading == "eyes_narrowed_or_closing" or "tired" in voice_state or "fatigue" in voice_state:
        mood = "tired"
    elif "calm" in voice_state or "focused" in voice_state:
        mood = "calm_focused"
    elif face_reading == "attentive" and 9 <= hour <= 18:
        mood = "calm_focused"
    if mood == "tired" and (hour >= 23 or hour < 6):
        mood = "tired_late"

    energy = _energy(hour, minutes, _last_sleep_hours())
    intent = _intent_from_app(app.get("app", ""), app.get("title", ""))

    if mood == "stressed":
        style_hint, suggestion = "calm_tone", "Mute non-urgent alerts and keep replies short and calm."
    elif mood in ("tired", "tired_late"):
        style_hint, suggestion = "suggest_rest", "Suggest rest and keep everything short."
    elif mood == "calm_focused":
        style_hint, suggestion = "stay_quiet", "Do not interrupt; only speak if something matters."
    elif energy == "high" and 9 <= hour <= 11:
        style_hint, suggestion = "briefing_mode", "Good time for the morning briefing."
    else:
        style_hint, suggestion = "normal", ""

    confidence = "high" if len(signals) >= 3 and mood != "unknown" else (
        "medium" if len(signals) >= 2 and mood != "unknown" else "low")

    return {
        "mood": mood,
        "confidence": confidence,
        "energy": energy,
        "intent": intent,
        "face": face,
        "voice": voice,
        "style_hint": style_hint,
        "suggestion": suggestion,
        "signals": signals,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
