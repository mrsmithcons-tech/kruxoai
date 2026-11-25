"""
core/room_sentry.py — Continuous Passive Room Sentry & Background Audio Monitor for JARVIS.

Runs a continuous, ultra-low CPU background audio monitor:
- Continuously listens for speech activity in the room.
- Automatically isolates speech bursts.
- Identifies whether the speaker is Faisal (Master) or an Unrecognized Person.
- Enforces Faisal's unrecognized_person_protocol on security breaches.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from core.voice_engine import voice_manager, SAMPLE_RATE

ROOT_DIR = Path(__file__).resolve().parent.parent
SENTRY_LOG = ROOT_DIR / "memory" / "room_sentry_events.json"


class PassiveRoomSentry:
    """Continuous background listener for room security and speaker monitoring."""

    def __init__(self, authorized_speaker: str = "Faisal"):
        self.authorized_speaker = authorized_speaker
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stream = None
        self._speech_buffer: List[np.ndarray] = []
        self._last_speech_time = 0.0
        self._last_alert_time = 0.0
        self._alert_cooldown_sec = 25.0
        self._unrecognized_count = 0
        self._lock = threading.Lock()

    def start(self) -> bool:
        if self._running:
            return True
        try:
            import sounddevice as sd
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="RoomSentryThread")
            self._thread.start()
            print("[RoomSentry] Background audio sentry active.")
            return True
        except Exception as e:
            print(f"[RoomSentry] Failed to start: {e}")
            self._running = False
            return False

    def stop(self) -> None:
        self._running = False

    def is_active(self) -> bool:
        return self._running

    def get_status(self) -> Dict[str, Any]:
        return {
            "active": self._running,
            "authorized_speaker": self.authorized_speaker,
            "unrecognized_events_today": self._unrecognized_count,
            "last_speech_time": time.strftime("%H:%M:%S", time.localtime(self._last_speech_time)) if self._last_speech_time else "Never"
        }

    def _monitor_loop(self) -> None:
        import sounddevice as sd

        # 0.5s audio chunk at 16kHz
        chunk_samples = int(0.5 * SAMPLE_RATE)
        burst_chunks = []

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=chunk_samples) as stream:
                while self._running:
                    data, overflowed = stream.read(chunk_samples)
                    if not self._running:
                        break

                    audio = data.flatten()
                    energy = float(np.mean(audio ** 2))
                    max_val = float(np.max(np.abs(audio)))

                    # Speech burst detection (energy threshold)
                    if energy > 0.002 and max_val > 0.035:
                        burst_chunks.append(audio)
                        self._last_speech_time = time.time()
                    else:
                        if len(burst_chunks) >= 3: # ~1.5 - 2.5s speech accumulated
                            full_burst = np.concatenate(burst_chunks)
                            self._process_speech_burst(full_burst)
                        burst_chunks = []
        except Exception as e:
            print(f"[RoomSentry] Audio loop error: {e}")
            self._running = False

    def _process_speech_burst(self, audio: np.ndarray) -> None:
        """Analyze speech burst in room to verify speaker identity."""
        try:
            # Check speaker identity
            id_res = voice_manager.identify_speaker(custom_audio=audio, threshold=0.70)
            speaker = id_res.get("speaker", "Unrecognized Speaker")
            conf = id_res.get("confidence_pct", 0.0)
            recognized = id_res.get("recognized", False)

            now = time.time()
            event = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "speaker": speaker,
                "confidence_pct": conf,
                "recognized": recognized,
                "action_taken": "logged"
            }

            if recognized and speaker.lower() == self.authorized_speaker.lower():
                # Authorized master speaking normally
                pass
            else:
                # Unrecognized speaker detected!
                self._unrecognized_count += 1
                event["action_taken"] = "security_alert"

                if now - self._last_alert_time > self._alert_cooldown_sec:
                    self._last_alert_time = now
                    # Notify HUD
                    self._dispatch_hud_alert(speaker, conf)

            # Save to log
            self._log_event(event)

        except Exception as e:
            print(f"[RoomSentry] Error processing burst: {e}")

    def _dispatch_hud_alert(self, speaker: str, conf: float) -> None:
        try:
            import urllib.request
            msg = (
                f"### ⚠️ Room Sentry Security Alert\n\n"
                f"- **Event**: Unrecognized Voice Detected in Room\n"
                f"- **Match Confidence**: `{conf}%` (Threshold: 70%)\n"
                f"- **Protocol Triggered**: `unrecognized_person_protocol`\n"
                f"- **Action**: Awaiting identity verification."
            )
            payload = json.dumps({
                "title": "Room Sentry Security Alert",
                "text": msg,
                "speak": "Unrecognized voice detected in room. Enforcing security protocol."
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:9876/panel",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2):
                pass
        except Exception:
            pass

    def _log_event(self, event: dict) -> None:
        try:
            logs = []
            if SENTRY_LOG.exists():
                with open(SENTRY_LOG, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            logs.append(event)
            logs = logs[-50:]
            with open(SENTRY_LOG, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
        except Exception:
            pass


# Global singleton
room_sentry = PassiveRoomSentry()
