"""
plugins/passive_room_sentry.py — Continuous Passive Room Sentry Plugin for JARVIS.

Monitors room audio continuously in the background for unauthorized voices.
"""
from __future__ import annotations

PLUGIN = {
    "name": "passive_room_sentry",
    "description": (
        "Continuous Passive Room Sentry. Background audio monitor that listens for voices in the room, "
        "identifies Faisal, and triggers security alerts when unrecognized voices are detected."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["start", "stop", "status"],
                "description": "Start, stop, or check status of the passive room sentry."
            }
        },
        "required": ["action"]
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action", "status").strip().lower()

    try:
        from core.room_sentry import room_sentry
    except Exception as e:
        return f"Room sentry engine import error: {e}"

    if action == "start":
        ok = room_sentry.start()
        if ok:
            if player and hasattr(player, "show_content"):
                player.show_content(
                    "Passive Room Sentry",
                    "### Room Sentry Armed\n\n"
                    "- **Status**: Continuous Background Audio Monitoring Active\n"
                    "- **Target**: Faisal (Master)\n"
                    "- **Threat Response**: Auto-alerts on unrecognized voices"
                )
            if player and hasattr(player, "write_log"):
                player.write_log("[RoomSentry]: Continuous passive room sentry armed.")
            return "Passive room sentry is now active and monitoring room audio."
        else:
            return "Failed to start passive room sentry."

    elif action == "stop":
        room_sentry.stop()
        if player and hasattr(player, "write_log"):
            player.write_log("[RoomSentry]: Passive room sentry paused.")
        return "Passive room sentry has been paused."

    elif action == "status":
        st = room_sentry.get_status()
        active = st.get("active", False)
        unrec = st.get("unrecognized_events_today", 0)
        card = (
            f"### Passive Room Sentry Status\n\n"
            f"- **Active**: `{'ONLINE (Listening)' if active else 'OFFLINE (Paused)'}`\n"
            f"- **Authorized Master**: `Faisal`\n"
            f"- **Unrecognized Detections**: `{unrec} events`\n"
            f"- **Last Speech Detected**: `{st.get('last_speech_time')}`\n"
            f"- **Protocol Trigger**: `unrecognized_person_protocol`"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("Room Sentry Status", card)
        return f"Room Sentry is {'active' if active else 'paused'}. {unrec} unrecognized voice events recorded today."

    return f"Unknown room sentry action: {action}"
