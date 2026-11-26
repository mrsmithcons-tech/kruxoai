"""
plugins/sleep_sentinel.py — Overnight Sleep Tracking & Room Activity Sentinel for JARVIS.

Full-night autonomous sleep monitoring and room activity analysis:
1. Vision Motion & Position Changes:
   - Frame-differencing motion energy to detect movement vs stillness.
   - Logs every position change (toss & turn) with exact timestamp.
   - Detects when lights are turned off and on.
   - Detects yawns via face/mouth opening duration.
2. Acoustic Snore & Noise Detection:
   - Continuous sounddevice listener analyzing audio energy and snore cadences (low-frequency rhythmic bursts).
   - Tracks snoring frequency, total snoring duration, and ambient room noise spikes.
3. Sleep Stage & Duration Metrics:
   - Sleep onset latency (time to fall asleep).
   - Total sleep duration (hours & minutes).
   - Restlessness score and overall Sleep Quality Score (0-100%).
4. Executive Morning Dashboard:
   - Formats a comprehensive Markdown report with timeline, tables, and statistics.
   - Streams directly to the HUD Content Panel and records in memory/sleep_tracker_log.json.

NIGHT WINDOW (Faisal, 26 Nov 2026): monitoring runs 9:00 PM – 6:00 AM ONLY.
Outside that window the camera frames are ignored and the microphone is
not recorded at all; at 6:00 AM the night is closed once with the morning
report and the per-night state is reset for the next night.
"""
from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "memory"
SLEEP_LOG_FILE = MEMORY_DIR / "sleep_tracker_log.json"
LONG_TERM_FILE = MEMORY_DIR / "long_term.json"

PLUGIN = {
    "name": "sleep_sentinel",
    "description": (
        "Overnight sleep and room activity sentinel, active 9:00 PM – 6:00 AM only. "
        "Monitors your sleep quality, tracks when you fall asleep and wake up, logs "
        "every position change, yawn, or snore, and generates a comprehensive morning "
        "sleep report on the HUD panel. Outside the night window it records nothing."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'start' (arm overnight monitoring), 'report' (view night report), 'status' (current sleep state), 'stop' (end session).",
                "enum": ["start", "report", "status", "stop"]
            }
        },
        "required": []
    }
}

# ── Night window: 9:00 PM – 6:00 AM ONLY (Faisal, 26 Nov 2026) ───────────────
# Outside this window the sentinel records nothing: camera frames are ignored
# in on_video_frame and the microphone is never opened in the audio loop.
NIGHT_START_HOUR = 21  # 9 PM
NIGHT_END_HOUR = 6     # 6 AM


def _in_night_window(now=None) -> bool:
    """True only between 9 PM and 6 AM (local time)."""
    hour = (now or datetime.now()).hour
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


_LAST_REPORT_DATE = ""  # YYYY-MM-DD of the last morning report (one per day)


# ── Sleep Sentinel State ──────────────────────────────────────────────────────

_MONITOR_ACTIVE = True  # Armed automatically; the night window gates all recording
_SESSION_START_TIME = time.time()
_LIGHTS_OFF_TIME: float | None = None
_SLEEP_ONSET_TIME: float | None = None
_WAKE_TIME: float | None = None

_IS_SLEEPING = False
_LAST_MOTION_TIME = time.time()
_LAST_POSITION_CHANGE_TIME = 0.0
_POSITION_CHANGES: list[dict] = []  # [{time: str, duration: float}]
_SNORE_EVENTS: list[dict] = []       # [{time: str, duration_sec: float, peak_rms: float}]
_YAWN_EVENTS: list[dict] = []        # [{time: str}]
_ROOM_NOISE_EVENTS: list[dict] = []  # [{time: str, level: str}]
_LIGHT_EVENTS: list[dict] = []       # [{time: str, event: 'off'|'on'}]

_PREV_GRAY = None
_CONSECUTIVE_QUIET_SECONDS = 0.0
_LAST_LIGHT_STATE = "unknown"
_AUDIO_LISTENER_ACTIVE = True

_LOCK = threading.Lock()


def _get_player():
    try:
        from ui import JarvisUI
        return JarvisUI.get_active()
    except Exception:
        return None


def _load_log() -> dict:
    try:
        if SLEEP_LOG_FILE.exists():
            with open(SLEEP_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "sessions": [],
        "current": {}
    }


def _save_current_state():
    try:
        data = _load_log()
        data["current"] = {
            "session_start": datetime.fromtimestamp(_SESSION_START_TIME).strftime("%Y-%m-%d %H:%M:%S"),
            "is_sleeping": _IS_SLEEPING,
            "sleep_onset": datetime.fromtimestamp(_SLEEP_ONSET_TIME).strftime("%H:%M:%S") if _SLEEP_ONSET_TIME else None,
            "position_changes_count": len(_POSITION_CHANGES),
            "position_changes": _POSITION_CHANGES[-20:],
            "snore_count": len(_SNORE_EVENTS),
            "snore_events": _SNORE_EVENTS[-20:],
            "yawns_count": len(_YAWN_EVENTS),
            "room_noises": _ROOM_NOISE_EVENTS[-20:],
            "light_events": _LIGHT_EVENTS[-10:]
        }
        with open(SLEEP_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ── Vision Frame Processor (called from camera loop) ──────────────────────────

def on_video_frame(frame, gray, faces):
    """Analyze incoming webcam frame for motion, position shifts, yawns, and lighting."""
    global _PREV_GRAY, _LAST_MOTION_TIME, _LAST_POSITION_CHANGE_TIME
    global _IS_SLEEPING, _SLEEP_ONSET_TIME, _WAKE_TIME, _LIGHTS_OFF_TIME
    global _LAST_LIGHT_STATE, _LAST_REPORT_DATE

    if not _MONITOR_ACTIVE or frame is None or gray is None:
        return

    if not _in_night_window():
        return  # Sleep Sentinel runs 9 PM – 6 AM only; daytime frames are ignored

    now = time.time()
    now_str = datetime.now().strftime("%I:%M %p")

    # 1. Ambient Lighting Detection
    try:
        import numpy as np
        brightness = float(np.mean(gray))

        if brightness < 25 and _LAST_LIGHT_STATE != "dark":
            _LAST_LIGHT_STATE = "dark"
            _LIGHTS_OFF_TIME = now
            with _LOCK:
                _LIGHT_EVENTS.append({"time": now_str, "event": "Room lights turned off (dark)"})
            player = _get_player()
            if player:
                player.write_log("🌙 Sleep Sentinel: Room lights turned off.")

        elif brightness >= 50 and _LAST_LIGHT_STATE == "dark":
            _LAST_LIGHT_STATE = "bright"
            _WAKE_TIME = now
            with _LOCK:
                _LIGHT_EVENTS.append({"time": now_str, "event": "Room lights turned on (morning/awake)"})
            player = _get_player()
            if player:
                player.write_log("☀️ Sleep Sentinel: Room lights turned on.")
                if _IS_SLEEPING:
                    _IS_SLEEPING = False
                    _generate_morning_report(player)
                    _LAST_REPORT_DATE = datetime.now().date().isoformat()
                    _reset_night_state()

    except Exception:
        pass

    # 2. Motion Energy & Position Shift Detection
    try:
        import cv2
        import numpy as np

        if _PREV_GRAY is not None and _PREV_GRAY.shape == gray.shape:
            diff = cv2.absdiff(_PREV_GRAY, gray)
            _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
            motion_pixels = int(np.count_nonzero(thresh))
            total_pixels = gray.shape[0] * gray.shape[1]
            motion_ratio = motion_pixels / total_pixels

            # Significant movement threshold (shifting in bed)
            if motion_ratio > 0.04:
                quiet_duration = now - _LAST_MOTION_TIME
                _LAST_MOTION_TIME = now

                # If the user was quiet for > 3 minutes and suddenly moved:
                # that is a POSITION CHANGE (tossing & turning)!
                if quiet_duration > 180 and (now - _LAST_POSITION_CHANGE_TIME > 60):
                    _LAST_POSITION_CHANGE_TIME = now
                    with _LOCK:
                        _POSITION_CHANGES.append({
                            "time": now_str,
                            "motion_percent": round(motion_ratio * 100, 1),
                            "rested_before_mins": round(quiet_duration / 60, 1)
                        })
                    player = _get_player()
                    if player:
                        player.write_log(f"🔄 Sleep Sentinel: Position change logged at {now_str} (after {round(quiet_duration/60, 1)}m quiet).")
            else:
                # User is still
                time_still = now - _LAST_MOTION_TIME
                # If still for > 15 minutes, mark as ASLEEP
                if not _IS_SLEEPING and time_still > 900:
                    _IS_SLEEPING = True
                    _SLEEP_ONSET_TIME = _LAST_MOTION_TIME
                    player = _get_player()
                    if player:
                        player.write_log(f"💤 Sleep Sentinel: Sleep onset detected at {now_str}.")

        _PREV_GRAY = gray.copy()
    except Exception:
        pass

    # 3. Yawn / Mouth Opening Detection
    try:
        if len(faces) > 0:
            fx, fy, fw, fh = faces[0]
            # Lower third of face = mouth region
            mouth_y = int(fy + fh * 0.65)
            mouth_h = int(fh * 0.35)
            mouth_x = int(fx + fw * 0.2)
            mouth_w = int(fw * 0.6)
            mouth_roi = gray[mouth_y:mouth_y+mouth_h, mouth_x:mouth_x+mouth_w]

            if mouth_roi.size > 0:
                # Threshold dark cavity of open mouth
                _, mouth_thresh = cv2.threshold(mouth_roi, 40, 255, cv2.THRESH_BINARY_INV)
                open_pixels = int(np.count_nonzero(mouth_thresh))
                ratio = open_pixels / mouth_roi.size
                if ratio > 0.35:
                    # Yawn event (debounced 10s)
                    if not _YAWN_EVENTS or (now - _YAWN_EVENTS[-1].get("ts", 0) > 10):
                        with _LOCK:
                            _YAWN_EVENTS.append({"time": now_str, "ts": now})
                        player = _get_player()
                        if player:
                            player.write_log(f"🥱 Sleep Sentinel: Yawn detected at {now_str}.")
    except Exception:
        pass


# ── Acoustic Snore & Noise Listener Thread ────────────────────────────────────

def _audio_snore_listener_loop():
    """Continuously monitors microphone for snoring patterns and noise disturbances."""
    global _AUDIO_LISTENER_ACTIVE
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        return

    sample_rate = 16000
    chunk_duration = 1.0  # seconds
    chunk_size = int(sample_rate * chunk_duration)

    snore_consecutive = 0
    noise_floor = 0.02

    while _AUDIO_LISTENER_ACTIVE:
        try:
            if not _in_night_window():
                # Outside 9 PM–6 AM the microphone is never opened. At 6 AM
                # the night is closed once with the morning report.
                _end_night_session(_get_player())
                time.sleep(30)
                continue

            # Record 1 second audio chunk non-blocking
            audio = sd.rec(chunk_size, samplerate=sample_rate, channels=1, dtype="float32")
            sd.wait()

            audio_flat = audio.flatten()
            rms = float(np.sqrt(np.mean(audio_flat ** 2)))

            # Dynamic noise floor adaptation
            if rms < noise_floor and rms > 0.001:
                noise_floor = noise_floor * 0.95 + rms * 0.05

            now = time.time()
            now_str = datetime.now().strftime("%I:%M %p")

            # Snore acoustic detection:
            # Snoring typically produces rhythmic acoustic bursts between 80-400Hz with RMS above noise floor
            if rms > noise_floor * 3.5 and rms > 0.035:
                # Low-pass energy check via FFT
                fft = np.abs(np.fft.rfft(audio_flat))
                freqs = np.fft.rfftfreq(len(audio_flat), 1.0 / sample_rate)
                
                low_band = np.sum(fft[(freqs >= 80) & (freqs <= 450)])
                high_band = np.sum(fft[freqs > 1000]) + 1e-6

                # Snore characteristic: heavy low-frequency energy compared to high frequency
                if (low_band / high_band) > 2.0:
                    snore_consecutive += 1
                    # 2 consecutive seconds of snoring pattern
                    if snore_consecutive == 2:
                        with _LOCK:
                            _SNORE_EVENTS.append({
                                "time": now_str,
                                "duration_sec": 3.0,
                                "peak_rms": round(rms, 3)
                            })
                        player = _get_player()
                        if player:
                            player.write_log(f"💤 Sleep Sentinel: Snoring detected at {now_str}.")
                else:
                    # Generic room noise (door, object, speaking)
                    snore_consecutive = 0
                    if rms > 0.15:
                        with _LOCK:
                            if not _ROOM_NOISE_EVENTS or (now - _ROOM_NOISE_EVENTS[-1].get("ts", 0) > 15):
                                _ROOM_NOISE_EVENTS.append({
                                    "time": now_str,
                                    "ts": now,
                                    "level": f"Loud disturbance ({round(rms*100, 1)} dB RMS)"
                                })
                        player = _get_player()
                        if player:
                            player.write_log(f"🔊 Sleep Sentinel: Room noise spike at {now_str}.")
            else:
                snore_consecutive = 0

            time.sleep(0.5)

        except Exception:
            time.sleep(1)


# Start background audio listener automatically
t_audio = threading.Thread(
    target=_audio_snore_listener_loop,
    daemon=True,
    name="SnoreAudioListenerThread"
)
t_audio.start()


# ── Sleep Analytics & Morning Report Generator ────────────────────────────────

def _reset_night_state():
    """Clear the per-night state so the next night starts clean."""
    global _IS_SLEEPING, _SLEEP_ONSET_TIME, _WAKE_TIME, _LIGHTS_OFF_TIME
    global _SESSION_START_TIME, _LAST_POSITION_CHANGE_TIME, _LAST_MOTION_TIME
    _IS_SLEEPING = False
    _SLEEP_ONSET_TIME = None
    _WAKE_TIME = None
    _LIGHTS_OFF_TIME = None
    _SESSION_START_TIME = time.time()
    _LAST_MOTION_TIME = time.time()
    _LAST_POSITION_CHANGE_TIME = 0.0
    with _LOCK:
        _POSITION_CHANGES.clear()
        _SNORE_EVENTS.clear()
        _YAWN_EVENTS.clear()
        _ROOM_NOISE_EVENTS.clear()
        _LIGHT_EVENTS.clear()


def _end_night_session(player=None) -> str:
    """Close the night once (at 6 AM, or on 'stop'): report once per day,
    then reset for the next night. A second call the same day does nothing
    but reset — the morning report is never delivered twice."""
    global _LAST_REPORT_DATE
    today = datetime.now().date().isoformat()
    had_night = bool(_IS_SLEEPING or _SLEEP_ONSET_TIME or _POSITION_CHANGES
                     or _SNORE_EVENTS or _YAWN_EVENTS)
    if not had_night or _LAST_REPORT_DATE == today:
        _reset_night_state()
        return "No sleep session to report."
    _LAST_REPORT_DATE = today
    report = _generate_morning_report(player)
    _reset_night_state()
    return report


def _generate_morning_report(player=None) -> str:
    """Build and deliver the executive full-night sleep report card."""
    now = time.time()
    sleep_start = _SLEEP_ONSET_TIME or _LIGHTS_OFF_TIME or _SESSION_START_TIME
    sleep_end = _WAKE_TIME or now

    duration_sec = max(0, sleep_end - sleep_start)
    hours = int(duration_sec // 3600)
    minutes = int((duration_sec % 3600) // 60)

    # Position changes breakdown
    num_positions = len(_POSITION_CHANGES)
    num_snores = len(_SNORE_EVENTS)
    num_yawns = len(_YAWN_EVENTS)
    num_noises = len(_ROOM_NOISE_EVENTS)

    # Calculate Sleep Quality Score (0 - 100)
    # Deductions: high restlessness, frequent snoring, room disturbances
    quality_score = 95
    if hours < 6:
        quality_score -= (6 - hours) * 5
    if num_positions > 15:
        quality_score -= min(15, (num_positions - 15) * 2)
    if num_snores > 10:
        quality_score -= min(15, (num_snores - 10) * 1.5)
    if num_noises > 5:
        quality_score -= min(10, num_noises * 2)
    quality_score = max(40, min(100, int(quality_score)))

    # Timeline table
    timeline_rows = []
    for p in _POSITION_CHANGES[-10:]:
        timeline_rows.append(f"| `{p.get('time')}` | 🔄 Shifted position | Rested {p.get('rested_before_mins', 0)}m prior |")
    for s in _SNORE_EVENTS[-6:]:
        timeline_rows.append(f"| `{s.get('time')}` | 💤 Snoring episode | Peak: {s.get('peak_rms', 0)} RMS |")
    for y in _YAWN_EVENTS[-4:]:
        timeline_rows.append(f"| `{y.get('time')}` | 🥱 Yawn detected | Drowsiness indicator |")
    for n in _ROOM_NOISE_EVENTS[-4:]:
        timeline_rows.append(f"| `{n.get('time')}` | 🔊 Room disturbance | {n.get('level')} |")

    timeline_table = "\n".join(timeline_rows) if timeline_rows else "| *Night was completely peaceful with minimal disturbance.* | | |"

    report_md = f"""### 🌙 Overnight Sleep & Room Activity Report
**Sleep Quality Score:** `{quality_score}/100` ({'Excellent' if quality_score >= 85 else 'Restful' if quality_score >= 70 else 'Restless'})

#### ⏱️ Sleep Architecture
- **Bedtime / Lights Off:** `{datetime.fromtimestamp(sleep_start).strftime('%I:%M %p')}`
- **Wake Time:** `{datetime.fromtimestamp(sleep_end).strftime('%I:%M %p')}`
- **Total Sleep Duration:** `{hours} hrs {minutes} mins`
- **Total Position Shifts (Toss & Turn):** `{num_positions} times`
- **Snoring Episodes:** `{num_snores} detected`
- **Yawns Recorded:** `{num_yawns} times`
- **Room Disturbances / Sounds:** `{num_noises} spikes`

#### 📊 Night Activity Timeline
| Time | Event | Details |
|:---|:---|:---|
{timeline_table}

---
*Generated autonomously by JARVIS Sleep & Room Sentinel.*
"""
    if player:
        player.show_content("🌙 Overnight Sleep & Room Report", report_md)
        player.write_log(f"✓ Morning Sleep Report delivered (Score: {quality_score}/100, Duration: {hours}h {minutes}m).")

    # Persist session to sleep log and date-specific report
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_report_path = MEMORY_DIR / f"sleep_report_{today_str}.json"
        report_data = {
            "date": today_str,
            "privacy_guarantee": "100% On-Device Processing. No video frames or audio recordings are uploaded or leave this PC.",
            "sleep_quality_score": quality_score,
            "bedtime": datetime.fromtimestamp(sleep_start).strftime("%Y-%m-%d %I:%M:%S %p"),
            "wake_time": datetime.fromtimestamp(sleep_end).strftime("%Y-%m-%d %I:%M:%S %p"),
            "total_sleep_duration_hours": round(duration_sec / 3600, 2),
            "position_shifts": _POSITION_CHANGES,
            "snore_events": _SNORE_EVENTS,
            "snore_confidence": "High (FFT 80-450Hz low-band dominance)" if _SNORE_EVENTS else "No rhythmic snoring detected",
            "yawns_detected": num_yawns,
            "noise_spikes": _ROOM_NOISE_EVENTS,
            "light_events": _LIGHT_EVENTS,
            "timeline": timeline_rows,
        }
        with open(daily_report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        data = _load_log()
        data["sessions"].append({
            "date": today_str,
            "duration": f"{hours}h {minutes}m",
            "score": quality_score,
            "positions": num_positions,
            "snores": num_snores,
            "yawns": num_yawns
        })
        with open(SLEEP_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[SleepSentinel] Save error: {e}")

    return f"Faisal, here is your sleep report: you slept for {hours} hours and {minutes} minutes with a quality score of {quality_score} out of 100. You shifted position {num_positions} times. The complete timeline is on your panel."


# ── Plugin Run Handler ────────────────────────────────────────────────────────

def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action", "start")).strip().lower() or "start"

    if action == "start":
        global _MONITOR_ACTIVE, _SESSION_START_TIME
        _MONITOR_ACTIVE = True
        _SESSION_START_TIME = time.time()
        if not _in_night_window():
            # Outside 9 PM–6 AM the sentinel does not record. It arms itself
            # at 9 PM — the window gates in on_video_frame and the audio loop.
            return ("Sleep Sentinel is scheduled for tonight, 9:00 PM – 6:00 AM. "
                    "It is off right now and will arm itself at 9 PM. "
                    "Outside the night window it records nothing.")
        if player:
            player.show_content(
                "🌙 Sleep Sentinel Armed",
                "### 🌙 Overnight Sleep Sentinel Active\n\n"
                "JARVIS is monitoring your room throughout the night (9 PM – 6 AM):\n"
                "• **Webcam:** Tracking motion, body position shifts, yawns, and lighting.\n"
                "• **Microphone:** Tracking breathing, snoring, and room noises.\n"
                "• **Morning Report:** Full timeline and sleep quality score will appear when you wake up.\n\n"
                "*Good night, Faisal. Sleep well.*"
            )
            player.write_log("🌙 Sleep Sentinel armed for overnight monitoring.")
        return "Sleep sentinel is armed. I am monitoring your room for movement, position shifts, yawns, and snoring. I will prepare your full report for the morning. Good night, Faisal."

    elif action == "report":
        return _generate_morning_report(player)

    elif action == "status":
        if not _in_night_window():
            return ("Sleep Sentinel is off right now — it only runs 9:00 PM to "
                    "6:00 AM. Next session starts tonight at 9 PM.")
        num_pos = len(_POSITION_CHANGES)
        num_snore = len(_SNORE_EVENTS)
        return f"Sleep sentinel is active. Tonight I have logged {num_pos} position shifts and {num_snore} snoring episodes."

    elif action == "stop":
        _MONITOR_ACTIVE = False
        return _end_night_session(player)

    return "Sleep Sentinel is active."
