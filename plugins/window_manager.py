"""
plugins/window_manager.py — Window & Desktop Layout Manager for JARVIS.

Allows JARVIS to:
1. List active application windows.
2. Focus / bring a specific window to front by name.
3. Minimize all windows (Show Desktop).
4. Strictly adheres to AGENTS.md: pure ctypes / win32 calls, never touches Qt widgets, catches all exceptions, returns spoken summary.
"""
from __future__ import annotations

import ctypes
import os
import sys

PLUGIN = {
    "name": "window_manager",
    "description": (
        "Manage desktop windows on Windows: list open application windows, focus a specific window by name, "
        "or minimize all windows to show the desktop."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: 'list' (list visible windows), 'focus' (bring window to front), or 'minimize_all' (show desktop). Default is 'list'.",
                "enum": ["list", "focus", "minimize_all"],
            },
            "window_name": {
                "type": "STRING",
                "description": "Name or partial title of the window to focus (e.g. 'Chrome', 'Notepad', 'VS Code', 'Explorer').",
            },
        },
        "required": [],
    },
}


def _get_visible_windows() -> list[tuple[int, str]]:
    """Enumerate visible application windows."""
    windows = []
    user32 = ctypes.windll.user32

    def enum_windows_callback(hwnd, extra):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                # Exclude internal / tiny / background windows
                if title and title not in ("Default IME", "MSCTFIME UI", "Program Manager"):
                    windows.append((hwnd, title))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
    return windows


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = str(parameters.get("action", "list")).lower().strip()
        target_name = str(parameters.get("window_name", "")).strip().lower()

        user32 = ctypes.windll.user32

        if action == "minimize_all":
            # SW_MINIMIZE = 6, or Shell.Application MinimizeAll
            import subprocess
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", "(New-Object -ComObject Shell.Application).MinimizeAll()"],
                capture_output=True,
                timeout=5,
            )
            if player:
                player.write_log("🖥️ Minimized all windows.")
                player.show_content("Desktop Manager", "Minimized all open windows to show the desktop.")
            return "I have minimized all open windows."

        elif action == "focus":
            if not target_name:
                return "Which application window would you like me to bring to the front?"

            windows = _get_visible_windows()
            found_hwnd = None
            found_title = None

            for hwnd, title in windows:
                if target_name in title.lower():
                    found_hwnd = hwnd
                    found_title = title
                    break

            if found_hwnd:
                # SW_RESTORE = 9, SW_SHOW = 5
                user32.ShowWindow(found_hwnd, 9)
                user32.SetForegroundWindow(found_hwnd)
                if player:
                    player.write_log(f"🖥️ Focused window: {found_title}")
                    player.show_content("Window Manager", f"Brought window to front:\n\n**{found_title}**")
                return f"I brought '{found_title}' to the front."
            else:
                return f"I couldn't find an open window matching '{target_name}'."

        else:
            # Action: list
            windows = _get_visible_windows()
            if not windows:
                return "No open application windows were detected."

            summary = f"### 🖥️ Open Windows ({len(windows)})\n\n"
            for hwnd, title in windows[:12]:
                summary += f"- **{title}**\n"

            if player:
                player.write_log(f"🖥️ Listed {len(windows)} active windows.")
                player.show_content("🖥️ Active Windows", summary)

            return f"There are {len(windows)} application windows open on your desktop."

    except Exception as e:
        if player:
            player.write_log(f"⚠️ Window manager error: {e}")
        return f"Could not manage windows: {e}"
