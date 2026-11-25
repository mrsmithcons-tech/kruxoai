"""
plugins/stonic_theme_switcher.py — Stonic Holographic Sci-Fi Theme Switcher for JARVIS.

Allows voice-activated retheming of the entire JARVIS desktop HUD:
- Stonic Cyan (#00f0ff): Signature glowing AI companion aesthetic
- Titanium Gold (#ffd700): Sci-Fi Cyber Armor look
- Matrix Emerald (#00ff88): Cyberpunk terminal neon
- Crimson Arc (#ff2a55): High-alert stealth mode
- Cyberpunk Purple (#bd00ff): Futuristic synthwave
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config" / "api_keys.json"

PLUGIN = {
    "name": "stonic_theme_switcher",
    "description": (
        "Switch the visual sci-fi color theme of the JARVIS HUD. "
        "Available themes: 'stonic_cyan', 'titanium_gold', 'matrix_emerald', 'crimson_arc', 'cyberpunk_purple'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "theme_name": {
                "type": "STRING",
                "enum": [
                    "stonic_cyan",
                    "titanium_gold",
                    "matrix_emerald",
                    "crimson_arc",
                    "cyberpunk_purple"
                ],
                "description": "Theme name to apply."
            }
        },
        "required": ["theme_name"]
    }
}

THEME_MAP = {
    "stonic_cyan": ("#00f0ff", "Stonic Holographic Cyan"),
    "titanium_gold": ("#ffd700", "Cyber Armor Titanium Gold"),
    "matrix_emerald": ("#00ff88", "Matrix Cyber Emerald"),
    "crimson_arc": ("#ff2a55", "Crimson Arc Reactor"),
    "cyberpunk_purple": ("#bd00ff", "Cyberpunk Synthwave Purple")
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    raw_name = parameters.get("theme_name", "stonic_cyan").strip().lower()
    theme_key = raw_name.replace(" ", "_")

    if theme_key not in THEME_MAP:
        for k in THEME_MAP:
            if k in theme_key:
                theme_key = k
                break

    if theme_key not in THEME_MAP:
        return f"Unknown theme '{raw_name}'. Available: {', '.join(THEME_MAP.keys())}."

    hex_color, display_name = THEME_MAP[theme_key]

    try:
        from gui.theme import apply_ui_accent, current_palette
        apply_ui_accent(hex_color)

        # Save to config so it persists
        try:
            if CONFIG_FILE.exists():
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                cfg["ui_accent_color"] = hex_color
                cfg["theme_name"] = theme_key
                CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

        if player and hasattr(player, "show_content"):
            player.show_content(
                "🎨 Holographic Theme Updated",
                f"### Theme Applied: {display_name}\n\n"
                f"- **Accent Hex**: `{hex_color}`\n"
                f"- **Palette**: Live dynamic hue derivation active\n"
                f"- **Aesthetic**: Stonic Sci-Fi Companion"
            )
        if player and hasattr(player, "write_log"):
            player.write_log(f"[Theme]: Switched to {display_name} ({hex_color}).")

        return f"Theme updated to {display_name}, Faisal."
    except Exception as e:
        return f"Theme switch failed: {e}"
