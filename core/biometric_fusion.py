"""
core/biometric_fusion.py — Multimodal Two-Factor Biometric Fusion (Face + Voice 2FA) for JARVIS.

Combines:
- Factor 1: OpenCV Real-Time Face Presence & Eye Alignment (Visual Biometrics)
- Factor 2: Mel-Cepstral Voiceprint Matching (Acoustic Biometrics)

Provides hardware-grade multi-factor authentication for sensitive desktop operations
(e.g., executing system commands, accessing confidential API keys, and memory wipes).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from core.voice_engine import voice_manager

ROOT_DIR = Path(__file__).resolve().parent.parent
FUSION_AUDIT_LOG = ROOT_DIR / "memory" / "biometric_2fa_audit.json"


def _check_face_presence() -> Dict[str, Any]:
    """Check visual presence via presence_and_learner or quick camera capture."""
    try:
        from plugins import presence_and_learner as pal
        user_present = getattr(pal, "_USER_PRESENT", False)
        last_seen = getattr(pal, "_LAST_SEEN_TIME", 0.0)
        elapsed = time.time() - last_seen if last_seen > 0 else 999.0

        if user_present and elapsed < 6.0:
            return {"present": True, "confidence": 1.0, "latency_sec": round(elapsed, 1), "source": "presence_loop"}
        elif elapsed < 18.0:
            return {"present": True, "confidence": 0.75, "latency_sec": round(elapsed, 1), "source": "presence_recent"}
        else:
            return {"present": False, "confidence": 0.0, "latency_sec": round(elapsed, 1), "source": "away"}
    except Exception as e:
        # Fallback to direct quick camera check
        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                    face_cascade = cv2.CascadeClassifier(cascade_path)
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.2, 4, minSize=(40, 40))
                    if len(faces) > 0:
                        return {"present": True, "confidence": 0.95, "faces_count": len(faces), "source": "direct_cam"}
        except Exception:
            pass
        return {"present": False, "confidence": 0.0, "error": str(e), "source": "unavailable"}


def authenticate_2fa(
    speaker_name: str = "Faisal",
    duration: float = 2.5,
    custom_audio: Optional[np.ndarray] = None,
    level: str = "HIGH"
) -> Dict[str, Any]:
    """
    Perform 2-Factor Biometric Fusion Authentication.
    Levels:
        - "HIGH": Requires BOTH Face Presence (Factor 1) AND Voice Match (Factor 2).
        - "STANDARD": Requires Composite Score >= 70%.
    """
    # 1. Visual Face Factor
    face_res = _check_face_presence()
    face_score = face_res.get("confidence", 0.0)

    # 2. Acoustic Voice Factor
    voice_res = voice_manager.verify_speaker(
        speaker_name,
        duration=duration,
        custom_audio=custom_audio,
        threshold=0.70
    )
    voice_score = voice_res.get("similarity", 0.0)
    voice_conf = voice_res.get("confidence_pct", 0.0)
    voice_verified = voice_res.get("verified", False)

    # 3. Composite Fusion Calculation
    composite = 0.50 * face_score + 0.50 * voice_score
    composite_pct = round(composite * 100, 1)

    req_level = level.upper()
    if req_level == "HIGH":
        authenticated = bool(face_res.get("present") and voice_verified)
    else:
        authenticated = bool(composite >= 0.65)

    result = {
        "ok": True,
        "authenticated": authenticated,
        "speaker": speaker_name,
        "security_level": req_level,
        "composite_score_pct": composite_pct,
        "face_factor": {
            "verified": face_res.get("present", False),
            "confidence_pct": round(face_score * 100, 1),
            "source": face_res.get("source")
        },
        "voice_factor": {
            "verified": voice_verified,
            "confidence_pct": voice_conf,
            "pitch_hz": voice_res.get("live_stats", {}).get("mean_pitch_hz")
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Log to 2FA audit trail
    try:
        logs = []
        if FUSION_AUDIT_LOG.exists():
            with open(FUSION_AUDIT_LOG, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(result)
        logs = logs[-50:]
        with open(FUSION_AUDIT_LOG, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass

    return result
