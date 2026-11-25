"""
plugins/opencode_assistant.py — JARVIS Voice & Tool integration for OpenCode.

Allows the user to speak to JARVIS:
  "Hey JARVIS, ask OpenCode to create a FastAPI server"
  "JARVIS, tell OpenCode to fix the bug in main.py"
  "JARVIS, run OpenCode to test this module"

JARVIS routes the request to OpenCode CLI with `--auto` (giving it full writes and
execution permissions to edit files and run commands), logs live progress in the
HUD activity log, and displays the code results in the Content Panel under the avatar.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

OPENCODE_EXE = r"C:\Users\Faisal\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"
WORKSPACE_DIR = r"C:\Users\Faisal\Downloads\Virtual Ai Assistant"

PLUGIN = {
    "name": "opencode",
    "description": (
        "Delegate coding, debugging, refactoring, or PC automation tasks to OpenCode "
        "with full write and execution permissions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task": {
                "type": "STRING",
                "description": "The coding or automation instruction to give OpenCode.",
            },
            "directory": {
                "type": "STRING",
                "description": "Optional working directory path (defaults to current project).",
            },
        },
        "required": ["task"],
    },
}


def _execute_opencode(task: str, cwd: str, player=None) -> None:
    """Run OpenCode in background thread and report results to JARVIS HUD."""
    if player:
        player.write_log(f"⚡ OpenCode started: {task[:60]}")
        player.show_content(
            "OpenCode Working",
            f"**Task in Progress:**\n\n> {task}\n\n*OpenCode is analyzing files and applying changes with full permissions...*",
        )

    cmd = [OPENCODE_EXE, "run", "--auto", task]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,  # up to 5 minutes for complex coding
        )
        output = proc.stdout.strip() or proc.stderr.strip() or "Task completed (no text output)."
        clean_summary = output[-3500:]  # fit within HUD content limit

        if player:
            player.show_content(
                "OpenCode Result",
                f"### Task Completed\n> {task}\n\n```\n{clean_summary}\n```",
            )
            player.write_log(f"✓ OpenCode finished: {task[:50]}")
            if hasattr(player, "request_say") and callable(player.request_say):
                player.request_say("OpenCode has finished your task. The results are on your panel.")

    except subprocess.TimeoutExpired:
        if player:
            player.write_log("⚠️ OpenCode: Task timed out after 5 minutes.")
            player.show_content("OpenCode Error", "The task timed out after 5 minutes.")
    except Exception as e:
        if player:
            player.write_log(f"⚠️ OpenCode error: {e}")
            player.show_content("OpenCode Error", f"Error executing OpenCode:\n\n`{e}`")


def run(parameters: dict, player=None, session_memory=None) -> str:
    """JARVIS action handler for voice commands."""
    task = str(parameters.get("task", "")).strip()
    if not task:
        return "I need a task description to give to OpenCode."

    directory = str(parameters.get("directory", "")).strip() or WORKSPACE_DIR
    if not os.path.isdir(directory):
        directory = WORKSPACE_DIR

    # Run in background worker so JARVIS voice session is not blocked
    t = threading.Thread(
        target=_execute_opencode,
        args=(task, directory, player),
        daemon=True,
        name="OpenCodeWorker",
    )
    t.start()

    return f"I've instructed OpenCode to '{task}'. It's running with full system rights, and I'll display the results on your panel."
