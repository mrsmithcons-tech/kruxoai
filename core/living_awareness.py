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

Layer 3 — Awareness upgrade (26 Nov 2026, Faisal: "like Stonic"):
  * Senses: core/environment.py — time of day, outside weather in
    Tandlianwala (Open-Meteo, cached), CPU temperature when the machine
    exposes it (honestly None when it does not).
  * Toggle: memory/living_config.json — awareness_enabled / proactive_enabled,
    read every tick, so "awareness off" takes effect without a restart.
    Quiet hours 9 PM – 6 AM: the loop never speaks then (sleep sentinel
    owns the night). Awareness OFF also silences all proactive speech.
  * Proactive brain: every ~5 minutes, when something actually changed
    (mood, app, hour, battery, extreme weather), the model judges from the
    fused state whether to speak — one short formal sentence, no pet names,
    never when stressed unless urgent. A failed judge call just means the
    small rules carry on; the loop never depends on the model.

Drop this file into core/ as core/living_awareness.py. It starts itself
through the watchdog (core/watchdog.py, next to the office_rhythm check),
which revives it if it ever stops — same pattern as room_sentry and
office_rhythm. It speaks through the local HUD panel endpoint
(http://127.0.0.1:9876/panel), exactly like core/proactive_rhythm.py, so it
needs no player object to be heard.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT_DIR / "memory"
STATE_FILE = MEMORY_DIR / "living_state.json"
JOURNAL_FILE = MEMORY_DIR / "living_journal.jsonl"
CONFIG_FILE = MEMORY_DIR / "living_config.json"
SENTRY_LOG = MEMORY_DIR / "room_sentry_events.json"

TICK_SECONDS = 30
SPEAK_COOLDOWN_SECONDS = 15 * 60      # at most one proactive line per 15 min
LONG_FOCUS_MINUTES = 120               # same app non-stop -> suggest a break
AWAY_MINUTES = 30                      # away this long -> "welcome back" on return
LOW_BATTERY_PERCENT = 20
QUIET_START_HOUR = 21                  # 9 PM – 6 AM: never speak (sleep sentinel owns the night)
QUIET_END_HOUR = 6
JUDGE_EVERY_TICKS = 10                 # proactive brain: every ~5 minutes
BANNED_WORDS = ("jaan", "darling", "sweetheart", "baby", "honey")  # Zara: formal, no pet names

DEFAULT_CONFIG = {
    "awareness_enabled": True,         # the master toggle (Stonic "Awareness")
    "proactive_enabled": True,         # proactive speech + brain; state still updates when off
    "quiet_hours_start": QUIET_START_HOUR,
    "quiet_hours_end": QUIET_END_HOUR,
}

_config_cache = {"mtime": 0.0, "data": dict(DEFAULT_CONFIG)}


def load_living_config() -> Dict[str, Any]:
    """Awareness toggle + quiet hours, re-read when the file changes.

    A corrupt or missing file falls back to defaults — the loop never dies
    over a config file. The plugin writes it; the loop reads it every tick.
    """
    try:
        mtime = CONFIG_FILE.stat().st_mtime
        if mtime == _config_cache["mtime"]:
            return dict(_config_cache["data"])
        data = dict(DEFAULT_CONFIG)
        data.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")) or {})
        _config_cache["mtime"] = mtime
        _config_cache["data"] = data
        return dict(data)
    except Exception:
        return dict(_config_cache["data"])


def save_living_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge one toggle change into living_config.json (voice/plugin path)."""
    data = load_living_config()
    data.update(patch)
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                               encoding="utf-8")
        _config_cache["mtime"] = CONFIG_FILE.stat().st_mtime
        _config_cache["data"] = dict(data)
    except Exception:
        pass
    return dict(data)


def _in_quiet_hours(cfg: Optional[Dict[str, Any]] = None, hour: Optional[int] = None) -> bool:
    """True between quiet-hours start and end (default 9 PM – 6 AM)."""
    cfg = cfg or DEFAULT_CONFIG
    start = int(cfg.get("quiet_hours_start", QUIET_START_HOUR))
    end = int(cfg.get("quiet_hours_end", QUIET_END_HOUR))
    h = datetime.now().hour if hour is None else hour
    return h >= start or h < end


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
        self._environment: Dict[str, Any] = {}
        self._last_rest_suggestion_date = ""
        self._last_judge_sig: Any = None
        self._last_brain_decision: Dict[str, Any] = {}

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

    def _refresh_environment(self) -> None:
        """Time of day + outside weather + CPU temp, every 6th tick (~3 min).
        Weather is cached 30 min inside the sensor; a failure keeps the last
        good reading and marks the source, never a guess."""
        try:
            from core.environment import sense_environment
            self._environment = sense_environment()
        except Exception as e:
            self._log(f"[LivingAwareness] environment refresh failed: {e}")

    def _tick(self) -> None:
        now = time.time()
        self._tick_count += 1
        cfg = load_living_config()
        snapshot = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "app": _foreground_app(),
            "system": _system(),
            "room": _last_sentry_event(),
            "awareness": {
                "enabled": bool(cfg.get("awareness_enabled", True)),
                "proactive": bool(cfg.get("proactive_enabled", True)),
                "quiet_hours": (f"{cfg.get('quiet_hours_start', QUIET_START_HOUR):02d}:00-"
                                f"{cfg.get('quiet_hours_end', QUIET_END_HOUR):02d}:00"),
                "in_quiet_hours": _in_quiet_hours(cfg),
            },
        }
        if self._tick_count == 1 or self._tick_count % 6 == 0:
            self._refresh_environment()
        snapshot["environment"] = self._environment
        app = snapshot["app"].get("app") or "unknown"
        if app != self._current_app:
            self._journal("app_change", {"from": self._current_app, "to": app,
                                         "title": snapshot["app"].get("title", "")})
            self._current_app = app
            self._app_since[app] = now
        minutes_on_app = (now - self._app_since.get(app, now)) / 60.0
        snapshot["minutes_on_current_app"] = round(minutes_on_app, 1)
        if self._tick_count == 1 or self._tick_count % JUDGE_EVERY_TICKS == 0:
            self._refresh_understanding(snapshot)
            self._judge_should_speak(snapshot, cfg, now)
        snapshot["understanding"] = self._understanding
        snapshot["last_brain_decision"] = self._last_brain_decision

        with self._lock:
            self._state = snapshot
        self._save_state(snapshot)
        self._evaluate_rules(snapshot, now, minutes_on_app)

    # -- proactive brain -----------------------------------------------------
    def _judge_signature(self, snap: Dict[str, Any]) -> tuple:
        """What the brain watches for change: mood, app, hour, battery, weather.

        The model is only asked when this signature changes — a quiet machine
        costs no model calls at all.
        """
        u = snap.get("understanding") or {}
        env = snap.get("environment") or {}
        outside = (env.get("outside") or {})
        temp = outside.get("temp_c")
        battery = (snap.get("system") or {}).get("battery") or {}
        return (
            u.get("mood", "unknown"),
            (snap.get("app") or {}).get("app", "unknown"),
            datetime.now().hour,
            bool(battery.get("percent") is not None
                 and battery["percent"] <= LOW_BATTERY_PERCENT
                 and not battery.get("plugged")),
            bool(temp is not None and (temp >= 40 or temp <= 5)),
        )

    def _judge_should_speak(self, snap: Dict[str, Any], cfg: Dict[str, Any], now: float) -> None:
        """The proactive brain: ask the model, from the fused state, whether
        interrupting Faisal is worth it. Guarded end to end — any failure
        just means the small rules carry on, and the loop never waits on it."""
        if not cfg.get("awareness_enabled", True):
            return
        if not cfg.get("proactive_enabled", True):
            return
        if _in_quiet_hours(cfg):
            return
        if now - self._last_spoke_at < SPEAK_COOLDOWN_SECONDS:
            return
        sig = self._judge_signature(snap)
        if sig == self._last_judge_sig:
            return  # nothing changed — no model call
        self._last_judge_sig = sig
        try:
            from core.tasks.brain import ask as brain_ask
        except Exception as e:
            self._log(f"[LivingAwareness] brain unavailable: {e}")
            return
        u = snap.get("understanding") or {}
        env = snap.get("environment") or {}
        outside = env.get("outside") or {}
        summary = (
            f"Time: {datetime.now():%H:%M} ({env.get('time_of_day', 'unknown')}). "
            f"App: {(snap.get('app') or {}).get('app', 'unknown')} "
            f"for {snap.get('minutes_on_current_app', 0)} minutes. "
            f"Mood: {u.get('mood', 'unknown')} (confidence {u.get('confidence', 'low')}, "
            f"energy {u.get('energy', 'unknown')}, intent {u.get('intent', 'unknown')}). "
            f"Outside {outside.get('place') or 'unknown'}: "
            f"{outside.get('temp_c')}C, {outside.get('conditions') or 'unknown'}. "
            f"CPU {snap.get('system', {}).get('cpu_percent')}%, "
            f"memory {snap.get('system', {}).get('memory_percent')}%. "
            f"Battery: {(snap.get('system', {}).get('battery') or {}).get('percent')}%."
        )
        system = (
            "You are the decision brain of Kruxo AI, a formal desktop assistant. "
            "Decide whether to interrupt Faisal with ONE short spoken line. "
            "Reply with JSON only: {\"speak\": true/false, \"text\": \"...\", \"reason\": \"...\"}. "
            "Speak ONLY when something genuinely deserves interrupting him: a real change "
            "in mood or energy, extreme weather, low battery, a natural moment (morning "
            "start, long focus, evening wrap-up). Default to silence — a living AI does "
            "not nag. The line must be one formal sentence, max 25 words, no pet names, "
            "no romantic words, no emojis. Never speak when mood is stressed unless "
            "there is a genuine safety or battery problem."
        )
        try:
            result = brain_ask(system, [{"role": "user", "text": summary}], None)
            text = (result or {}).get("text", "") or ""
            text = text.strip()
            if text.startswith("```"):
                text = text.strip("`").strip()
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            decision = json.loads(text)
            speak = bool(decision.get("speak"))
            line = str(decision.get("text") or "").strip()
            reason = str(decision.get("reason") or "").strip()
        except Exception as e:
            self._log(f"[LivingAwareness] brain judge failed (rules carry on): {e}")
            return
        self._last_brain_decision = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "speak": speak, "reason": reason,
            "text": line if speak else "",
        }
        if not speak or not line or len(line) > 200:
            return
        if re.search(r"\b(" + "|".join(BANNED_WORDS) + r")\b", line.lower()):
            self._log("[LivingAwareness] brain line dropped (pet name).")
            return
        self._act(line, security=False)
        self._journal("proactive_brain", {"reason": reason, "text": line})

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
        if not security:
            cfg = load_living_config()
            if not cfg.get("awareness_enabled", True):
                return  # Awareness toggle OFF: the loop stays silent
            if _in_quiet_hours(cfg):
                return  # 9 PM – 6 AM: sleep sentinel owns the night
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
