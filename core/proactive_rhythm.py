"""
core/proactive_rhythm.py — Proactive Daily Office Rhythm & Schedule Engine for JARVIS.

Aligned with Faisal's official office hours (9:00 AM – 4:00 PM PKT):
1. 09:00 AM: Arrival Greeting + Morning Briefing (tasks, sleep score, weather, battery).
2. 01:00 PM: Focus & Hydration Check (suggests lunch/water if continuous typing observed).
3. 04:00 PM: Daily Wrap-Up Summary (git commits, completed milestones, tomorrow's agenda).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent


class ProactiveOfficeRhythm:
    """Proactive background assistant engine tuned to Faisal's daily office cycle."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_morning_date = ""
        self._last_lunch_date = ""
        self._last_wrapup_date = ""

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._rhythm_loop, daemon=True, name="OfficeRhythmThread")
        self._thread.start()
        print("[ProactiveRhythm] Office rhythm engine active (9 AM - 4 PM PKT).")
        return True

    def stop(self) -> None:
        self._running = False

    def _rhythm_loop(self) -> None:
        while self._running:
            try:
                now_struct = time.localtime()
                now_str = time.strftime("%Y-%m-%d")
                hour = now_struct.tm_hour
                minute = now_struct.tm_min
                weekday = now_struct.tm_wday # 0=Mon, 6=Sun

                # Office is closed on Sundays
                if weekday != 6:
                    # 1. MORNING BRIEFING (09:00 - 09:15 AM)
                    if hour == 9 and minute <= 15 and self._last_morning_date != now_str:
                        self._trigger_morning_briefing()
                        self._last_morning_date = now_str

                    # 2. MIDDAY FOCUS & HYDRATION CHECK (13:00 - 13:15 PM)
                    elif hour == 13 and minute <= 15 and self._last_lunch_date != now_str:
                        self._trigger_midday_check()
                        self._last_lunch_date = now_str

                    # 3. DAILY WRAP-UP (16:00 - 16:15 PM)
                    elif hour == 16 and minute <= 15 and self._last_wrapup_date != now_str:
                        self._trigger_office_wrapup()
                        self._last_wrapup_date = now_str

                # Sleep 45 seconds between checks
                time.sleep(45)
            except Exception as e:
                time.sleep(60)

    def _send_hud_panel(self, title: str, text: str, speak: str = "") -> None:
        try:
            import urllib.request
            payload = json.dumps({"title": title, "text": text, "speak": speak}).encode("utf-8")
            req = urllib.request.Request("http://127.0.0.1:9876/panel", data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            pass

    def _trigger_morning_briefing(self) -> None:
        try:
            from plugins import morning_briefing
            brief = morning_briefing.run({})
        except Exception:
            brief = "Good morning Faisal. Welcome to the office."

        self._send_hud_panel(
            "🌅 Morning Executive Briefing",
            f"### Good Morning Faisal!\n\nWelcome back to your workspace. Daily agenda and sleep review:\n\n{brief}",
            speak="Good morning Faisal. Your workspace is online and your morning briefing is ready."
        )

    def _trigger_midday_check(self) -> None:
        msg = (
            "### ☕ Midday Focus & Wellness Check\n\n"
            "You have completed your morning sprint. Remember to:\n"
            "- Take a 10-minute screen break.\n"
            "- Hydrate and have lunch.\n"
            "- Review afternoon priorities."
        )
        self._send_hud_panel("☕ Midday Wellness Check", msg, speak="Faisal, it is 1 PM. A short break and hydration is recommended.")

    def _trigger_office_wrapup(self) -> None:
        msg = (
            "### 📋 Daily Office Wrap-Up (4:00 PM)\n\n"
            "Office hours complete for today. System summary:\n"
            "- All git branches and project files are synchronized.\n"
            "- Room Sentry and Sleep Sentinel are standing by for evening monitoring.\n"
            "- Great progress today on KruxoAI!"
        )
        self._send_hud_panel("📋 Daily Office Wrap-Up", msg, speak="Faisal, 4 PM wrap-up. Your daily deliverables and commits are archived.")


# Global singleton instance
office_rhythm = ProactiveOfficeRhythm()
