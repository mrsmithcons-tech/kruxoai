"""
plugins/living_awareness.py — "What do you see right now?" for Kruxo AI.

Drop-in plugin (see plugins/_template.py). It is the voice of the Living
Awareness engine in core/living_awareness.py: one live picture of the
machine, one journal of the day, and a switch to turn living mode on/off.

Actions:
  status              — is living mode on, and what is the live state?
  what_do_you_see     — describe right now: app, system, room (honest "unknown"
                        when a sensor is off — never a guess)
  what_happened_today — summary of today's journal
  start / stop        — turn the living loop on / off ("go quiet")
  awareness_on/off    — the Awareness toggle (Stonic-style): on = Kruxo senses
                        and may speak; off = silent, state still updates
  awareness_status    — toggle state + quiet hours + last brain decision
  awareness_card      — show the "mind" panel on the HUD: toggle, senses,
                        mood, last brain decision (the visible Awareness panel)

Model calls, if ever needed, go through core.gemini (template rule).
This plugin never raises: it returns a spoken error string instead.
"""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = {
    "name": "living_awareness",
    "description": (
        "Kruxo AI's living awareness: what it sees right now on this machine "
        "(foreground app, system load, battery, who is in the room, outside "
        "weather, time of day), what happened today, and the Awareness toggle. "
        "Use this when the user asks what you see, what is happening, what "
        "happened today, how you feel, or to turn awareness on/off or go quiet. "
        "Do NOT use it for general chat or web questions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["status", "what_do_you_see", "what_happened_today",
                         "how_am_i_feeling", "what_do_you_understand",
                         "awareness_on", "awareness_off", "awareness_status",
                         "awareness_card", "start", "stop"],
                "description": "What to do (default: what_do_you_see).",
            },
        },
        "required": [],
    },
}

# The watchdog keeps one shared engine alive; the plugin talks to that same
# instance so "what do you see" and the background loop never disagree.
def _engine(player=None):
    try:
        from core.living_awareness import living_awareness
        if not living_awareness._running:
            living_awareness.start()
        return living_awareness, ""
    except Exception as e:
        return None, f"Living awareness engine could not start: {e}"


def _describe(state: dict) -> str:
    app = (state.get("app") or {})
    app_name = app.get("app") or "unknown"
    title = app.get("title") or ""
    system = state.get("system") or {}
    battery = system.get("battery") or {}
    parts = []
    if app_name == "unknown" or not app.get("ok", True):
        parts.append("I cannot see the screen right now — the screen sensor is off or unavailable.")
    else:
        where = f" on {app_name}" + (f" — {title}" if title else "")
        parts.append(f"Right now you are{where}.")
        minutes = state.get("minutes_on_current_app")
        if minutes:
            parts.append(f"You have been there for about {int(minutes)} minutes.")
    if system.get("cpu_percent") is not None:
        parts.append(f"CPU {system['cpu_percent']} percent, memory {system['memory_percent']} percent.")
    if battery.get("percent") is not None:
        parts.append(f"Battery {battery['percent']} percent"
                     + (" and charging." if battery.get("plugged") else " and not charging."))
    room = state.get("room") or {}
    speaker = room.get("speaker") or room.get("person")
    if speaker:
        parts.append(f"Last voice in the room: {speaker}.")
    else:
        parts.append("The room sensor has not reported anyone.")
    env = state.get("environment") or {}
    if env.get("time_of_day"):
        parts.append(f"It is {env['time_of_day']}.")
    outside = env.get("outside") or {}
    if outside.get("temp_c") is not None:
        parts.append(f"Outside {outside.get('place', '')}: {outside['temp_c']} degrees, "
                     f"{outside.get('conditions') or ''}.")
    if env.get("cpu_temp_c") is not None:
        parts.append(f"CPU temperature {env['cpu_temp_c']} degrees.")
    u = state.get("understanding") or {}
    if u.get("mood") and u["mood"] != "unknown":
        parts.append(f"Understood mood: {u['mood']} (confidence {u.get('confidence', 'low')}, "
                     f"energy {u.get('energy', 'unknown')}, doing {u.get('intent', 'unknown')}).")
    if state.get("avatar_mood") and state["avatar_mood"] != "unknown":
        parts.append(f"My face is showing {state['avatar_mood']} right now.")
    return " ".join(parts)


def _awareness_card(state: dict) -> str:
    """The visible 'mind' panel (Stonic-style): toggle, senses, mood, brain."""
    aw = state.get("awareness") or {}
    env = state.get("environment") or {}
    outside = env.get("outside") or {}
    u = state.get("understanding") or {}
    brain = state.get("last_brain_decision") or {}
    lines = [
        "### 🧠 Awareness",
        "",
        f"- **Awareness:** {'ON' if aw.get('enabled', True) else 'OFF'}"
        f" · Proactive brain: {'ON' if aw.get('proactive', True) else 'OFF'}",
        f"- **Quiet hours:** {aw.get('quiet_hours', '21:00-06:00')}"
        f" (now: {'quiet' if aw.get('in_quiet_hours') else 'awake'})",
        f"- **Time:** {env.get('time_of_day', 'unknown')}"
        + (f" · Outside {outside.get('place', '')}: {outside.get('temp_c')}°C, "
           f"{outside.get('conditions') or 'unknown'}" if outside.get("temp_c") is not None
           else " · Outside weather: unknown"),
        f"- **CPU temp:** {env.get('cpu_temp_c')}°C" if env.get("cpu_temp_c") is not None
        else "- **CPU temp:** not exposed by this machine",
        f"- **Mood:** {u.get('mood', 'unknown')} (confidence {u.get('confidence', 'low')}, "
        f"energy {u.get('energy', 'unknown')})",
        f"- **Last brain decision:** {brain.get('at', 'none yet')} — "
        f"{'spoke' if brain.get('speak') else 'stayed quiet'}"
        + (f" — {brain.get('reason', '')}" if brain.get("reason") else ""),
    ]
    return "\n".join(lines)


def _feeling_summary(state: dict) -> str:
    u = state.get("understanding") or {}
    mood = u.get("mood", "unknown")
    if mood == "unknown":
        return ("I cannot tell how you are feeling right now — the face and "
                "voice sensors did not report. The camera or mic may be busy "
                "or off. I will not guess.")
    face = u.get("face") or {}
    voice = u.get("voice") or {}
    bits = [f"You seem {mood} (confidence {u.get('confidence', 'low')})."]
    if face.get("reading") not in (None, "unknown"):
        bits.append(f"Face: {face['reading']} (eye ratio {face.get('ear')}, "
                    f"mouth ratio {face.get('mar')}).")
    if voice.get("emotional_state") not in (None, "unknown"):
        bits.append(f"Voice: {voice['emotional_state']}, "
                    f"stress {voice.get('stress_level_pct')} percent.")
    bits.append(f"Energy {u.get('energy', 'unknown')}, you are doing "
                f"{u.get('intent', 'unknown')}.")
    if u.get("suggestion"):
        bits.append(u["suggestion"])
    bits.append("Face readings are geometry only — not a diagnosis.")
    return " ".join(bits)


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = (parameters or {}).get("action") or "what_do_you_see"
    try:
        engine, err = _engine(player)
        if engine is None:
            return f"Living awareness is not available. {err}"
        if action == "start":
            engine.start()
            return "Living mode is on. I am watching the machine now — quietly, and everything stays on this laptop."
        if action == "stop":
            engine.stop()
            return "Going quiet now. Living mode is off. Everything I learned stays saved locally."
        if action in ("awareness_on", "awareness_off", "awareness_status", "awareness_card"):
            from core.living_awareness import load_living_config, save_living_config
            if action == "awareness_on":
                save_living_config({"awareness_enabled": True, "proactive_enabled": True})
                engine._send_hud_panel("🧠 Awareness ON",
                                       "Awareness is ON. I can sense and speak again.",
                                       speak="Awareness is on.")
                return "Awareness is on. I can sense the machine and speak when something matters."
            if action == "awareness_off":
                save_living_config({"awareness_enabled": False})
                engine._send_hud_panel("🧠 Awareness OFF",
                                       "Awareness is OFF. I will stay silent. State still updates.",
                                       speak="")
                return "Awareness is off. I will stay silent. My senses still update, but I will not speak."
            try:
                engine._tick()
            except Exception:
                pass
            state = engine.get_state()
            if action == "awareness_status":
                aw = state.get("awareness") or {}
                brain = state.get("last_brain_decision") or {}
                return ("Awareness is " + ("ON" if aw.get("enabled", True) else "OFF")
                        + f", proactive brain {'ON' if aw.get('proactive', True) else 'OFF'}"
                        + f", quiet hours {aw.get('quiet_hours', '21:00-06:00')}"
                        + (" (quiet now)." if aw.get("in_quiet_hours") else " (awake now).")
                        + (f" Last brain decision: {brain.get('at', 'none yet')} — "
                           f"{'spoke' if brain.get('speak') else 'stayed quiet'}."
                           if brain else " Brain has not decided anything yet."))
            engine._send_hud_panel("🧠 Awareness", _awareness_card(state), speak="")
            return "Here is my awareness panel — toggle, senses, mood, and my last decision."
        if action == "status":
            state = engine.get_state()
            return ("Living mode is on." if getattr(engine, "_running", False)
                    else "Living mode is off.") + " " + _describe(state)
        if action == "what_happened_today":
            return engine.what_happened_today()
        if action in ("how_am_i_feeling", "what_do_you_understand"):
            # Fresh sense on demand: face + voice + context, fused now.
            try:
                from core.understanding import (fuse_understanding,
                                                sense_face, sense_voice)
                engine._tick()
                state = engine.get_state()
                state["understanding"] = fuse_understanding(
                    state, sense_face(), sense_voice())
            except Exception:
                pass
            return _feeling_summary(engine.get_state())
        # what_do_you_see (default): fresh snapshot, not a stale file
        try:
            engine._tick()
        except Exception:
            pass
        return _describe(engine.get_state())
    except Exception as e:
        return f"Living awareness failed: {e}"


# Auto-start the living loop when Kruxo discovers this plugin at startup.
# Plugin modules are fully executed at discovery (core/plugin_loader uses
# exec_module), and a failure here only skips this plugin — it never breaks
# discovery. The watchdog wiring in core/watchdog.py stays as a second layer:
# it revives the loop if it ever stops. Guarded twice on purpose.
try:
    from core.living_awareness import living_awareness as _LA
    if not _LA._running:
        _LA.start()
except Exception:
    pass
