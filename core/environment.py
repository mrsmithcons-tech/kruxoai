"""
core/environment.py — the world OUTSIDE the machine, for Living Awareness.

What Kruxo can sense about its surroundings (Stonic-style awareness):
  * time of day (from the local clock — always available)
  * outside weather in Tandlianwala (Open-Meteo, free, no key — reuses the
    existing core.cloud.weather_today; cached 30 min so the loop never
    hammers the network)
  * CPU temperature (psutil on Windows almost always reports nothing, and
    WMI thermal zones are usually absent too — so this is honestly None
    when the machine does not expose it, never a made-up number)

Everything is guarded: a failed sensor returns None with a "source" note,
never a guess. Nothing here opens a camera or microphone.

Install as core/environment.py. Imported lazily by the living loop, so a
failure here can never break the loop.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Optional

# Faisal's home town — the weather that matters to him.
CITY = "Tandlianwala"
WEATHER_CACHE_SECONDS = 30 * 60

_weather_cache: Dict[str, Any] = {"at": 0.0, "data": None}


def time_of_day(hour: Optional[int] = None) -> str:
    """Plain label for the hour — the sense Stonic demos as 'time of day'."""
    h = datetime.now().hour if hour is None else hour
    if 5 <= h < 9:
        return "early morning"
    if 9 <= h < 12:
        return "morning"
    if 12 <= h < 16:
        return "afternoon"
    if 16 <= h < 19:
        return "evening"
    if 19 <= h < 21:
        return "night"
    return "late night"


def _outside_weather() -> Optional[Dict[str, Any]]:
    """Outside temperature + conditions, cached 30 min. None on any failure."""
    now = time.time()
    if now - _weather_cache["at"] < WEATHER_CACHE_SECONDS and _weather_cache["data"] is not None:
        return _weather_cache["data"]
    try:
        from core.cloud import weather_today
        w = weather_today(CITY) or {}
        data = {
            "place": w.get("place") or CITY,
            "temp_c": w.get("now_c"),
            "conditions": w.get("now") or w.get("today") or None,
            "min_c": w.get("min_c"),
            "max_c": w.get("max_c"),
            "rain_chance_pct": w.get("rain_chance_pct"),
            "source": "open-meteo",
        }
        _weather_cache["at"] = now
        _weather_cache["data"] = data
        return data
    except Exception:
        return None


def _cpu_temp_c() -> Optional[float]:
    """CPU temperature in Celsius, or None when the machine hides it.

    psutil.sensors_temperatures() is empty on most Windows laptops; WMI
    thermal zones are usually absent too. Both are tried; neither is faked.
    """
    try:
        import psutil  # type: ignore
        temps = psutil.sensors_temperatures() or {}
        for entries in temps.values():
            for entry in entries or []:
                current = getattr(entry, "current", None)
                if current is not None:
                    return round(float(current), 1)
    except Exception:
        pass
    try:
        import wmi  # type: ignore
        c = wmi.WMI(namespace="root\\wmi")
        for zone in c.MSAcpi_ThermalZoneTemperature():
            kelvin = getattr(zone, "CurrentTemperature", None)
            if kelvin:
                return round(float(kelvin) / 10.0 - 273.15, 1)
    except Exception:
        pass
    return None


def sense_environment() -> Dict[str, Any]:
    """One honest picture of the surroundings. Unknowns stay unknown."""
    weather = _outside_weather()
    cpu_temp = _cpu_temp_c()
    return {
        "time_of_day": time_of_day(),
        "hour": datetime.now().hour,
        "outside": weather,                      # None when offline/unknown
        "cpu_temp_c": cpu_temp,                  # None when the machine hides it
        "cpu_temp_source": ("sensor" if cpu_temp is not None
                            else "not exposed by this machine"),
    }
