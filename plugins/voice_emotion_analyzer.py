"""
plugins/voice_emotion_analyzer.py — Vocal Emotion & Fatigue Diagnostics Plugin for JARVIS.

Analyzes vocal jitter, shimmer, speaking pace, and stress levels from live speech.
"""
from __future__ import annotations

PLUGIN = {
    "name": "voice_emotion_analyzer",
    "description": (
        "Voice Emotion & Stress Diagnostics. Analyzes vocal jitter, shimmer, speaking pace, "
        "and fatigue levels to provide wellness insights and adaptive tone recommendations."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "duration": {
                "type": "NUMBER",
                "description": "Duration to listen and analyze voice (default: 3.0 seconds)."
            }
        }
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    duration = float(parameters.get("duration", 3.0))

    try:
        from core.voice_emotion import analyze_vocal_emotion
    except Exception as e:
        return f"Voice emotion engine import error: {e}"

    if player and hasattr(player, "write_log"):
        player.write_log(f"[VoiceEmotion]: Listening ({duration}s) to diagnose vocal stress & fatigue...")

    res = analyze_vocal_emotion(duration=duration)
    if not res.get("ok"):
        return f"Vocal analysis failed: {res.get('error')}"

    state = res.get("emotional_state")
    stress = res.get("stress_level_pct")
    health = res.get("vocal_health_score_pct")
    metrics = res.get("metrics", {})
    advice = res.get("wellness_advice")

    card = (
        f"### Vocal Emotion & Wellness Diagnosis\n\n"
        f"- **Vocal State**: `{state}`\n"
        f"- **Stress Indicator**: `{stress}%`\n"
        f"- **Vocal Health Score**: `{health}%`\n"
        f"- **Pitch Jitter**: `{metrics.get('pitch_jitter_pct')}%` (Normal: < 1.8%)\n"
        f"- **Vocal Shimmer**: `{metrics.get('vocal_shimmer_pct')}%` (Normal: < 3.8%)\n"
        f"- **Speaking Pace**: `{metrics.get('speaking_pace_syllables_per_sec')} syllables/sec`\n\n"
        f"**Wellness Recommendation:**\n"
        f"> {advice}"
    )

    if player and hasattr(player, "show_content"):
        player.show_content("Vocal Emotion & Stress Diagnostics", card)
    if player and hasattr(player, "write_log"):
        player.write_log(f"[VoiceEmotion]: State: {state} (Stress: {stress}%)")

    return f"Vocal diagnostic complete: User is {state} with {stress}% stress index. {advice}"
