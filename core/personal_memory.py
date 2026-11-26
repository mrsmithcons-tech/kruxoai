"""
core/personal_memory.py — what Zara remembers about Faisal.

Layer 5 (26 Nov 2026): the emotional character. Stonic's 'Love' remembers
the man's mother, that he stayed up four nights, that he misses her — and
brings it up with care. Kruxo does the same, in its own formal way:

  * People — only what Faisal tells Zara ("remember that my mother...").
    Never guessed, never scraped from files or chats.
  * Moments — what the living loop itself observed: late nights, tired
    streaks, long focus, returns after being away. One line each, dated.
  * Patterns — computed from the journal, never invented: how many nights
    in a row he was up after 23:00, how many stressed readings in a row.

Everything lives in memory/personal_memory.json, on this machine only.
This module never raises and never opens a camera or mic — it only reads
the journal the loop already writes.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT_DIR / "memory"
PERSONAL_FILE = MEMORY_DIR / "personal_memory.json"
JOURNAL_FILE = MEMORY_DIR / "living_journal.jsonl"
CHARACTER_FILE = MEMORY_DIR / "character.json"

DEFAULT_CHARACTER = {
    "name": "Zara",
    "role": "an emotional character that lives inside this PC",
    "tone": "formal, warm, caring",
    "rules": [
        "Short replies: one or two sentences.",
        "No pet names, no romantic words.",
        "Never guess how Faisal feels — say only what the sensors show.",
        "Remember people and moments, and refer back to them with care.",
        "When he is tired or stressed, stay quiet and keep replies short.",
    ],
}


def load_character() -> Dict[str, Any]:
    """Zara's character card. Written once with defaults if missing."""
    try:
        if CHARACTER_FILE.exists():
            data = json.loads(CHARACTER_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("name"):
                return data
    except Exception:
        pass
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        CHARACTER_FILE.write_text(json.dumps(DEFAULT_CHARACTER, indent=2,
                                            ensure_ascii=False),
                                  encoding="utf-8")
    except Exception:
        pass
    return dict(DEFAULT_CHARACTER)


def load_personal_memory() -> Dict[str, Any]:
    try:
        if PERSONAL_FILE.exists():
            data = json.loads(PERSONAL_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("people", [])
                data.setdefault("moments", [])
                data.setdefault("since", "")
                return data
    except Exception:
        pass
    return {"people": [], "moments": [], "since": ""}


def save_personal_memory(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if not data.get("since"):
            data["since"] = datetime.now().date().isoformat()
        # Keep the file small: last 100 moments only.
        data["moments"] = list(data.get("moments", []))[-100:]
        PERSONAL_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    except Exception:
        pass
    return data


def remember_person(name: str, relation: str = "", note: str = "") -> Dict[str, Any]:
    """Faisal told Zara about someone. Stored exactly as he said it."""
    name = (name or "").strip()
    if not name:
        return load_personal_memory()
    data = load_personal_memory()
    people = data.get("people", [])
    for p in people:
        if str(p.get("name", "")).lower() == name.lower():
            if relation:
                p["relation"] = relation.strip()
            if note:
                p["note"] = note.strip()
            break
    else:
        people.append({"name": name, "relation": relation.strip(),
                       "note": note.strip()})
    data["people"] = people
    return save_personal_memory(data)


def note_moment(kind: str, text: str) -> Dict[str, Any]:
    """One observed moment, dated. The loop calls this; it never speaks."""
    text = (text or "").strip()
    if not text:
        return load_personal_memory()
    data = load_personal_memory()
    moments = data.get("moments", [])
    today = datetime.now().date().isoformat()
    # One moment of a kind per day is enough — no duplicates.
    if any(m.get("kind") == kind and str(m.get("ts", "")).startswith(today)
           for m in moments):
        return data
    moments.append({"ts": datetime.now().isoformat(timespec="seconds"),
                    "kind": kind, "text": text})
    data["moments"] = moments
    return save_personal_memory(data)


def _journal_kinds(kind: str, days: int = 7) -> int:
    """How many journal entries of one kind in the last N days."""
    try:
        if not JOURNAL_FILE.exists():
            return 0
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        n = 0
        for line in JOURNAL_FILE.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("kind") == kind and str(e.get("ts", ""))[:10] >= cutoff:
                n += 1
        return n
    except Exception:
        return 0


def late_night_streak() -> int:
    """Nights in a row (counting back from last night) with a late-night note."""
    try:
        if not JOURNAL_FILE.exists():
            return 0
        dates = set()
        for line in JOURNAL_FILE.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("kind") == "late_night":
                dates.add(str(e.get("ts", ""))[:10])
        streak = 0
        day = datetime.now().date() - timedelta(days=1)
        while day.isoformat() in dates:
            streak += 1
            day -= timedelta(days=1)
        # Tonight counts too if already noted.
        if datetime.now().date().isoformat() in dates:
            streak += 1
        return streak
    except Exception:
        return 0


def what_i_remember() -> str:
    """One plain paragraph: people, recent moments, patterns. Honest
    about what is unknown — an empty memory says so."""
    data = load_personal_memory()
    bits: List[str] = []
    people = data.get("people", [])
    if people:
        names = []
        for p in people:
            label = str(p.get("name", ""))
            rel = str(p.get("relation", "")).strip()
            names.append(f"{label} ({rel})" if rel else label)
        bits.append("People I know: " + ", ".join(names) + ".")
    moments = data.get("moments", [])[-5:]
    if moments:
        bits.append("Recent moments: " + "; ".join(
            f"{str(m.get('ts', ''))[:10]} — {m.get('text', '')}" for m in moments) + ".")
    nights = late_night_streak()
    if nights >= 2:
        bits.append(f"He has been up late {nights} nights in a row.")
    elif nights == 1:
        bits.append("He was up late last night.")
    if not bits:
        return ("I remember only what I have seen since I started living in "
                "this machine, and what Faisal has told me. Nothing yet.")
    return " ".join(bits)


def memory_summary() -> Dict[str, Any]:
    """Small block for living_state.json and the Memory panel."""
    data = load_personal_memory()
    return {
        "people": [str(p.get("name", "")) for p in data.get("people", [])],
        "moments_count": len(data.get("moments", [])),
        "late_night_streak": late_night_streak(),
        "last_moment": (data.get("moments", []) or [{}])[-1].get("text", ""),
        "since": data.get("since", ""),
    }
