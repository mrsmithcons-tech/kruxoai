"""
plugins/smart_clipboard_assistant.py — Competitor-Adopted Feature: Smart Clipboard & Code Intelligence.

Adapted from Cursor & Copilot desktop companion tools:
- Inspects, summarizes, or transforms clipboard content.
- Explains copied code, fixes syntax, formats JSON, or generates git commit messages.
- Displays rich breakdown cards on the HUD panel.
- Complies strictly with AGENTS.md rules.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

PLUGIN = {
    "name": "smart_clipboard",
    "description": (
        "Inspect, summarize, or transform the text/code on your clipboard. "
        "Can explain code snippets, generate git commits, fix syntax, or format data."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task": {
                "type": "STRING",
                "description": "What to do with clipboard: 'explain' (analyze code/text), 'summarize' (bullet summary), 'format_json', 'commit_message' (from git diff), or 'read'.",
                "enum": ["explain", "summarize", "format_json", "commit_message", "read"]
            }
        },
        "required": []
    }
}


def _get_clipboard_text() -> str:
    """Retrieve text from the Windows clipboard safely."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        if not user32.OpenClipboard(0):
            return ""

        CF_UNICODETEXT = 13
        h_clip_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_clip_mem:
            user32.CloseClipboard()
            return ""

        p_clip_mem = kernel32.GlobalLock(h_clip_mem)
        text = ctypes.c_wchar_p(p_clip_mem).value or ""
        kernel32.GlobalUnlock(h_clip_mem)
        user32.CloseClipboard()
        return text
    except Exception:
        return ""


def _process_clipboard(task: str, player=None):
    text = _get_clipboard_text().strip()
    if not text:
        if player:
            player.write_log("📋 Clipboard is currently empty.")
            player.show_content("Clipboard Empty", "No text or code was found on the clipboard.")
        return

    if player:
        player.write_log(f"📋 Processing clipboard ({task}, {len(text)} chars)...")

    title = f"📋 Clipboard Intelligence: {task.title()}"
    snippet_preview = text[:400] + ("..." if len(text) > 400 else "")

    if task == "format_json":
        try:
            parsed = json.loads(text)
            formatted = json.dumps(parsed, indent=2)
            content = f"### Formatted JSON\n```json\n{formatted[:2500]}\n```"
        except Exception as e:
            content = f"### JSON Format Error\nText is not valid JSON: `{e}`\n\n```text\n{snippet_preview}\n```"

    elif task == "summarize":
        # Ask core.gemini for quick summary
        try:
            from core import gemini
            res = gemini.text(f"Summarize this text in 3 crisp bullet points:\n\n{text[:4000]}", tier=gemini.FAST)
            content = f"### Summary\n{res}\n\n**Source Preview:**\n> {snippet_preview}"
        except Exception:
            content = f"### Clipboard Text\n> {snippet_preview}"

    elif task == "commit_message":
        try:
            from core import gemini
            res = gemini.text(f"Generate a conventional git commit message (title + short bullet points) for this diff or change:\n\n{text[:4000]}", tier=gemini.FAST)
            content = f"### Suggested Git Commit\n```git\n{res}\n```\n\n**Diff Preview:**\n```diff\n{snippet_preview}\n```"
        except Exception:
            content = f"### Git Diff Content\n```diff\n{snippet_preview}\n```"

    else:
        # Default: explain / read
        try:
            from core import gemini
            res = gemini.text(f"Analyze this clipboard text or code snippet. Identify what it is, its purpose, and any notable points:\n\n{text[:4000]}", tier=gemini.FAST)
            content = f"### Analysis\n{res}\n\n**Clipboard Content:**\n```\n{snippet_preview}\n```"
        except Exception:
            content = f"### Clipboard Content ({len(text)} characters)\n```\n{text[:2000]}\n```"

    if player:
        player.show_content(title, content)
        player.write_log("✓ Clipboard analysis delivered to panel.")


def run(parameters: dict, player=None, session_memory=None) -> str:
    task = str(parameters.get("task", "explain")).strip().lower() or "explain"

    t = threading.Thread(
        target=_process_clipboard,
        args=(task, player),
        daemon=True,
        name="SmartClipboardThread"
    )
    t.start()

    return f"Analyzing your clipboard for {task}. The breakdown is appearing on your panel."
