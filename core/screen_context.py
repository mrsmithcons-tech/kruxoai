"""
core/screen_context.py — Active Window & Screen Context Fusion Engine for JARVIS.

Captures foreground application state, window titles, active process info,
and cropped visual display context to answer queries like:
- "What is this error?"
- "Explain this code"
- "Draft a reply to this"
without requiring the user to manually explain what is on screen.
"""
from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_foreground_app_info() -> Dict[str, Any]:
    """Retrieve title, process name, and geometry of the active top-level user window."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        return {"ok": False, "title": "Desktop / No active window", "process": "explorer.exe", "hwnd": 0}

    # Window title
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value.strip() or "Untitled Window"

    # Process ID & Process Name
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    proc_name = "unknown"
    try:
        import psutil
        if pid.value:
            proc_name = psutil.Process(pid.value).name()
    except Exception:
        pass

    # Window rect
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = max(0, rect.right - rect.left)
    h = max(0, rect.bottom - rect.top)

    return {
        "ok": True,
        "hwnd": hwnd,
        "title": title,
        "process_name": proc_name,
        "pid": pid.value,
        "bounds": {"x": rect.left, "y": rect.top, "width": w, "height": h}
    }


def capture_active_window_screenshot() -> Tuple[Optional[bytes], str]:
    """
    Capture a screenshot cropped specifically to the foreground application window.
    Falls back to primary display if window rect is degenerate.
    """
    try:
        import mss
        info = get_foreground_app_info()
        b = info.get("bounds", {})

        with mss.mss() as sct:
            if b.get("width", 0) > 100 and b.get("height", 0) > 100:
                monitor = {
                    "top": max(0, b["y"]),
                    "left": max(0, b["x"]),
                    "width": b["width"],
                    "height": b["height"]
                }
            else:
                monitor = sct.monitors[1] # Primary screen

            sct_img = sct.grab(monitor)
            # Convert to JPEG bytes via Pillow
            from PIL import Image
            import io
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Resize if overly large for fast LLM transmission
            if img.width > 1280 or img.height > 720:
                img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
                
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return buf.getvalue(), "image/jpeg"
    except Exception as e:
        return None, str(e)


def get_screen_context_summary() -> Dict[str, Any]:
    """Compile a rich text context summary for prompt injection."""
    info = get_foreground_app_info()
    title = info.get("title", "Unknown")
    proc = info.get("process_name", "Unknown")

    context_hint = "General desktop usage"
    if any(k in proc.lower() for k in ["code", "devenv", "pycharm", "cursor"]):
        context_hint = "Coding / Software Development"
    elif any(k in proc.lower() for k in ["chrome", "brave", "edge", "firefox"]):
        context_hint = "Web Research / Browsing"
    elif any(k in proc.lower() for k in ["cmd", "powershell", "terminal", "wt", "bash"]):
        context_hint = "Terminal / Shell Operations"
    elif any(k in proc.lower() for k in ["excel", "calc", "word"]):
        context_hint = "Document / Office Management"

    return {
        "active_window": title,
        "process": proc,
        "category": context_hint,
        "timestamp": time.strftime("%H:%M:%S"),
        "formatted_prompt": f"[Active Window Context: '{title}' ({proc}) — Focus: {context_hint}]"
    }
