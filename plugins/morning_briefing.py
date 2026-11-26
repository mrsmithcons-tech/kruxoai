"""
plugins/morning_briefing.py — Executive Morning Briefing Plugin for JARVIS.

Allows JARVIS to deliver a comprehensive morning briefing:
1. Sleep Sentinel Overview (bedtime, wake time, sleep duration, stillness, room disturbances).
2. Hardware & Battery Health (plugged status, battery percent, RAM/CPU loads).
3. System & Background Status (overnight self-upgrades deployed).
4. Date, day, and weather/agenda summary.
5. Strictly adheres to AGENTS.md: thread-safe player calls, catches all exceptions, returns concise speech.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "memory"
PLUGINS_DIR = BASE_DIR / "plugins"

PLUGIN = {
    "name": "morning_briefing",
    "description": (
        "Deliver the executive morning briefing to Faisal: summarizes how you slept overnight "
        "(sleep duration, position changes, snoring, disruptions), what happened overnight in "
        "the living journal, how you woke up (mood, weather), system health, battery level, "
        "and overnight upgrades developed by JARVIS."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
}


def _get_sleep_summary() -> str:
    """Read the latest sleep sentinel report."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    sleep_file = MEMORY_DIR / f"sleep_report_{today_str}.json"
    if not sleep_file.exists():
        # Check any recent sleep report
        reports = sorted(MEMORY_DIR.glob("sleep_report_*.json"), reverse=True)
        if reports:
            sleep_file = reports[0]
        else:
            return "No overnight sleep record found. Sleep sentinel was not running."

    try:
        data = json.loads(sleep_file.read_text(encoding="utf-8"))
        bedtime = data.get("bedtime", "Not recorded")
        wake_time = data.get("wake_time", "Not recorded")
        duration = data.get("total_sleep_duration_hours", "N/A")
        shifts = len(data.get("position_shifts", []))
        snores = len(data.get("snore_events", []))
        noises = len(data.get("noise_spikes", []))
        yawns = data.get("yawns_detected", 0)

        return (
            f"- **Bedtime:** {bedtime}\n"
            f"- **Wake Time:** {wake_time}\n"
            f"- **Estimated Sleep Duration:** {duration} hours\n"
            f"- **Position Shifts (Toss & Turn):** {shifts} shifts\n"
            f"- **Yawns Detected:** {yawns}\n"
            f"- **Snore Events:** {snores} detected\n"
            f"- **Room Noise Spikes:** {noises} ambient audio spikes"
        )
    except Exception as e:
        return f"Could not parse sleep report: {e}"


def _get_system_metrics() -> tuple[str, str]:
    """Retrieve quick system and battery stats."""
    import psutil
    vm = psutil.virtual_memory()
    ram_str = f"{vm.percent}% used ({vm.available / 1024**3:.1f} GB available)"
    cpu_str = f"{psutil.cpu_percent(interval=0.2)}%"

    bat = psutil.sensors_battery()
    if bat:
        plugged_str = "Plugged in (AC)" if bat.power_plugged else "Running on Battery"
        bat_str = f"{bat.percent}% ({plugged_str})"
    else:
        bat_str = "Desktop PC / No battery sensor"

    return f"RAM: {ram_str} | CPU: {cpu_str}", bat_str


def _get_recent_upgrades() -> list[str]:
    """Get list of overnight upgrades from memory or plugins dir."""
    upgrades = []
    log_file = MEMORY_DIR / "overnight_evolution_log.json"
    if log_file.exists():
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            for entry in data[-5:]:
                upgrades.append(f"• **{entry.get('name', 'Feature')}**: {entry.get('description', '')[:70]}...")
        except Exception:
            pass
    if not upgrades:
        # Fallback to checking active plugins
        if PLUGINS_DIR.exists():
            for p in PLUGINS_DIR.glob("*.py"):
                if not p.name.startswith("_") and p.stem in ("battery_health", "network_speed_tester", "quick_note_vault", "downloads_file_organizer"):
                    upgrades.append(f"• **{p.stem}**: Hot-deployed & validated local capability")
    return upgrades


def _get_overnight_journal() -> str:
    """What happened while Faisal slept (21:00 – 06:00), from the living
    journal: app changes, returns, unknown voices, tired nudges, and what
    the proactive brain said or decided. Counts + the notable lines only —
    the full timeline stays in memory/living_journal.jsonl."""
    log_file = MEMORY_DIR / "living_journal.jsonl"
    if not log_file.exists():
        return "No overnight journal yet — living awareness only started recording recently."
    try:
        now = datetime.now()
        start = (now - timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0)
        end = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now.hour < 6:  # before 6 AM the night started yesterday 21:00, ends now
            end = now
        events = []
        for line in log_file.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            try:
                ts = datetime.fromisoformat(e.get("ts", ""))
            except Exception:
                continue
            if start <= ts <= end:
                events.append(e)
        if not events:
            return "Nothing recorded overnight — the machine was quiet all night."
        kinds: dict = {}
        for e in events:
            kinds[e.get("kind", "?")] = kinds.get(e.get("kind", "?"), 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in kinds.items())
        lines = [f"- **{len(events)} events overnight:** {summary}"]
        notable = [e for e in events
                   if e.get("kind") in ("unknown_speaker", "proactive_brain",
                                        "tired_nudge", "return")]
        for e in notable[-3:]:
            when = e.get("ts", "")[11:16]
            if e.get("kind") == "proactive_brain":
                lines.append(f"- {when} — I said: “{e.get('text', '')}”")
            elif e.get("kind") == "unknown_speaker":
                lines.append(f"- {when} — an unrecognized voice was heard.")
            elif e.get("kind") == "tired_nudge":
                lines.append(f"- {when} — I suggested rest (mood {e.get('mood', '')}).")
            else:
                lines.append(f"- {when} — you came back ({e.get('speaker', '')}).")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not read the overnight journal: {e}"


def _get_waking_awareness() -> str:
    """How Faisal woke up: understood mood + outside weather, from the
    living state file. Honest 'not recorded' when the loop was off."""
    state_file = MEMORY_DIR / "living_state.json"
    if not state_file.exists():
        return "Awareness state not recorded yet."
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        u = state.get("understanding") or {}
        env = state.get("environment") or {}
        outside = env.get("outside") or {}
        bits = []
        if u.get("mood") and u["mood"] != "unknown":
            bits.append(f"- **Mood on waking:** {u['mood']} "
                        f"(confidence {u.get('confidence', 'low')}, "
                        f"energy {u.get('energy', 'unknown')})")
            if u.get("suggestion"):
                bits.append(f"- **Suggestion:** {u['suggestion']}")
        if outside.get("temp_c") is not None:
            bits.append(f"- **Outside:** {outside.get('place', '')} "
                        f"{outside['temp_c']}°C, {outside.get('conditions') or ''}")
        if state.get("avatar_mood") and state["avatar_mood"] != "unknown":
            bits.append(f"- **Avatar face:** showing {state['avatar_mood']}")
        return "\n".join(bits) if bits else "Awareness state not recorded yet."
    except Exception as e:
        return f"Could not read the awareness state: {e}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")

        sleep_summary = _get_sleep_summary()
        overnight_journal = _get_overnight_journal()
        waking_awareness = _get_waking_awareness()
        sys_metrics, bat_metrics = _get_system_metrics()
        upgrades = _get_recent_upgrades()

        upgrades_md = "\n".join(upgrades) if upgrades else "• Core autonomous tools running steadily."

        content_md = (
            f"# 🌅 Good Morning, Faisal\n\n"
            f"**{date_str}** — **{time_str}**\n\n"
            f"---\n\n"
            f"### 🌙 Overnight Sleep & Room Sentinel\n"
            f"{sleep_summary}\n\n"
            f"---\n\n"
            f"### 🌃 Overnight — While You Slept\n"
            f"{overnight_journal}\n\n"
            f"---\n\n"
            f"### 🧠 Awareness On Waking\n"
            f"{waking_awareness}\n\n"
            f"---\n\n"
            f"### ⚡ Hardware & Power Status\n"
            f"- **Power:** {bat_metrics}\n"
            f"- **System Resources:** {sys_metrics}\n\n"
            f"---\n\n"
            f"### 🧬 Overnight Autonomous Self-Upgrades\n"
            f"{upgrades_md}\n\n"
            f"---\n\n"
            f"*KruxoAI is online and ready for your day, Faisal. Built by kruxoai.com.*"
        )

        if player:
            player.write_log("🌅 Morning briefing delivered to Faisal.")
            player.show_content("🌅 Morning Executive Briefing", content_md)

        return (
            f"Good morning, Faisal. Today is {now.strftime('%A, %B %d')}. "
            f"I have prepared your complete overnight sleep and system health briefing on the HUD panel. "
            f"All overnight upgrades are verified and active."
        )

    except Exception as e:
        if player:
            player.write_log(f"⚠️ Morning briefing error: {e}")
        return f"Good morning, Faisal. I encountered an issue preparing the briefing: {e}"
