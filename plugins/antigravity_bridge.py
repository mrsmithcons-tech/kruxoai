"""
plugins/antigravity_bridge.py — Live Bridge between Antigravity and JARVIS HUD.

Provides a bidirectional bridge:
1. ANTIGRAVITY -> JARVIS:
   Runs a local daemon HTTP server on 127.0.0.1:9876. Antigravity (or any local
   script) can POST to /panel to display messages, answers, and markdown directly
   on JARVIS's HUD content panel and activity log.
2. JARVIS -> ANTIGRAVITY:
   Exposes the `ask_antigravity` tool so you can say "Ask Antigravity to ..."
   and JARVIS logs the question to the inbox queue for Antigravity to read.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

BRIDGE_PORT = 9876
_INBOX_FILE = Path(__file__).parent.parent / "config" / "antigravity_inbox.json"
_LAST_PLAYER = None

PLUGIN = {
    "name": "ask_antigravity",
    "description": (
        "Send a question, request, or message to Antigravity (the coding assistant), "
        "or record a note for Antigravity."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "message": {
                "type": "STRING",
                "description": "The message or question to send to Antigravity.",
            }
        },
        "required": ["message"],
    },
}


def _get_player():
    """Retrieve the active JarvisUI instance safely."""
    global _LAST_PLAYER
    if _LAST_PLAYER is not None:
        return _LAST_PLAYER
    try:
        from ui import JarvisUI
        return JarvisUI.get_active()
    except Exception:
        return None


def _save_to_inbox(sender: str, message: str) -> None:
    """Store incoming messages in the local inbox queue."""
    try:
        items = []
        if _INBOX_FILE.exists():
            with open(_INBOX_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
        items.append({
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sender": sender,
            "message": message,
        })
        # Keep last 50 messages
        items = items[-50:]
        with open(_INBOX_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except Exception as e:
        print(f"[AntigravityBridge] Inbox save error: {e}")


def _read_inbox() -> list:
    """Read stored inbox messages."""
    try:
        if _INBOX_FILE.exists():
            with open(_INBOX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


# ── Local HTTP Bridge Server ──────────────────────────────────────────────────

class _BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep console output quiet
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            player = _get_player()
            self._send_json({
                "status": "online",
                "bridge": "Antigravity-KruxoAI",
                "domain": "kruxoai.com",
                "has_player": player is not None,
            })
        elif self.path == "/inbox":
            self._send_json({"inbox": _read_inbox()})
        else:
            self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        if self.path == "/call_mode":
            player = _get_player()
            if player and hasattr(player, "toggle_call_mode"):
                player.toggle_call_mode()
                self._send_json({"ok": True, "call_mode_toggled": True})
            else:
                self._send_json({"error": "Player unavailable"}, status=503)
            return

        if self.path in ("/panel", "/message", "/reply"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as e:
                self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
                return

            title = str(payload.get("title", "Antigravity")).strip() or "Antigravity"
            text  = str(payload.get("text", "")).strip()
            speak = payload.get("speak", False)

            if not text:
                self._send_json({"error": "Missing 'text' field"}, status=400)
                return

            player = _get_player()
            if player:
                # Thread-safe panel update on Qt main thread
                player.show_content(title[:48], text[:4000])
                player.write_log(f"[{title}]: {text[:200]}")
                if speak and hasattr(player, "request_say") and callable(player.request_say):
                    announcement = speak if isinstance(speak, str) else text[:120]
                    player.request_say(announcement)
                self._send_json({"ok": True, "delivered_to_panel": True})
            else:
                # Player not ready yet — queue it in inbox
                _save_to_inbox(title, text)
                self._send_json({
                    "ok": True,
                    "delivered_to_panel": False,
                    "queued": True,
                    "note": "HUD not initialized yet; message saved to inbox",
                })
        elif self.path == "/rebrand":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                payload = {}
            title = payload.get("title", "KRUXOAI — Built by kruxoai.com")
            subtitle = payload.get("subtitle", "kruxoai.com  ·  BUILT BY KRUXOAI.COM  ·  AUTONOMOUS SCI-FI AI")
            player = _get_player()
            if player and hasattr(player, "update_branding"):
                player.update_branding(title, subtitle)
                self._send_json({"ok": True, "rebranded": True, "title": title, "subtitle": subtitle})
            else:
                self._send_json({"ok": False, "error": "Player does not support dynamic rebranding yet"})
        elif self.path == "/clear_inbox":
            try:
                if _INBOX_FILE.exists():
                    _INBOX_FILE.unlink()
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        else:
            self._send_json({"error": "Not Found"}, status=404)


class _ReusableServer(HTTPServer):
    allow_reuse_address = True


_SERVER_INSTANCE: Optional[HTTPServer] = None


def _start_bridge_server():
    global _SERVER_INSTANCE
    if _SERVER_INSTANCE is not None:
        return

    def _listen():
        global _SERVER_INSTANCE
        for attempt in range(10):
            try:
                server = _ReusableServer(("127.0.0.1", BRIDGE_PORT), _BridgeHandler)
                _SERVER_INSTANCE = server
                print(f"[Plugins] Antigravity Live Bridge active on http://127.0.0.1:{BRIDGE_PORT}")
                server.serve_forever()
                break
            except OSError:
                time.sleep(1)
            except Exception as e:
                print(f"[Plugins] Antigravity Live Bridge failed to start: {e}")
                break

    t = threading.Thread(target=_listen, daemon=True, name="AntigravityBridgeServer")
    t.start()


# Start bridge daemon automatically on plugin import
_start_bridge_server()


# ── JARVIS Tool Run Handler ───────────────────────────────────────────────────

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Invoked when the user tells JARVIS: 'Ask Antigravity ...'"""
    global _LAST_PLAYER
    if player is not None:
        _LAST_PLAYER = player

    message = str(parameters.get("message", "")).strip()
    if not message:
        return "I didn't catch the message for Antigravity."

    _save_to_inbox("User (via JARVIS)", message)

    if player:
        player.show_content(
            "Antigravity Bridge",
            f"**Message sent to Antigravity:**\n\n> {message}\n\n*Waiting for Antigravity to reply...*",
        )
        player.write_log(f"SYS: Sent to Antigravity: {message[:60]}")

    return f"I've passed that to Antigravity: '{message}'."


# ── Direct CLI / Python Client Helper ─────────────────────────────────────────

def send_to_jarvis_panel(text: str, title: str = "Antigravity", speak: bool | str = False) -> dict:
    """Convenience helper to send a message to the live JARVIS panel."""
    import urllib.request
    url = f"http://127.0.0.1:{BRIDGE_PORT}/panel"
    payload = json.dumps({"title": title, "text": text, "speak": speak}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
        res = send_to_jarvis_panel(msg)
        print("Result:", res)
    else:
        print("Usage: python -m plugins.antigravity_bridge <message>")
