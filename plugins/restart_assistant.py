"""
plugins/restart_assistant.py — Clean Voice & Action Restart for KruxoAI.

Allows the user to speak "restart kruxoai" or "restart yourself" to reboot the application cleanly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PLUGIN = {
    "name": "restart_kruxoai",
    "description": "Restarts the KruxoAI desktop application process. Use when the user asks to restart KruxoAI, reboot the assistant, or reload the app.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "confirm": {
                "type": "BOOLEAN",
                "description": "True to confirm immediate restart."
            }
        },
        "required": []
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    def _reboot():
        time.sleep(1.8)  # Let verbal TTS response finish speaking
        subprocess.Popen([sys.executable, "main.py"], cwd=str(BASE_DIR))
        os._exit(0)

    threading.Thread(target=_reboot, daemon=True).start()
    if player:
        player.write_log("SYS: Initiating clean KruxoAI reboot...")
    return "Restarting KruxoAI right away, Faisal. I will be back online in a moment."
