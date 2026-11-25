"""
plugins/quick_note_vault.py — Local Markdown Note & Knowledge Vault for JARVIS.

Allows JARVIS to:
1. Capture quick thoughts, voice memos, ideas, and meeting notes into `memory/notes/`.
2. Search past notes by keyword or list recent entries.
3. Completely local storage in standard Markdown (.md) format.
4. Strictly adheres to AGENTS.md: never touches Qt widgets, catches all exceptions, returns spoken summary.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "memory" / "notes"

PLUGIN = {
    "name": "quick_note_vault",
    "description": (
        "Capture, search, and manage quick personal notes, ideas, reminders, and knowledge snippets. "
        "Stores everything locally in markdown files. Supports 'add', 'search', and 'list'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: 'add' (save a new note), 'search' (find notes matching a keyword), or 'list' (show recent notes). Defaults to 'add'.",
                "enum": ["add", "search", "list"],
            },
            "title": {
                "type": "STRING",
                "description": "Short title or topic for the note (e.g. 'Project Ideas', 'Meeting with Client').",
            },
            "content": {
                "type": "STRING",
                "description": "The text, note content, thought, or memo to save.",
            },
            "query": {
                "type": "STRING",
                "description": "Keyword to search for when action is 'search'.",
            },
        },
        "required": [],
    },
}


def _ensure_notes_dir():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        _ensure_notes_dir()
        action = str(parameters.get("action", "add")).lower().strip()
        title = str(parameters.get("title", "")).strip()
        content = str(parameters.get("content", "")).strip()
        query = str(parameters.get("query", "")).strip()

        # If user just spoke a thought with content but didn't specify action
        if not action or (content and action not in ("search", "list")):
            action = "add"

        if action == "add":
            if not content and not title:
                return "What would you like me to note down?"

            note_title = title if title else (content[:30] + "...")
            clean_filename = re.sub(r"[^a-zA-Z0-9_\- ]", "", note_title).strip().replace(" ", "_")
            if not clean_filename:
                clean_filename = "quick_note"
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            filename = f"{timestamp}_{clean_filename[:32]}.md"
            note_path = NOTES_DIR / filename

            body = (
                f"# {note_title}\n\n"
                f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
                f"**Captured By:** JARVIS  \n\n"
                f"---\n\n"
                f"{content}\n"
            )
            note_path.write_text(body, encoding="utf-8")

            if player:
                player.write_log(f"📝 Note saved: {note_title}")
                player.show_content(
                    f"📝 Note Saved: {note_title}",
                    f"### {note_title}\n\n"
                    f"*{datetime.now().strftime('%A, %b %d %Y at %I:%M %p')}*\n\n"
                    f"---\n\n"
                    f"{content}\n\n"
                    f"📁 *Saved to: `memory/notes/{filename}`*",
                )

            return f"I've saved your note titled '{note_title}'."

        elif action == "search":
            if not query:
                return "What keyword would you like to search for in your notes?"

            matches = []
            q_lower = query.lower()
            for note_file in sorted(NOTES_DIR.glob("*.md"), reverse=True):
                try:
                    text = note_file.read_text(encoding="utf-8", errors="replace")
                    if q_lower in text.lower() or q_lower in note_file.name.lower():
                        first_line = text.splitlines()[0] if text.splitlines() else note_file.name
                        matches.append((note_file.name, first_line.replace("#", "").strip(), text[:200]))
                except Exception:
                    pass

            if not matches:
                if player:
                    player.show_content("Search Notes", f"No notes found matching `{query}`.")
                return f"I couldn't find any notes matching '{query}'."

            summary = f"### 🔍 Note Search Results for `{query}`\n\nFound {len(matches)} matching note(s):\n\n"
            for fname, ftitle, preview in matches[:8]:
                summary += f"- **{ftitle}** (`{fname}`)\n  > {preview.strip()}...\n\n"

            if player:
                player.write_log(f"🔍 Found {len(matches)} notes matching '{query}'")
                player.show_content("🔍 Note Search Results", summary)

            return f"I found {len(matches)} note(s) matching '{query}'."

        else:
            # Action: list
            notes = sorted(NOTES_DIR.glob("*.md"), reverse=True)[:10]
            if not notes:
                if player:
                    player.show_content("Personal Notes Vault", "Your notes vault is currently empty. Tell me: 'Take a note: ...' to add one.")
                return "Your personal notes vault is empty right now."

            summary = f"### 📝 Personal Notes Vault\n\nRecent Notes ({len(notes)}):\n\n"
            for n in notes:
                try:
                    lines = n.read_text(encoding="utf-8", errors="replace").splitlines()
                    title_line = lines[0].replace("#", "").strip() if lines else n.stem
                    mtime = datetime.fromtimestamp(n.stat().st_mtime).strftime("%b %d, %H:%M")
                    summary += f"- **{title_line}** *({mtime})* — `{n.name}`\n"
                except Exception:
                    pass

            if player:
                player.write_log("📝 Displayed recent notes vault.")
                player.show_content("📝 Personal Notes Vault", summary)

            return f"Here are your {len(notes)} most recent notes."

    except Exception as e:
        if player:
            player.write_log(f"⚠️ Quick notes error: {e}")
        return f"Could not manage notes: {e}"
