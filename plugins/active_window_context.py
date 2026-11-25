"""
plugins/active_window_context.py — Active Window Context Fusion Plugin for JARVIS.

Enables JARVIS to automatically explain errors, analyze code, or summarize the active window.
"""
from __future__ import annotations

PLUGIN = {
    "name": "active_window_context",
    "description": (
        "Active Window Context Fusion. Identifies what app, code, error, or document Faisal "
        "is currently looking at on screen to provide instant context-aware assistance."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["get_context", "capture_crop"],
                "description": "Get window info summary or capture cropped visual screenshot."
            }
        }
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action", "get_context").strip().lower()

    try:
        from core.screen_context import get_screen_context_summary, capture_active_window_screenshot
    except Exception as e:
        return f"Screen context engine error: {e}"

    if action == "capture_crop":
        b, mime = capture_active_window_screenshot()
        if b:
            if player and hasattr(player, "show_content"):
                player.show_content("Active Window Capture", f"Captured {len(b):,} bytes from foreground window.")
            return f"Captured active window screenshot ({len(b):,} bytes)."
        else:
            return f"Failed to capture active window: {mime}"

    else:
        ctx = get_screen_context_summary()
        title = ctx.get("active_window")
        proc = ctx.get("process")
        cat = ctx.get("category")

        card = (
            f"### Active Screen Context\n\n"
            f"- **Foreground App**: `{proc}`\n"
            f"- **Window Title**: `{title}`\n"
            f"- **Focus Domain**: `{cat}`\n"
            f"- **Timestamp**: `{ctx.get('timestamp')}`\n\n"
            f"*Context is automatically fused into assistant reasoning.*"
        )
        if player and hasattr(player, "show_content"):
            player.show_content("Active Screen Context", card)
        if player and hasattr(player, "write_log"):
            player.write_log(f"[ScreenContext]: {proc} - {title[:40]}")

        return f"Currently active window is '{title}' in {proc} ({cat})."
