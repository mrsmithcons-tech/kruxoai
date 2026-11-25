"""
plugins/downloads_file_organizer.py — Intelligent Downloads & Desktop File Organizer for JARVIS.

Allows JARVIS to:
1. Scan the user's Downloads folder.
2. Categorize files by type: Documents, Images, Installers, Archives, Audio & Video, Code.
3. Offer a safe `preview` mode (dry-run) or `organize` mode (creates folders and safely moves files).
4. Strictly adheres to AGENTS.md: never touches Qt widgets, never deletes files, catches all exceptions, returns spoken summary.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PLUGIN = {
    "name": "downloads_organizer",
    "description": (
        "Organize files in your Downloads folder into neat categories (Documents, Images, Installers, "
        "Archives, Media, Code). Can run a dry-run 'preview' or perform the actual safe 'organize' moves."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to take: 'preview' (dry-run report without moving) or 'organize' (perform file moves). Default is 'preview'.",
                "enum": ["preview", "organize"],
            },
            "custom_folder": {
                "type": "STRING",
                "description": "Optional custom folder path to organize (defaults to the Windows Downloads folder).",
            },
        },
        "required": [],
    },
}

EXTENSIONS = {
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv", ".epub"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico"],
    "Installers": [".exe", ".msi", ".bat", ".cmd"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
    "Media": [".mp4", ".mkv", ".mp3", ".wav", ".avi", ".mov", ".flac"],
    "Code & Data": [".py", ".json", ".js", ".ts", ".html", ".css", ".sql", ".xml", ".yaml", ".yml"],
}


def _get_target_dir(custom_path: str | None) -> Path:
    if custom_path and os.path.isdir(custom_path):
        return Path(custom_path)
    # Default: user Downloads
    home = Path.home()
    dl = home / "Downloads"
    if dl.exists():
        return dl
    return home


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = str(parameters.get("action", "preview")).lower().strip()
        custom_folder = parameters.get("custom_folder")
        target_dir = _get_target_dir(custom_folder)

        if not target_dir.exists():
            return f"The target directory {target_dir} was not found."

        # Scan top-level files (skip directories)
        files = [f for f in target_dir.iterdir() if f.is_file() and not f.name.startswith(".")]

        categorized: dict[str, list[Path]] = {cat: [] for cat in EXTENSIONS}
        uncategorized: list[Path] = []

        for f in files:
            ext = f.suffix.lower()
            matched = False
            for cat, ext_list in EXTENSIONS.items():
                if ext in ext_list:
                    categorized[cat].append(f)
                    matched = True
                    break
            if not matched:
                uncategorized.append(f)

        total_match = sum(len(items) for items in categorized.values())

        if action == "organize":
            moved_count = 0
            for cat, cat_files in categorized.items():
                if not cat_files:
                    continue
                dest_dir = target_dir / cat
                dest_dir.mkdir(exist_ok=True)
                for src_file in cat_files:
                    target_file = dest_dir / src_file.name
                    # Avoid overwriting existing files
                    if target_file.exists():
                        target_file = dest_dir / f"{src_file.stem}_{int(src_file.stat().st_mtime)}{src_file.suffix}"
                    try:
                        shutil.move(str(src_file), str(target_file))
                        moved_count += 1
                    except Exception as me:
                        if player:
                            player.write_log(f"⚠️ Move skipped for {src_file.name}: {me}")

            summary_text = (
                f"### 📁 Downloads Organizer — Completed\n\n"
                f"**Target Directory:** `{target_dir}`\n"
                f"**Files Organized:** {moved_count} files moved into category folders.\n\n"
            )
            for cat, cat_files in categorized.items():
                if cat_files:
                    summary_text += f"- **{cat}**: {len(cat_files)} files\n"
            if uncategorized:
                summary_text += f"- **Uncategorized (Left in place)**: {len(uncategorized)} files\n"

            if player:
                player.write_log(f"📁 Downloads organized: {moved_count} files sorted into categories.")
                player.show_content("📁 Downloads Organizer", summary_text)

            return f"I have organized your Downloads folder. {moved_count} files were sorted into category folders."

        else:
            # Preview mode
            summary_text = (
                f"### 📁 Downloads Organizer — Preview (Dry-Run)\n\n"
                f"**Target Directory:** `{target_dir}`\n"
                f"**Files Found:** {len(files)} total files ({total_match} can be sorted into categories).\n\n"
            )
            for cat, cat_files in categorized.items():
                if cat_files:
                    sample = ", ".join(f.name for f in cat_files[:3])
                    extra = f" (+{len(cat_files)-3} more)" if len(cat_files) > 3 else ""
                    summary_text += f"• **{cat}** ({len(cat_files)}): `{sample}{extra}`\n"

            if uncategorized:
                summary_text += f"• **Uncategorized** ({len(uncategorized)} files will stay in place)\n"

            summary_text += (
                f"\n*To execute these moves, say: 'Organize my downloads folder for real'.*"
            )

            if player:
                player.write_log(f"📁 Downloads preview: {total_match} files ready to be organized.")
                player.show_content("📁 Downloads Organizer Preview", summary_text)

            return f"I scanned your Downloads folder. There are {total_match} files ready to be organized into neat category folders. Would you like me to organize them?"

    except Exception as e:
        if player:
            player.write_log(f"⚠️ Downloads organizer error: {e}")
        return f"Could not inspect the downloads folder: {e}"
