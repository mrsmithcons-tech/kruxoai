"""
plugins/fault_handler.py — capture the Python traceback when the app dies
from a fatal native signal (e.g. the _ctypes access violation that crashed
the app 4x on 24 Nov 2026, always at _ctypes.pyd +0x12561).

faulthandler is enabled at import (plugin discovery runs at startup), so it
is active for the whole session. It writes to fault.log in the install dir
— under pythonw there is no console, so stderr would be lost. A WER mini
dump (see CrashDumps) still covers fail-fast crashes that faulthandler
cannot catch (e.g. the Qt 0xC0000409 stack overrun).

Actions:
  status — is faulthandler on, and how big is fault.log?
"""
from __future__ import annotations

import faulthandler
from pathlib import Path

PLUGIN = {
    "name": "fault_handler",
    "description": (
        "Crash diagnostics: captures the Python traceback when the app dies "
        "from a fatal native signal. Use this when the user asks why the app "
        "crashed, or to check the last crash report."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["status"], "description": "What to do (default: status)."},
        },
        "required": [],
    },
}

_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)
_FAULT_LOG = _LOGS_DIR / "fault.log"
_fault_file = None
_enabled = False

try:
    _fault_file = open(_FAULT_LOG, "a", encoding="utf-8")
    _fault_file.write("\n--- fault handler armed ---\n")
    _fault_file.flush()
    faulthandler.enable(file=_fault_file)
    _enabled = True
except Exception:
    # Never break startup over diagnostics.
    _enabled = False


def run(action="status", **kwargs):
    try:
        size = _FAULT_LOG.stat().st_size if _FAULT_LOG.exists() else 0
        tail = ""
        if _FAULT_LOG.exists() and size > 0:
            tail = _FAULT_LOG.read_text(encoding="utf-8", errors="ignore")[-500:]
        return (
            "Fault handler: %s. fault.log is %d bytes.\n%s"
            % ("ON" if _enabled else "OFF (could not enable)", size, tail)
        )
    except Exception as e:
        return "Fault handler status check failed: %s" % e
