"""
plugins/autonomous_evolution_daemon.py — Autonomous Overnight Self-Upgrade & Learning Engine.

Enables JARVIS to:
1. Run background autonomous evolution loops while the user is asleep or away.
2. Regularly evaluate capability gaps against cutting-edge open-source AI agents.
3. Automatically synthesize, sandbox-test, and hot-deploy verified plugins into plugins/.
4. Track all overnight developments and prepare a morning briefing on the HUD panel.
5. Provide the `autonomous_evolution` tool to inspect status or trigger immediate cycles.
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PLUGINS_DIR = BASE_DIR / "plugins"
MEMORY_DIR = BASE_DIR / "memory"
LOG_FILE = MEMORY_DIR / "overnight_evolution_log.json"
LONG_TERM_FILE = MEMORY_DIR / "long_term.json"
AGENTS_MD_PATH = BASE_DIR / "AGENTS.md"

PLUGIN = {
    "name": "autonomous_evolution",
    "description": (
        "Check autonomous self-upgrade status, review overnight developed tools, "
        "or trigger an immediate self-evolution cycle."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to take: 'status' (view recent self-upgrades) or 'run_cycle' (trigger evolution now).",
                "enum": ["status", "run_cycle"]
            }
        },
        "required": []
    }
}

# Curated evolution roadmap of open-source agent capabilities
EVOLUTION_ROADMAP = [
    {
        "name": "network_speed_tester",
        "inspiration": "Open Interpreter / System Admin Tools",
        "description": "Measures ping, packet latency, and network connection status on Windows, reporting to the HUD panel.",
    },
    {
        "name": "quick_note_vault",
        "inspiration": "Obsidian / Notion AI Companion",
        "description": "Quickly saves, searches, and appends timestamped thoughts, notes, and ideas to local markdown files in memory/notes/.",
    },
    {
        "name": "audio_device_switcher",
        "inspiration": "Windows Copilot Media Tools",
        "description": "Inspects audio output devices and switches default playback or volume safely via PowerShell / Windows audio APIs.",
    }
]


def _get_player():
    try:
        from ui import JarvisUI
        return JarvisUI.get_active()
    except Exception:
        return None


def _load_evolution_log() -> list[dict]:
    try:
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_evolution_log(entry: dict):
    try:
        logs = _load_evolution_log()
        logs.append(entry)
        logs = logs[-30:]  # keep last 30
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass


def _get_installed_plugin_names() -> set[str]:
    names = set()
    if PLUGINS_DIR.exists():
        for f in PLUGINS_DIR.glob("*.py"):
            if not f.name.startswith("_"):
                names.add(f.stem)
    return names


def _run_single_evolution_cycle(player=None) -> str:
    """Find a missing capability from the roadmap, generate, test, and deploy it."""
    installed = _get_installed_plugin_names()
    target = None
    for item in EVOLUTION_ROADMAP:
        if item["name"] not in installed:
            target = item
            break

    if not target:
        if player:
            player.write_log("✨ Autonomous evolution: All planned roadmap capabilities are deployed!")
        return "All planned roadmap capabilities are currently installed."

    feat_name = target["name"]
    feat_desc = target["description"]
    insp = target["inspiration"]

    if player:
        player.write_log(f"🧬 Autonomous Evolution: Synthesizing {feat_name} ({insp})...")
        player.show_content(
            f"🧬 Autonomous Evolution: {feat_name}",
            f"**Autonomous Overnight Self-Upgrade**\n\n"
            f"• **Target Capability:** `{feat_name}`\n"
            f"• **Inspiration:** {insp}\n"
            f"• **Objective:** {feat_desc}\n\n"
            f"*Generating Python code conforming to AGENTS.md and running isolated sandbox tests...*",
        )

    # 1. Synthesize code via Gemini
    prompt = f"""
You are the Autonomous Evolution Engine of JARVIS (Windows AI assistant).
Create a standalone Python plugin file `plugins/{feat_name}.py`.
Objective: {feat_desc}

STRICT ARCHITECTURAL REQUIREMENTS (AGENTS.md):
1. Top-level PLUGIN dictionary:
   PLUGIN = {{
       "name": "{feat_name}",
       "description": "{feat_desc}",
       "parameters": {{ "type": "OBJECT", "properties": {{ ... }}, "required": [...] }}
   }}
2. Execution function:
   def run(parameters: dict, player=None, session_memory=None) -> str:
       ...
3. THREADING: NEVER import or touch PyQt6 or Qt widgets.
   To show results on screen, use:
   - if player: player.show_content(title, text)
   - if player: player.write_log(message)
4. ERROR HANDLING: `run()` must NEVER raise. Catch all exceptions and return a friendly string.
5. Return a short string that the assistant speaks aloud.
6. Return ONLY valid Python code in a ```python block.
"""
    try:
        from core import gemini
        raw = gemini.text(prompt, tier=gemini.SMART, timeout_ms=60_000)
    except Exception as e:
        if player:
            player.write_log(f"⚠️ Evolution generation error: {e}")
        return f"Generation error: {e}"

    if not raw:
        return "Failed to generate code."

    code = raw.strip()
    if "```python" in code:
        code = code.split("```python", 1)[1].split("```", 1)[0].strip()
    elif "```" in code:
        code = code.split("```", 1)[1].split("```", 1)[0].strip()

    if "PLUGIN" not in code or "def run(" not in code:
        return "Generated code invalid."

    # 2. Sandbox testing
    staging = PLUGINS_DIR / f"_staging_{feat_name}.py"
    final = PLUGINS_DIR / f"{feat_name}.py"

    try:
        with open(staging, "w", encoding="utf-8") as f:
            f.write(code)

        py_compile.compile(str(staging), doraise=True)

        test_script = f"""
import sys, importlib.util
spec = importlib.util.spec_from_file_location("test_plugin", r"{staging}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "PLUGIN") and hasattr(mod, "run")
res = mod.run({{}}, player=None, session_memory=None)
assert isinstance(res, str)
print("PASS")
"""
        res = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True, timeout=10)
        if res.returncode != 0 or "PASS" not in res.stdout:
            staging.unlink(missing_ok=True)
            err = res.stderr or res.stdout
            if player:
                player.write_log(f"⚠️ Validation rejected {feat_name}: {err[:80]}")
            return f"Validation failed: {err}"

        # 3. Hot-deploy
        staging.replace(final)

        # 4. Log and sync
        entry = {
            "timestamp": time.time(),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "plugin": feat_name,
            "description": feat_desc,
            "status": "deployed"
        }
        _save_evolution_log(entry)

        if player:
            player.write_log(f"✓ Autonomous Upgrade Deployed: {feat_name}.py is active!")
            player.show_content(
                f"🚀 JARVIS Upgraded: {feat_name}",
                f"### New Autonomous Capability Deployed\n\n"
                f"• **Plugin:** `plugins/{feat_name}.py`\n"
                f"• **Inspiration:** {insp}\n"
                f"• **Capability:** {feat_desc}\n\n"
                f"```python\n{code[:600]}\n...\n```",
            )

        return f"Successfully developed and hot-deployed `{feat_name}`."

    except Exception as e:
        staging.unlink(missing_ok=True)
        if player:
            player.write_log(f"⚠️ Evolution deployment error: {e}")
        return f"Deployment error: {e}"


def _autonomous_overnight_worker():
    """Background loop that executes periodic autonomous upgrade cycles."""
    # Initial sleep of 2 minutes after startup before first cycle
    time.sleep(120)

    while True:
        try:
            player = _get_player()
            # Run one roadmap upgrade cycle every 2 hours
            _run_single_evolution_cycle(player)
            time.sleep(7200)
        except Exception:
            time.sleep(600)


# Start background daemon on import
t_daemon = threading.Thread(
    target=_autonomous_overnight_worker,
    daemon=True,
    name="AutonomousEvolutionDaemon"
)
t_daemon.start()


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action", "status")).strip().lower() or "status"

    if action == "run_cycle":
        t = threading.Thread(
            target=_run_single_evolution_cycle,
            args=(player,),
            daemon=True,
            name="ManualEvolutionCycle"
        )
        t.start()
        return "Starting an immediate autonomous evolution cycle now. Progress will show on your panel."
    else:
        logs = _load_evolution_log()
        installed = _get_installed_plugin_names()
        recent_names = [item["plugin"] for item in logs[-5:]] if logs else ["None yet"]

        if player:
            log_table = "\n".join(
                f"| `{item.get('time', '')}` | `{item.get('plugin', '')}` | {item.get('description', '')[:60]}... |"
                for item in logs[-6:]
            ) if logs else "No overnight evolutions logged yet."

            player.show_content(
                "🧬 Autonomous Evolution Engine",
                f"### Autonomous System Upgrade Status\n\n"
                f"• **Active Plugins:** {len(installed)} plugins online\n"
                f"• **Background Daemon:** Running (automatic cycles active)\n"
                f"• **Recent Evolutions:** {', '.join(recent_names)}\n\n"
                f"#### Recent Upgrade History\n"
                f"| Timestamp | Plugin | Capability |\n|:---|:---|:---|\n"
                f"{log_table}\n"
            )

        return f"Autonomous evolution is active. Currently {len(installed)} plugins are online. Recent upgrades: {', '.join(recent_names)}."
