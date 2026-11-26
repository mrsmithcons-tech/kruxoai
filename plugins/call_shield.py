"""
plugins/call_shield.py — Instant Call Shield & Mute for Phone / Conference Calls.

Allows the assistant to be put into Call Mode via voice or automation:
immediately stops KruxoAI speaking and mutes the microphone.
"""
from __future__ import annotations

PLUGIN = {
    "name": "call_shield",
    "description": (
        "Activate or deactivate Call Mode / Call Shield when the user is on a phone call, "
        "Zoom, Teams, or conference call. Immediately stops KruxoAI from speaking and mutes the microphone."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'start' to mute and silence for a call, 'stop' to unmute and resume listening, or 'toggle'.",
                "enum": ["start", "stop", "toggle"],
            }
        },
        "required": ["action"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action", "toggle")).strip().lower()

    if player is None:
        return "Call Shield command received, but UI player is currently offline."

    try:
        # Check current muted state if player has it
        is_muted = getattr(player, "muted", False)

        if action == "start":
            if not is_muted and hasattr(player, "toggle_call_mode"):
                player.toggle_call_mode()
            return "Call Mode activated. Microphone muted and audio silenced for your call."
        elif action == "stop":
            if is_muted and hasattr(player, "toggle_call_mode"):
                player.toggle_call_mode()
            return "Call Mode deactivated. Microphone is active and I am listening."
        else:
            if hasattr(player, "toggle_call_mode"):
                player.toggle_call_mode()
            return "Call Mode toggled."
    except Exception as e:
        return f"Could not toggle Call Shield: {e}"
