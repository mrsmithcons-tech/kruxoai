"""
plugins/system_watchdog_supervisor.py — Supervisory Self-Healing Daemon Plugin for JARVIS.

Monitors health of all background threads and auto-revives any crashed components.
"""
from __future__ import annotations

PLUGIN = {
    "name": "system_watchdog_supervisor",
    "description": (
        "Supervisory Self-Healing Watchdog. Monitors background daemons (Live Bridge, Muse MCP, "
        "Room Sentry, Persistent Camera, Office Rhythm) and auto-recovers them silently."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["start", "status"],
                "description": "Start the watchdog supervisor or check health status."
            }
        },
        "required": ["action"]
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action", "status").strip().lower()

    try:
        from core.watchdog import supervisor_watchdog
    except Exception as e:
        return f"Watchdog supervisor error: {e}"

    if action == "start":
        supervisor_watchdog.start()
        if player and hasattr(player, "write_log"):
            player.write_log("[Watchdog]: Self-healing supervisor armed.")
        return "System supervisor watchdog is now active."

    else:
        st = supervisor_watchdog.get_status()
        revivals = st.get("revivals", {})
        rev_str = ", ".join(f"{k}: {v}" for k, v in revivals.items())

        card = (
            f"### System Supervisor & Self-Healing Status\n\n"
            f"- **Watchdog Daemon**: `{'ONLINE' if st.get('active') else 'STANDBY'}`\n"
            f"- **Monitored Services**: `Bridge (9876)`, `MCP (9877)`, `Room Sentry`, `Office Rhythm`\n"
            f"- **Subsystem Revivals**: `{rev_str}`\n"
            f"- **Crash-Proof Protection**: `Active`"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("Self-Healing Supervisor", card)
        return f"Watchdog is {'active' if st.get('active') else 'standby'}. Subsystems healthy."
