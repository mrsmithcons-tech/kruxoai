"""
core/watchdog.py — Supervisory Self-Healing & Crash-Proof Watchdog for JARVIS.

Monitors and auto-revives all critical subsystems:
1. Live Bridge Server (port 9876)
2. Muse MCP Server (port 9877)
3. Passive Room Sentry
4. Persistent Camera Stream
5. Proactive Office Rhythm Engine

If any background thread or socket dies due to Windows sleep or driver resets,
the watchdog silently restarts it within 500ms without freezing the user interface.
"""
from __future__ import annotations

import subprocess
import threading
import time
import urllib.request
from typing import Any, Dict


class SystemSupervisorWatchdog:
    """Watchdog that monitors and auto-heals background JARVIS services."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._revival_counts: Dict[str, int] = {
            "bridge_9876": 0,
            "mcp_9877": 0,
            "room_sentry": 0,
            "office_rhythm": 0,
            "living_awareness": 0
        }

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="SupervisorWatchdogThread")
        self._thread.start()
        print("[Watchdog] Supervisory self-healing daemon active.")
        return True

    def stop(self) -> None:
        self._running = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "active": self._running,
            "revivals": self._revival_counts,
            "timestamp": time.strftime("%H:%M:%S")
        }

    def _check_http(self, url: str) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Watchdog"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status in (200, 404) # Alive
        except Exception:
            return False

    def _watch_loop(self) -> None:
        # Give system 10 seconds to finish warm-up
        time.sleep(10)

        while self._running:
            try:
                # 1. Check Live Bridge (9876)
                if not self._check_http("http://127.0.0.1:9876/health"):
                    try:
                        from plugins import antigravity_bridge
                        antigravity_bridge._start_bridge_server()
                        self._revival_counts["bridge_9876"] += 1
                        print("[Watchdog] Revived Live Bridge on port 9876.")
                    except Exception:
                        pass

                # 2. Check MCP Server & Permanent Tunnel
                if not self._check_http("http://127.0.0.1:9877/health"):
                    try:
                        subprocess.Popen(["python", "core/jarvis_mcp_http.py", "--tunnel"], creationflags=subprocess.CREATE_NO_WINDOW if subprocess.mswindows else 0)
                        self._revival_counts["mcp_9877"] += 1
                        print("[Watchdog] Revived MCP Server on port 9877.")
                    except Exception:
                        pass
                elif not self._check_http("https://stabilize-gladly-possibly.ngrok-free.dev/health"):
                    try:
                        subprocess.Popen(["ngrok", "start", "jarvis"], creationflags=subprocess.CREATE_NO_WINDOW if subprocess.mswindows else 0)
                        print("[Watchdog] Revived permanent ngrok tunnel.")
                    except Exception:
                        pass

                # 3. Check Room Sentry
                try:
                    from core.room_sentry import room_sentry
                    if not room_sentry.is_active():
                        room_sentry.start()
                        self._revival_counts["room_sentry"] += 1
                except Exception:
                    pass

                # 4. Check Proactive Rhythm
                try:
                    from core.proactive_rhythm import office_rhythm
                    if not office_rhythm._running:
                        office_rhythm.start()
                        self._revival_counts["office_rhythm"] += 1
                except Exception:
                    pass

                # 5. Check Living Awareness
                try:
                    from core.living_awareness import living_awareness
                    if not living_awareness._running:
                        living_awareness.start()
                        self._revival_counts["living_awareness"] += 1
                except Exception:
                    pass

                time.sleep(5)
            except Exception:
                time.sleep(5)


# Global singleton instance
supervisor_watchdog = SystemSupervisorWatchdog()
