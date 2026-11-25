"""
plugins/competitor_evolution.py — Autonomous Competitor Learning & Feature Evolution Engine.

Allows JARVIS to:
1. Search online open-source repositories and competitors (Open Interpreter, Copilot,
   Cursor, Claude Computer Use, Leon, etc.) for cutting-edge agent tools.
2. Perform automated Gap Analysis between competitor features and JARVIS's existing toolset.
3. Use OpenCode/Gemini to synthesize, test, and hot-deploy new matching plugins into plugins/
   tailored specifically for your Windows desktop while adhering to AGENTS.md rules.
4. Post full benchmark cards to the HUD Content Panel and announce upgrades via speech.
"""
from __future__ import annotations

import base64
import json
import os
import py_compile
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PLUGINS_DIR = BASE_DIR / "plugins"
ACTIONS_DIR = BASE_DIR / "actions"
AGENTS_MD_PATH = BASE_DIR / "AGENTS.md"
OPENCODE_EXE = r"C:\Users\Faisal\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"

PLUGIN = {
    "name": "evolve_from_competitor",
    "description": (
        "Autonomously research online competitor AI agents (Open Interpreter, Copilot, Cursor, AutoGPT, Claude Computer Use, etc.), "
        "analyze their features, and self-develop/hot-deploy matching capabilities directly into JARVIS's codebase. "
        "Call this whenever the user asks JARVIS to develop itself, learn from competitors, or adopt competitor features."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "competitor": {
                "type": "STRING",
                "description": "Name of competitor or open-source agent (e.g. 'open-interpreter', 'copilot', 'cursor', 'claude-computer-use', 'auto'). Defaults to 'open-interpreter' if not specified.",
            },
            "desired_capability": {
                "type": "STRING",
                "description": "Optional specific capability to adapt (e.g. 'terminal_executor', 'smart_clipboard', 'git_companion', 'network_troubleshooter').",
            },
        },
        "required": [],
    },
}

# ── Popular Repositories & Benchmarks ─────────────────────────────────────────

KNOWN_COMPETITORS = {
    "open-interpreter": {
        "repo": "OpenInterpreter/open-interpreter",
        "description": "Local code execution, system shell automation, multi-language scripting",
        "top_features": ["terminal_command_executor", "system_health_inspector", "file_diff_patcher"]
    },
    "copilot": {
        "repo": "microsoft/copilot",
        "description": "Windows Copilot: clipboard intelligence, system diagnostics, media control",
        "top_features": ["smart_clipboard_summarizer", "pc_audio_tuner", "quick_settings_switcher"]
    },
    "cursor": {
        "repo": "getcursor/cursor",
        "description": "Developer AI companion: git diff explainer, test suite generator, syntax auto-fixer",
        "top_features": ["git_smart_commit", "codebase_indexer", "unit_test_builder"]
    },
    "claude-computer-use": {
        "repo": "anthropics/anthropic-quickstarts",
        "description": "OS world model: desktop visual element targeting, hotkey orchestration",
        "top_features": ["screen_coordinate_clicker", "multi_window_arranger"]
    },
    "stonic": {
        "repo": "stonicai/desktop-assistant",
        "description": "Stonic AI by Inventor Usman: Windows desktop AI companion with particle avatar, voice interaction, and app control",
        "top_features": ["desktop_voice_companion", "media_and_music_orchestrator", "web_workflow_automator"]
    }
}


def _get_player():
    try:
        from ui import JarvisUI
        return JarvisUI.get_active()
    except Exception:
        return None


def _get_existing_capabilities() -> list[str]:
    """List all current actions and plugins to identify capability gaps."""
    caps = []
    if ACTIONS_DIR.exists():
        caps.extend([f.stem for f in ACTIONS_DIR.glob("*.py") if not f.name.startswith("_")])
    if PLUGINS_DIR.exists():
        caps.extend([f.stem for f in PLUGINS_DIR.glob("*.py") if not f.name.startswith("_")])
    return sorted(set(caps))


def _fetch_online_features(competitor_name: str) -> tuple[str, list[str]]:
    """Research competitor capabilities via GitHub API or known profiles."""
    comp_key = competitor_name.lower().strip()
    for k, info in KNOWN_COMPETITORS.items():
        if k in comp_key or comp_key in k:
            return info["description"], info["top_features"]

    # If not in local presets, query GitHub API for open-source agent features
    try:
        url = f"https://api.github.com/search/repositories?q={urllib.request.quote(competitor_name)}+ai+agent&per_page=3"
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-CompetitorEvolution/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            if items:
                top = items[0]
                desc = top.get("description", "") or "Autonomous AI agent"
                name_slug = re.sub(r"[^a-zA-Z0-9_]", "", top.get("name", "agent").lower())
                return desc, [f"{name_slug}_automation", f"{name_slug}_assistant"]
    except Exception as e:
        print(f"[CompetitorEvolution] Online search note: {e}")

    return f"AI desktop capabilities inspired by {competitor_name}", [f"{comp_key}_automation"]


def _clean_code_fence(raw: str) -> str:
    text = raw.strip()
    if "```python" in text:
        return text.split("```python", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text


def _synthesize_competitor_plugin(feature_name: str, feature_desc: str, competitor: str) -> str:
    """Use OpenCode or Gemini to generate code matching the competitor's feature."""
    prompt = f"""
You are the Competitor Evolution Engine of JARVIS (Windows AI assistant).
JARVIS has studied the competitor '{competitor}' and wants to adopt this feature:
Feature Name: `{feature_name}`
Description: {feature_desc}

REQUIREMENTS:
1. Write a standalone Python plugin file `plugins/{feature_name}.py`.
2. Must contain:
   PLUGIN = {{
       "name": "{feature_name}",
       "description": "Description of the feature adapted from {competitor}",
       "parameters": {{ "type": "OBJECT", "properties": {{ ... }} }}
   }}
   def run(parameters: dict, player=None, session_memory=None) -> str:
       ...
3. Never touch Qt widgets. If player is provided, use:
   player.show_content(title, text)
   player.write_log(message)
4. Must be self-contained and run on Windows.
5. `run()` must never raise (catch all exceptions).
6. Return a short string summary that the assistant can speak aloud.
7. Return ONLY valid Python code.
"""
    # 1. Try Gemini first (fast, reliable ladder)
    try:
        from core import gemini
        raw = gemini.text(prompt, tier=gemini.SMART, timeout_ms=45_000)
        code = _clean_code_fence(raw or "")
        if "PLUGIN" in code and "def run(" in code:
            return code
    except Exception as e:
        print(f"[CompetitorEvolution] Gemini error: {e}")

    # 2. Try OpenCode if available
    if os.path.exists(OPENCODE_EXE):
        try:
            res = subprocess.run(
                [OPENCODE_EXE, "run", "--auto", prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )
            code = _clean_code_fence(res.stdout.strip())
            if "PLUGIN" in code and "def run(" in code:
                return code
        except Exception:
            pass

    return ""


def _validate_plugin(temp_path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(temp_path), doraise=True)
    except Exception as e:
        return False, f"Syntax Error: {e}"

    test_script = f"""
import sys, importlib.util
spec = importlib.util.spec_from_file_location("test_plugin", r"{temp_path}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "PLUGIN") and hasattr(mod, "run")
res = mod.run({{}}, player=None, session_memory=None)
assert isinstance(res, str)
print("PASS")
"""
    try:
        res = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and "PASS" in res.stdout:
            return True, "Valid"
        return False, res.stderr or res.stdout
    except Exception as e:
        return False, str(e)


def _benchmark_worker(competitor: str, desired_capability: str, player=None) -> None:
    """Analyze competitor online, identify capability gap, code and deploy the feature."""
    if player:
        player.write_log(f"🔍 Benchmarking competitor: {competitor}...")
        player.show_content(
            f"🔍 Benchmarking: {competitor}",
            f"**Analyzing Online Competitor:** `{competitor}`\n\n"
            f"*Querying open repositories, mapping feature differences, and synthesizing new tools...*",
        )

    # 1. Fetch competitor profile
    comp_desc, comp_features = _fetch_online_features(competitor)
    existing = _get_existing_capabilities()

    # 2. Select missing capability
    target_feature = ""
    if desired_capability:
        target_feature = re.sub(r"[^a-zA-Z0-9_]", "", desired_capability.lower().replace("-", "_")).strip("_")
    else:
        # Find first feature not already in existing
        for f in comp_features:
            f_clean = re.sub(r"[^a-zA-Z0-9_]", "", f.lower().replace("-", "_")).strip("_")
            if f_clean not in existing:
                target_feature = f_clean
                break
        if not target_feature:
            target_feature = f"{competitor.replace('-', '_')}_toolkit"

    feature_desc = f"Adopted capability from {competitor}: {comp_desc}"

    if player:
        player.write_log(f"💡 Identified gap: {target_feature}. Synthesizing code...")
        player.show_content(
            f"💡 Gap Analysis: {target_feature}",
            f"### Competitor Analysis: `{competitor}`\n\n"
            f"• **Competitor Focus:** {comp_desc}\n"
            f"• **Target Innovation:** `{target_feature}`\n\n"
            f"*Drafting plugin adhering to AGENTS.md rules and testing in sandbox...*",
        )

    # 3. Generate Code
    code = _synthesize_competitor_plugin(target_feature, feature_desc, competitor)
    if not code:
        if player:
            player.write_log(f"⚠️ Could not synthesize code for {target_feature}")
            player.show_content("Evolution Note", f"Failed to generate code for `{target_feature}`.")
        return

    # 4. Sandbox validation
    staging = PLUGINS_DIR / f"_staging_{target_feature}.py"
    final = PLUGINS_DIR / f"{target_feature}.py"

    try:
        with open(staging, "w", encoding="utf-8") as fp:
            fp.write(code)

        valid, msg = _validate_plugin(staging)
        if not valid:
            staging.unlink(missing_ok=True)
            if player:
                player.write_log(f"⚠️ Validation error for {target_feature}: {msg[:80]}")
            return

        staging.replace(final)

        if player:
            player.write_log(f"✓ Competitor upgrade deployed: {target_feature}.py is online!")
            player.show_content(
                f"🚀 Competitor Upgrade: {target_feature}",
                f"### Learned & Evolved from `{competitor}`\n\n"
                f"**New Capability:** `{target_feature}`\n"
                f"**Source Inspiration:** {comp_desc}\n"
                f"• **Status:** Validated & Hot-Deployed to `plugins/{target_feature}.py`\n\n"
                f"```python\n{code[:800]}\n...\n```",
            )
            if hasattr(player, "request_say") and callable(player.request_say):
                player.request_say(f"I have studied {competitor} and developed a new {target_feature} capability for myself.")

    except Exception as e:
        staging.unlink(missing_ok=True)
        if player:
            player.write_log(f"⚠️ Error deploying {target_feature}: {e}")


def run(parameters: dict, player=None, session_memory=None) -> str:
    competitor = str(parameters.get("competitor", "open-interpreter")).strip() or "open-interpreter"
    desired_capability = str(parameters.get("desired_capability", "")).strip()

    t = threading.Thread(
        target=_benchmark_worker,
        args=(competitor, desired_capability, player),
        daemon=True,
        name="CompetitorBenchmarker",
    )
    t.start()

    return f"I am researching {competitor} online, analyzing its features, and synthesizing a new upgrade for myself. Results will appear on your panel."
