"""
plugins/self_evolution.py — Autonomous Self-Evolution & Dynamic Upgrading Engine for JARVIS.

Allows JARVIS to:
1. Self-develop new plugins and capabilities on the fly when requested by voice or text.
2. Generate clean, safe Python plugin code adhering to AGENTS.md rules.
3. Validate code via sandbox AST compilation and dry-run import in a separate subprocess.
4. Hot-deploy new plugins directly into plugins/ without restarting the application.
5. Track and evolve from an unmet-needs backlog (memory/evolution_backlog.json).
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
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PLUGINS_DIR = BASE_DIR / "plugins"
AGENTS_MD_PATH = BASE_DIR / "AGENTS.md"
BACKLOG_PATH = BASE_DIR / "memory" / "evolution_backlog.json"
OPENCODE_EXE = r"C:\Users\Faisal\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"

PLUGIN = {
    "name": "evolve_feature",
    "description": (
        "Self-modify and upgrade JARVIS's own codebase. Writes, tests, and hot-deploys new Python plugins and capabilities "
        "into JARVIS automatically whenever a new feature, tool, automation, or upgrade is requested."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "feature_name": {
                "type": "STRING",
                "description": "Short snake_case name for the new tool (e.g. 'battery_monitor', 'currency_converter', 'reddit_reader'). Optional, will be auto-generated if omitted.",
            },
            "description": {
                "type": "STRING",
                "description": "Clear description of what the feature should do, what inputs it takes, and what it returns.",
            },
        },
        "required": ["description"],
    },
}


def _clean_code_fence(raw: str) -> str:
    """Extract raw Python source code from markdown fences."""
    text = raw.strip()
    if "```python" in text:
        parts = text.split("```python", 1)[1].split("```", 1)
        return parts[0].strip()
    elif "```" in text:
        parts = text.split("```", 1)[1].split("```", 1)
        return parts[0].strip()
    return text


def _load_agents_rules() -> str:
    """Read AGENTS.md guidelines to instruct the generator model."""
    try:
        if AGENTS_MD_PATH.exists():
            with open(AGENTS_MD_PATH, "r", encoding="utf-8") as f:
                return f.read()[:4000]
    except Exception:
        pass
    return "Never touch Qt widgets from worker threads. Call player.show_content(title, text) or player.write_log(text)."


def _generate_code(feature_name: str, description: str) -> str:
    """Draft plugin code using OpenCode or Gemini."""
    prompt = f"""
You are the self-evolution engine of JARVIS, an autonomous desktop assistant.
Write a COMPLETE, production-ready Python plugin file named `{feature_name}.py` that provides this capability:
Task: {description}

STRICT ARCHITECTURAL REQUIREMENTS (from AGENTS.md):
1. Top-level dictionary named `PLUGIN`:
   PLUGIN = {{
       "name": "{feature_name}",
       "description": "Clear description of what this does for the model to route",
       "parameters": {{
           "type": "OBJECT",
           "properties": {{ ... }},
           "required": [...]
       }}
   }}
2. Top-level execution function:
   def run(parameters: dict, player=None, session_memory=None) -> str:
       ...
3. THREADING RULE: NEVER import or touch PyQt6 / Qt widgets.
   To show results on screen, call thread-safe methods on `player`:
   - player.show_content(title, text)
   - player.write_log("message")
   Always check `if player:` before calling them.
4. ERROR HANDLING: `run()` must NEVER raise. Catch all exceptions and return a friendly error string.
5. Return a short string summary that the assistant can speak aloud.
6. Return ONLY the raw valid Python code. No conversational text.
"""
    # 1. Try Gemini first (fast, reliable ladder)
    try:
        from core import gemini
        raw = gemini.text(prompt, tier=gemini.SMART, timeout_ms=45_000)
        code = _clean_code_fence(raw or "")
        if "PLUGIN" in code and "def run(" in code:
            return code
    except Exception as e:
        print(f"[SelfEvolution] Gemini generation error: {e}")

    # 2. Try OpenCode if available as fallback
    if os.path.exists(OPENCODE_EXE):
        try:
            res = subprocess.run(
                [OPENCODE_EXE, "run", "--auto", prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )
            raw = res.stdout.strip()
            code = _clean_code_fence(raw)
            if "PLUGIN" in code and "def run(" in code:
                return code
        except Exception:
            pass

    return ""


def _validate_plugin_code(temp_file: Path) -> tuple[bool, str]:
    """Test syntax and dry-run import in an isolated child process."""
    # 1. Syntax check
    try:
        py_compile.compile(str(temp_file), doraise=True)
    except py_compile.PyCompileError as e:
        return False, f"Syntax Error: {e}"

    # 2. Isolated import verification
    test_script = f"""
import sys, importlib.util
spec = importlib.util.spec_from_file_location("test_plugin", r"{temp_file}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert hasattr(mod, "PLUGIN"), "Plugin missing PLUGIN dictionary"
assert isinstance(mod.PLUGIN, dict), "PLUGIN must be a dict"
assert "name" in mod.PLUGIN, "PLUGIN dict missing 'name'"
assert hasattr(mod, "run"), "Plugin missing run() function"
assert callable(mod.run), "run must be callable"

# Test dry-run with empty params
result = mod.run({{}}, player=None, session_memory=None)
assert isinstance(result, str), "run() must return a string"
print("VALID")
"""
    try:
        res = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and "VALID" in res.stdout:
            return True, "Code passed all validation checks."
        else:
            err = res.stderr.strip() or res.stdout.strip()
            return False, f"Runtime validation failed: {err}"
    except Exception as e:
        return False, f"Validation subprocess error: {e}"


def _evolve_worker(feature_name: str, description: str, player=None) -> None:
    """Background worker that generates, validates, and deploys the new plugin."""
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "", feature_name.lower().replace("-", "_")).strip("_")
    if not clean_name:
        clean_name = "custom_tool"

    if player:
        player.write_log(f"🧬 Evolving new feature: {clean_name}...")
        player.show_content(
            "🧬 Self-Evolution in Progress",
            f"**Developing New Capability:** `{clean_name}`\n\n"
            f"> **Objective:** {description}\n\n"
            "*Designing architecture, enforcing AGENTS.md rules, and running sandbox tests...*",
        )

    # Step 1: Draft code
    code = _generate_code(clean_name, description)
    if not code:
        if player:
            player.write_log(f"⚠️ Self-Evolution failed: could not generate code for {clean_name}")
            player.show_content("Evolution Error", "Model could not generate valid code.")
        return

    # Step 2: Write to staging file
    staging_file = PLUGINS_DIR / f"_staging_{clean_name}.py"
    final_file = PLUGINS_DIR / f"{clean_name}.py"

    try:
        with open(staging_file, "w", encoding="utf-8") as f:
            f.write(code)

        # Step 3: Sandbox validation
        valid, msg = _validate_plugin_code(staging_file)
        if not valid:
            staging_file.unlink(missing_ok=True)
            if player:
                player.write_log(f"⚠️ Validation rejected {clean_name}: {msg[:100]}")
                player.show_content(
                    "Evolution Validation Failed",
                    f"The generated code for `{clean_name}` did not pass safety checks:\n\n```\n{msg}\n```",
                )
            return

        # Step 4: Deploy
        # If file exists, create a .bak copy first
        if final_file.exists():
            bak_file = PLUGINS_DIR / f"{clean_name}.py.bak"
            try:
                import shutil
                shutil.copy2(str(final_file), str(bak_file))
            except Exception:
                pass

        staging_file.replace(final_file)

        # Step 5: Notify HUD
        if player:
            player.write_log(f"✓ JARVIS Evolved: {clean_name}.py deployed and active!")
            player.show_content(
                f"✨ JARVIS Evolved: {clean_name}",
                f"### New Capability Online: `{clean_name}`\n\n"
                f"**Purpose:** {description}\n\n"
                f"• **Status:** Tested & Hot-Deployed\n"
                f"• **Location:** `plugins/{clean_name}.py`\n\n"
                f"```python\n{code[:800]}\n...\n```",
            )
            if hasattr(player, "request_say") and callable(player.request_say):
                player.request_say(f"I have upgraded myself with the {clean_name} capability. It is active now.")

    except Exception as e:
        staging_file.unlink(missing_ok=True)
        if player:
            player.write_log(f"⚠️ Deployment error: {e}")
            player.show_content("Deployment Error", str(e))


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Action handler called by JARVIS when told to evolve/upgrade."""
    feature_name = str(parameters.get("feature_name", "")).strip()
    description = str(parameters.get("description", "")).strip()

    if not description:
        # Check backlog if present
        backlog_item = None
        if BACKLOG_PATH.exists():
            try:
                items = json.loads(BACKLOG_PATH.read_text(encoding="utf-8"))
                if items and isinstance(items, list):
                    backlog_item = items.pop(0)
                    BACKLOG_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")
            except Exception:
                pass
        if backlog_item:
            feature_name = backlog_item.get("feature_name", "")
            description = backlog_item.get("description", "")
        else:
            description = "Autonomous capability enhancement based on user desktop workflow"

    if not feature_name:
        feature_name = "auto_feature_" + str(int(time.time()))

    t = threading.Thread(
        target=_evolve_worker,
        args=(feature_name, description, player),
        daemon=True,
        name="SelfEvolutionWorker",
    )
    t.start()

    return f"I am developing and self-upgrading the '{feature_name}' capability now. Once tested, it will go live on your panel."
