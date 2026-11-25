"""
plugins/proactive_office_assistant.py — Proactive Daily Office Rhythm Plugin.

Manages morning executive briefings, midday hydration checks, and 4 PM wrap-ups.
"""
from __future__ import annotations

PLUGIN = {
    "name": "proactive_office_assistant",
    "description": (
        "Proactive Office Assistant. Delivers morning briefings at 9 AM, midday wellness checks at 1 PM, "
        "and daily wrap-up summaries at 4 PM aligned with Faisal's office hours."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["start_rhythm", "status", "trigger_morning", "trigger_wrapup"],
                "description": "Control or trigger daily proactive routines."
            }
        },
        "required": ["action"]
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action", "status").strip().lower()

    try:
        from core.proactive_rhythm import office_rhythm
    except Exception as e:
        return f"Proactive rhythm engine error: {e}"

    if action == "start_rhythm":
        office_rhythm.start()
        if player and hasattr(player, "write_log"):
            player.write_log("[ProactiveRhythm]: Daily rhythm active (9 AM - 4 PM PKT).")
        return "Proactive daily office rhythm engine is active."

    elif action == "trigger_morning":
        office_rhythm._trigger_morning_briefing()
        return "Morning executive briefing triggered on HUD."

    elif action == "trigger_wrapup":
        office_rhythm._trigger_office_wrapup()
        return "Daily office wrap-up triggered on HUD."

    else:
        return f"Proactive Office Rhythm status: Active={office_rhythm._running}, Schedule=9 AM to 4 PM PKT."
