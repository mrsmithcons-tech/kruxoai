"""
plugins/terminal_command_executor.py — Open Interpreter Terminal & Code Execution Plugin for JARVIS.

Gives JARVIS the flagship capability of Open Interpreter:
- Execute PowerShell, CMD, and Python scripts directly on Windows.
- Full output capture (stdout, stderr, exit code).
- Non-blocking execution with live HUD Content Panel streaming.
- Follows AGENTS.md rules: never touches Qt widgets directly, catches all exceptions, returns short spoken summary.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

PLUGIN = {
    "name": "terminal_executor",
    "description": (
        "Execute PowerShell, CMD, or Python commands and scripts directly on this computer "
        "(like Open Interpreter). Runs commands, controls programs, installs packages, or runs scripts, "
        "streaming the full output to the HUD panel."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "description": "The command or script to execute in PowerShell or CMD.",
            },
            "shell": {
                "type": "STRING",
                "description": "The shell environment: 'powershell' (default), 'cmd', or 'python'.",
            },
            "working_dir": {
                "type": "STRING",
                "description": "Optional working directory path where the command should run.",
            },
            "timeout_seconds": {
                "type": "INTEGER",
                "description": "Maximum seconds to wait before terminating (default 45).",
            },
        },
        "required": ["command"],
    },
}


def _run_terminal_worker(command: str, shell_type: str, working_dir: str | None, timeout: int, player=None):
    if player:
        player.write_log(f"💻 Executing terminal command ({shell_type}): {command[:60]}...")
        player.show_content(
            f"💻 Terminal ({shell_type})",
            f"**Running:**\n```sh\n{command}\n```\n\n*Executing in background...*",
        )

    cwd = working_dir if (working_dir and os.path.isdir(working_dir)) else None

    try:
        if shell_type.lower() == "cmd":
            cmd_args = ["cmd.exe", "/c", command]
        elif shell_type.lower() == "python":
            cmd_args = [sys.executable, "-c", command]
        else:
            # Default: PowerShell
            cmd_args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]

        proc = subprocess.run(
            cmd_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        exit_code = proc.returncode

        output_preview = stdout if stdout else (stderr if stderr else "(no output)")
        if len(output_preview) > 3000:
            output_preview = output_preview[:3000] + "\n... [truncated]"

        if player:
            status_symbol = "✓" if exit_code == 0 else "⚠️"
            player.write_log(f"{status_symbol} Terminal finished (exit code {exit_code})")
            player.show_content(
                f"💻 Terminal Output (Code {exit_code})",
                f"**Command:** `{command}`\n\n"
                f"**Status:** {'Success' if exit_code == 0 else 'Failed (Exit code: ' + str(exit_code) + ')'}\n\n"
                f"```text\n{output_preview}\n```",
            )

    except subprocess.TimeoutExpired:
        if player:
            player.write_log(f"⚠️ Terminal timed out after {timeout}s: {command[:40]}")
            player.show_content("Terminal Timeout", f"Command timed out after {timeout} seconds:\n`{command}`")
    except Exception as e:
        if player:
            player.write_log(f"⚠️ Terminal error: {e}")
            player.show_content("Terminal Error", str(e))


def run(parameters: dict, player=None, session_memory=None) -> str:
    command = str(parameters.get("command", "")).strip()
    if not command:
        return "No command was provided to execute."

    shell_type = str(parameters.get("shell", "powershell")).strip() or "powershell"
    working_dir = parameters.get("working_dir")
    timeout = int(parameters.get("timeout_seconds", 45))

    t = threading.Thread(
        target=_run_terminal_worker,
        args=(command, shell_type, working_dir, timeout, player),
        daemon=True,
        name="TerminalExecutorWorker",
    )
    t.start()

    return f"Running `{command[:40]}` in {shell_type}. The output will appear on your panel."
