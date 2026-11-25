"""
plugins/biometric_fusion_security.py — Multimodal Biometric Fusion (Face + Voice 2FA) Plugin.

Allows JARVIS to authenticate privileged operations using simultaneous Face & Voice verification.
"""
from __future__ import annotations

PLUGIN = {
    "name": "biometric_fusion_security",
    "description": (
        "Multimodal Biometric 2FA Engine. Authenticates actions using simultaneous "
        "OpenCV Face Tracking and Mel-Cepstral Voice Biometrics for Faisal."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["authenticate", "status"],
                "description": "Authenticate via 2FA or check current biometric security status."
            },
            "security_level": {
                "type": "STRING",
                "enum": ["HIGH", "STANDARD"],
                "description": "HIGH requires both Face AND Voice match. STANDARD requires composite >= 65%."
            }
        },
        "required": ["action"]
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action", "authenticate").strip().lower()
    level = parameters.get("security_level", "HIGH").upper()

    try:
        from core.biometric_fusion import authenticate_2fa, _check_face_presence
        from core.voice_engine import voice_manager
    except Exception as e:
        return f"Biometric fusion engine unavailable: {e}"

    if action == "status":
        face = _check_face_presence()
        profiles = voice_manager.list_speakers()
        enrolled_names = ", ".join(p["speaker"] for p in profiles) if profiles else "None"

        card = (
            f"### Biometric Fusion Security Status\n\n"
            f"- **Face Presence**: {'Active (In Front of PC)' if face.get('present') else 'User Away'}\n"
            f"- **Enrolled Voice Profiles**: `{enrolled_names}`\n"
            f"- **Two-Factor Mode**: `Face + Voice 2FA Active`\n"
            f"- **Security Standard**: `Biometric Fusion Mark LVII`"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("Biometric 2FA Status", card)
        return f"Biometric Status: Face is {'present' if face.get('present') else 'away'}, Enrolled voices: {enrolled_names}."

    elif action == "authenticate":
        if player and hasattr(player, "write_log"):
            player.write_log("[Biometric 2FA]: Initiating simultaneous Face + Voice authentication...")

        res = authenticate_2fa(speaker_name="Faisal", duration=2.5, level=level)
        auth = res.get("authenticated", False)
        comp = res.get("composite_score_pct", 0.0)
        face_v = res.get("face_factor", {}).get("verified")
        voice_v = res.get("voice_factor", {}).get("verified")
        voice_conf = res.get("voice_factor", {}).get("confidence_pct", 0.0)

        badge = "✅ **AUTHENTICATION GRANTED**" if auth else "❌ **AUTHENTICATION DENIED**"
        card = (
            f"### Two-Factor Biometric Fusion: {badge}\n\n"
            f"- **User**: `Faisal`\n"
            f"- **Security Level**: `{level}`\n"
            f"- **Factor 1 (Face Presence)**: {'Verified' if face_v else 'Failed / Not Detected'}\n"
            f"- **Factor 2 (Voice Biometrics)**: {'Verified' if voice_v else 'Failed'} (`{voice_conf}% match`)\n"
            f"- **Composite Biometric Score**: `{comp}%`\n"
            f"- **Audit Event**: Logged to `memory/biometric_2fa_audit.json`"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("2FA Biometric Fusion", card)
        if player and hasattr(player, "write_log"):
            player.write_log(f"[Biometric 2FA]: Result = {auth} (Composite: {comp}%)")

        if auth:
            return f"Two-factor biometric authentication successful for Faisal ({comp}% composite confidence)."
        else:
            return f"Biometric 2FA denied: Face verified={face_v}, Voice verified={voice_v} ({voice_conf}% confidence)."

    return f"Unknown 2FA action: {action}"
