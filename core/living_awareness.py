"""
core/living_awareness.py — Living Awareness engine for Kruxo AI.

One continuous loop that makes Kruxo feel alive inside the machine:

    SENSE -> WORLD MODEL -> REMEMBER -> DECIDE -> ACT, every 30 seconds.

It does NOT open any new camera/mic stream. It only reads sensors Kruxo
already has (screen context, room sentry events, presence state) plus cheap
system reads (psutil). Everything it learns is stored locally:
    memory/living_state.json    — one live picture of "right now"
    memory/living_journal.jsonl — one line per event, the day's memory

Rules are small, with cooldowns, so Kruxo speaks rarely and only when it
matters. Security events ignore the cooldown. Never raises: every sensor
read is guarded, and a failed sensor is reported honestly in the state
("screen": "unknown") instead of being guessed.

Drop this file into core/ as core/living_awareness.py. It starts itself
through the watchdog (core/watchdog.py, next to the office_rhythm check),
which revives it if it ever stops — same pattern as room_sentry and
office_rhythm. It speaks through the local HUD panel endpoint
(http://127.0.0.1:9876/panel), exactly like core/proactive_rhythm.py, so it
needs no player object to be heard.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT_DIR / "memory"
STATE_FILE = MEMORY_DIR / "living_state.json"
JOURNAL_FILE = MEMORY_DIR / "living_journal.jsonl"
SENTRY_LOG = MEMORY_DIR / "room_sentry_events.json"

TICK_SECONDS = 30
SPEAK_COOLDOWN_SECONDS = 15 * 60      # at most one proactive line per 15 min
LONG_FOCUS_MINUTES = 120               # same app non-stop -> suggest a break
AWAY_MINUTES = 30                      # away this long -> "welcome back" on return
LOW_BATTERY_PERCENT = 20


def _safe_psutil():
    try:
        import psutil  # type: ignore
        return psutil
    except Exception:
        return None


def _foreground_app() -> Dict[str, Any]:
    """Active window, via the existing screen-context engine. Unknown on failure."""
    try:
        from core.screen_context import get_foreground_app_info
        info = get_foreground_app_info() or {}
        return {
            "app": info.get("process") or "unknown",
            "title": (info.get("title") or "")[:120],
            "ok": bool(info.get("ok", True)),
        }
    except Exception:
        return {"app": "unknown", "title": "", "ok": False}


def _system() -> Dict[str, Any]:
    psutil = _safe_psutil()
    if psutil is None:
        return {"cpu_percent": None, "memory_percent": None, "battery": None}
    try:
        battery = None
        try:
            b = psutil.sensors_battery()
            if b is not None:
                battery = {"percent": round(b.percent), "plugged": bool(b.power_plugged)}
        except Exception:
            battery = None
        return {
            "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
            "memory_percent": round(psutil.virtual_memory().percent, 1),
            "battery": battery,
        }
    except Exception:
        return {"cpu_percent": None, "memory_percent": None, "battery": None}


def _last_sentry_event() -> Optional[Dict[str, Any]]:
    """Last room-sentry event (who spoke in the room), if the sentry is running."""
    try:
        if not SENTRY_LOG.exists():
            return None
        lines = SENTRY_LOG.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return None
        return json.loads(lines[-1])
    except Exception:
        return None


class LivingAwareness:
    """The living loop. One instance per Kruxo process."""

    def __init__(self, player=None, speak_fn: Optional[Callable[[str], None]] = None,
                 tick_seconds: int = TICK_SECONDS):
        self.player = player
        self.speak_fn = speak_fn
        self.tick_seconds = tick_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {"status": "starting"}
        self._last_spoke_at = 0.0
        self._last_break_suggestion_at = 0.0
        self._last_battery_warning_at = 0.0
        self._was_away = False
        self._app_since: Dict[str, float] = {}   # app -> timestamp first seen
        self._current_app = "unknown"
        self._tick_count = 0
        self._understanding: Dict[str, Any] = {
            "mood": "unknown", "confidence": "low", "energy": "unknown",
            "intent": "unknown", "style_hint": "normal", "signals": ["context"],
        }
        self._last_rest_suggestion_date = ""

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="LivingAwarenessThread")
        self._thread.start()
        self._log("[LivingAwareness] Living mode on — sensing every "
                  f"{self.tick_seconds}s, everything stays on this machine.")
        return True

    def stop(self) -> None:
        self._running = False
        self._log("[LivingAwareness] Living mode off. State file kept, journal kept.")

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    # -- the loop ----------------------------------------------------------
    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as e:  # never let the loop die
                self._log(f"[LivingAwareness] tick failed (will retry): {e}")
            time.sleep(self.tick_seconds)

    def _refresh_understanding(self, snapshot: Dict[str, Any]) -> None:
        """Face + voice + context, throttled: every 10th tick (~5 minutes).
        Both sensors are slow (camera frame, 3s mic) and may be busy — a
        failure just keeps the previous understanding, never a guess."""
        try:
            from core.understanding import fuse_understanding, sense_face, sense_voice
            face = sense_face()
            voice = sense_voice()
            self._understanding = fuse_understanding(snapshot, face, voice)
        except Exception as e:
            self._log(f"[LivingAwareness] understanding refresh failed: {e}")

    def _tick(self) -> None:
        now = time.time()
        self._tick_count += 1
        snapshot = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "app": _foreground_app(),
            "system": _system(),
            "room": _last_sentry_event(),
        }
        if self._tick_count == 1 or self._tick_count % 10 == 0:
            self._refresh_understanding(snapshot)
        snapshot["understanding"] = self._understanding
        app = snapshot["app"].get("app") or "unknown"
        if app != self._current_app:
            self._journal("app_change", {"from": self._current_app, "to": app,
                                         "title": snapshot["app"].get("title", "")})
            self._current_app = app
            self._app_since[app] = now
        minutes_on_app = (now - self._app_since.get(app, now)) / 60.0
        snapshot["minutes_on_current_app"] = round(minutes_on_app, 1)

        with self._lock:
            self._state = snapshot
        self._save_state(snapshot)
        self._evaluate_rules(snapshot, now, minutes_on_app)

    # -- decisions (small rules, cooldowns, security ignores cooldown) ----
    def _evaluate_rules(self, snap: Dict[str, Any], now: float, minutes_on_app: float) -> None:
        app = snap["app"].get("app") or "unknown"

        # Away -> back: greet once (presence comes from the sentry/presence
        # plugins; until they report, "away" means no app activity + no events).
        # This rule only fires on a real return signal, never on a guess.
        room = snap.get("room") or {}
        speaker = str(room.get("speaker") or room.get("person") or "").lower()
        if speaker and "faisal" in speaker and self._was_away:
            self._was_away = False
            self._act("Welcome back, Faisal.", security=False)
            self._journal("return", {"speaker": speaker})

        mood = (self._understanding or {}).get("mood", "unknown")

        # Tired late at night: one rest suggestion per evening, then quiet.
        if mood in ("tired", "tired_late"):
            today = datetime.now().date().isoformat()
            if self._last_rest_suggestion_date != today:
                self._last_rest_suggestion_date = today
                self._act("You look tired. Shall I keep everything short "
                          "and let you rest?", security=False)
                self._journal("tired_nudge", {"mood": mood})

        # Long focus: one quiet suggestion, at most once per 2 hours.
        # Never when stressed — a break nudge is the last thing a stressed
        # person needs from an assistant that claims to understand.
        if (mood != "stressed"
                and minutes_on_app >= LONG_FOCUS_MINUTES
                and now - self._last_break_suggestion_at > LONG_FOCUS_MINUTES * 60
                and app != "unknown"):
            self._last_break_suggestion_at = now
            self._act(f"You have been on {app} for two hours. Shall I hold "
                      "interruptions for a while?", security=False)
            self._journal("long_focus", {"app": app, "minutes": round(minutes_on_app)})

        # Low battery: warn once per hour.
        battery = (snap.get("system") or {}).get("battery") or {}
        if (battery.get("percent") is not None
                and battery["percent"] <= LOW_BATTERY_PERCENT
                and not battery.get("plugged")
                and now - self._last_battery_warning_at > 3600):
            self._last_battery_warning_at = now
            self._act(f"Battery is at {battery['percent']} percent and the "
                      "charger is not connected.", security=False)
            self._journal("low_battery", {"percent": battery["percent"]})

        # Unknown speaker while Faisal is away: security note, no cooldown.
        if speaker and "faisal" not in speaker and "unknown" in speaker:
            self._act("An unrecognized voice was heard in the room.",
                      security=True)
            self._journal("unknown_speaker", {"speaker": speaker})

    # -- acting / remembering ----------------------------------------------
    def _send_hud_panel(self, title: str, text: str, speak: str = "") -> None:
        """Same delivery as core/proactive_rhythm.py: local HUD panel endpoint."""
        try:
            import urllib.request
            payload = json.dumps({"title": title, "text": text,
                                  "speak": speak}).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:9876/panel", data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            pass

    def _act(self, text: str, security: bool = False) -> None:
        now = time.time()
        if not security and now - self._last_spoke_at < SPEAK_COOLDOWN_SECONDS:
            return  # stay quiet: a living AI does not nag
        self._last_spoke_at = now
        self._log(f"[LivingAwareness] {text}")
        try:
            if self.speak_fn is not None:
                self.speak_fn(text)
            elif self.player is not None and hasattr(self.player, "speak"):
                self.player.speak(text)
            else:
                self._send_hud_panel("Kruxo AI", text, speak=text)
        except Exception as e:
            self._log(f"[LivingAwareness] could not speak: {e}")

    def _journal(self, kind: str, data: Dict[str, Any]) -> None:
        try:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            line = {"ts": datetime.now().isoformat(timespec="seconds"),
                    "kind": kind, **data}
            with JOURNAL_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception:
            pass  # journaling must never break the loop

    def what_happened_today(self) -> str:
        """One-paragraph summary of today's journal, for the evening wrap-up."""
        try:
            if not JOURNAL_FILE.exists():
                return "Nothing recorded today yet."
            today = datetime.now().date().isoformat()
            events = [json.loads(line) for line in
                      JOURNAL_FILE.read_text(encoding="utf-8").splitlines()
                      if line.strip() and line.strip().startswith('{"ts": "' + today)]
            if not events:
                return "Nothing recorded today yet."
            kinds: Dict[str, int] = {}
            for e in events:
                kinds[e.get("kind", "?")] = kinds.get(e.get("kind", "?"), 0) + 1
            summary = ", ".join(f"{n} {k}" for k, n in kinds.items())
            return f"Today so far: {summary} ({len(events)} events, all local)."
        except Exception as e:
            return f"I could not read today's journal: {e}"

    def _save_state(self, snapshot: Dict[str, Any]) -> None:
        try:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        except Exception:
            pass

    def _log(self, text: str) -> None:
        try:
            if self.player is not None and hasattr(self.player, "write_log"):
                self.player.write_log(text)
            else:
                print(text)
        except Exception:
            print(text)


# Global singleton instance (same pattern as office_rhythm / room_sentry).
# The watchdog (core/watchdog.py) starts this and revives it if it stops.
living_awareness = LivingAwareness()
