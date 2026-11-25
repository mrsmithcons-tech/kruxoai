"""
plugins/voice_recognition_system.py — Real-time Voice Recognition & Biometrics Plugin for JARVIS.

Enables JARVIS to:
1. Enroll a speaker's voiceprint profile (e.g., "Faisal").
2. Identify the active speaker from live microphone audio.
3. Verify if the current speaker is the authorized user.
4. Detect unrecognized speakers and enforce the unrecognized person protocol.
5. Provide acoustic analysis (pitch, resonance, speaking clarity).

Complies with AGENTS.md rules:
- Thread-safe UI updates through player methods only.
- Never raises exceptions; returns concise strings for speech.
- Uses core/voice_engine.py for local, fast signal processing.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

PLUGIN = {
    "name": "voice_recognition_system",
    "description": (
        "Voice Recognition & Speaker Biometrics System. Enrolls speaker voiceprints, "
        "identifies who is speaking, verifies authorized users, and analyzes acoustic voice pitch and clarity."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "enroll_speaker",
                    "identify_speaker",
                    "verify_speaker",
                    "analyze_voice",
                    "list_speakers",
                    "delete_speaker"
                ],
                "description": "Voice recognition action to perform."
            },
            "speaker_name": {
                "type": "STRING",
                "description": "Name of the speaker to enroll, verify, or delete (e.g. 'Faisal')."
            },
            "duration": {
                "type": "NUMBER",
                "description": "Microphone recording duration in seconds (default: 3.0)."
            }
        },
        "required": ["action"]
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    Executes voice recognition action. Thread-safe and non-blocking.
    """
    action = parameters.get("action", "").strip().lower()
    speaker_name = parameters.get("speaker_name", "").strip()
    duration = float(parameters.get("duration", 3.0))

    try:
        from core.voice_engine import voice_manager
    except Exception as e:
        msg = f"Voice recognition engine import failed: {e}"
        if player and hasattr(player, "write_log"):
            player.write_log(f"[VoiceRecognition]: {msg}")
        return "Voice recognition engine is currently unavailable."

    # ── ACTION: ENROLL SPEAKER ────────────────────────────────────────────────
    if action == "enroll_speaker":
        target_name = speaker_name or "Faisal"
        if player and hasattr(player, "write_log"):
            player.write_log(f"[VoiceRecognition]: Enrolling voice for '{target_name}' (recording {duration}s)...")
        if player and hasattr(player, "show_content"):
            player.show_content(
                "Voice Biometrics: Enrollment",
                f"### Enrolling Voice Profile for {target_name}\n\n"
                f"- **Listening duration**: {duration} seconds\n"
                "- **Status**: Recording speech samples and calculating 64-d Mel-filterbank voiceprint...\n"
                "- *Please speak normally into the microphone.*"
            )

        res = voice_manager.enroll_speaker(target_name, duration=duration)
        if not res.get("ok"):
            err = res.get("error", "Enrollment failed.")
            if player and hasattr(player, "write_log"):
                player.write_log(f"[VoiceRecognition Error]: {err}")
            return f"Voice enrollment failed: {err}"

        pitch = res.get("pitch_hz", "N/A")
        if player and hasattr(player, "show_content"):
            player.show_content(
                "Voice Biometrics: Enrolled",
                f"### Voice Profile Enrolled: {target_name}\n\n"
                f"- **Speaker**: `{target_name}`\n"
                f"- **Pitch (F0)**: `{pitch} Hz`\n"
                f"- **Spectral Resonance**: `{res.get('spectral_centroid_hz', 'N/A')} Hz`\n"
                f"- **Acoustic Windows**: `{res.get('windows', 1)} samples averaged`\n"
                f"- **Status**: Profile saved to local biometric vault."
            )
        if player and hasattr(player, "write_log"):
            player.write_log(f"[VoiceRecognition]: Voice profile enrolled for {target_name} ({pitch} Hz).")

        return f"Voice profile for {target_name} has been successfully enrolled."

    # ── ACTION: IDENTIFY SPEAKER ──────────────────────────────────────────────
    elif action == "identify_speaker":
        if player and hasattr(player, "write_log"):
            player.write_log(f"[VoiceRecognition]: Listening to identify active speaker ({duration}s)...")

        res = voice_manager.identify_speaker(duration=duration)
        if not res.get("ok"):
            err = res.get("error", "Identification failed.")
            return f"Voice identification failed: {err}"

        speaker = res.get("speaker", "Unrecognized Speaker")
        conf = res.get("confidence_pct", 0.0)
        recognized = res.get("recognized", False)
        live_stats = res.get("live_stats", {})

        if player and hasattr(player, "show_content"):
            status_badge = "✅ **VERIFIED MATCH**" if recognized else "⚠️ **UNRECOGNIZED SPEAKER**"
            player.show_content(
                "Voice Biometrics: Identification",
                f"### Voice Recognition Result\n\n"
                f"- **Result**: {status_badge}\n"
                f"- **Identified Speaker**: `{speaker}`\n"
                f"- **Biometric Confidence**: `{conf}%`\n"
                f"- **Live Pitch**: `{live_stats.get('mean_pitch_hz', 'N/A')} Hz`\n"
                f"- **Speech Activity**: `{live_stats.get('active_ratio', 'N/A')}%`"
            )

        if player and hasattr(player, "write_log"):
            player.write_log(f"[VoiceRecognition]: Identified: {speaker} ({conf}% confidence)")

        if recognized:
            return f"Speaker identified as {speaker} with {conf}% biometric confidence."
        else:
            return (
                f"Unrecognized speaker detected with best match to {res.get('best_match_name')} "
                f"at only {conf}% confidence. Unrecognized person protocol applies."
            )

    # ── ACTION: VERIFY SPEAKER ────────────────────────────────────────────────
    elif action == "verify_speaker":
        target_name = speaker_name or "Faisal"
        if player and hasattr(player, "write_log"):
            player.write_log(f"[VoiceRecognition]: Verifying voice for '{target_name}'...")

        res = voice_manager.verify_speaker(target_name, duration=duration)
        if not res.get("ok"):
            return f"Verification error: {res.get('error')}"

        verified = res.get("verified", False)
        conf = res.get("confidence_pct", 0.0)
        live_stats = res.get("live_stats", {})

        if player and hasattr(player, "show_content"):
            status_text = "✅ **VERIFICATION PASSED**" if verified else "❌ **VERIFICATION FAILED**"
            player.show_content(
                "Voice Biometrics: Verification",
                f"### Verification for {target_name}\n\n"
                f"- **Status**: {status_text}\n"
                f"- **Confidence**: `{conf}%` (Threshold: {res.get('threshold_pct')}%\n"
                f"- **Pitch Match**: `{'Yes' if res.get('pitch_match') else 'Divergent'}`\n"
                f"- **Live Pitch**: `{live_stats.get('mean_pitch_hz')} Hz`"
            )

        if verified:
            return f"Voice verified: This is {target_name} with {conf}% confidence."
        else:
            return f"Voice verification failed for {target_name}. Confidence was {conf}%, below authentication threshold."

    # ── ACTION: ANALYZE VOICE ─────────────────────────────────────────────────
    elif action == "analyze_voice":
        if player and hasattr(player, "write_log"):
            player.write_log(f"[VoiceRecognition]: Analyzing voice acoustics ({duration}s)...")

        res = voice_manager.analyze_voice(duration=duration)
        if not res.get("ok"):
            return f"Voice analysis failed: {res.get('error')}"

        an = res.get("analysis", {})
        pitch = an.get("fundamental_frequency_hz", 0)
        clarity = an.get("voice_clarity_score_pct", 0)
        cls = an.get("pitch_classification", "Standard")

        if player and hasattr(player, "show_content"):
            player.show_content(
                "Acoustic Voice Diagnostics",
                f"### Live Acoustic Analysis\n\n"
                f"- **Fundamental Pitch (F0)**: `{pitch} Hz` ({cls})\n"
                f"- **Pitch Stability**: `±{an.get('pitch_stability_std_hz')} Hz`\n"
                f"- **Vocal Tract Centroid**: `{an.get('vocal_resonance_centroid_hz')} Hz`\n"
                f"- **Speech Clarity**: `{clarity}%`\n"
                f"- **Energy Rolloff**: `{an.get('frequency_energy_rolloff_hz')} Hz`"
            )

        return f"Acoustic analysis complete: Fundamental pitch is {pitch} Hz ({cls}), with {clarity}% speech clarity."

    # ── ACTION: LIST SPEAKERS ─────────────────────────────────────────────────
    elif action == "list_speakers":
        speakers = voice_manager.list_speakers()
        if not speakers:
            return "No voice profiles are currently enrolled in the vault."

        lines = ["### Enrolled Voice Profiles\n"]
        for s in speakers:
            lines.append(f"- **{s['speaker']}**: Enrolled {s['created_at']} | Pitch: {s['pitch_hz']} Hz")

        if player and hasattr(player, "show_content"):
            player.show_content("Enrolled Speakers", "\n".join(lines))

        names = ", ".join(s["speaker"] for s in speakers)
        return f"Enrolled speakers in database: {names}."

    # ── ACTION: DELETE SPEAKER ────────────────────────────────────────────────
    elif action == "delete_speaker":
        target = speaker_name
        if not target:
            return "Please provide the name of the speaker profile to delete."

        ok = voice_manager.delete_speaker(target)
        if ok:
            return f"Voice profile for '{target}' has been deleted."
        else:
            return f"No voice profile found for '{target}'."

    return f"Unknown voice recognition action: {action}"
