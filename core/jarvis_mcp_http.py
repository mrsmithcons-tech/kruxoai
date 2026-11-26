"""
core/jarvis_mcp_http.py — HTTP / Streamable HTTP Model Context Protocol (MCP) Server for JARVIS.

Enables cloud & remote AI platforms (like Muse AI) to connect directly to JARVIS:
- Transport: Streamable HTTP / JSON-RPC 2.0 over HTTP (POST /mcp & GET /sse).
- Public Tunnel: Built-in Cloudflare tunnel helper for instant public HTTPS URLs.
- Authentication: Bearer Token / API Key support.
- Tools: show_on_hud, speak, execute_command, launch_program, desktop_control.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.jarvis_mcp import TOOLS_SCHEMA, _handle_tool_call

DEFAULT_PORT = 9877
AUTH_TOKEN = os.environ.get("JARVIS_MCP_TOKEN", "")


def _handle_incoming_license_request(email: str, name: str, payment_ref: str, auto_approve: bool = True) -> dict:
    """Process incoming remote license requests from kruxoai.com or client activations.

    Generates HMAC-signed $20 lifetime license keys, registers them in the DRM database,
    and alerts Faisal immediately on his desktop HUD with spoken audio.
    """
    from core.license_manager import register_buyer
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        return {"ok": False, "error": "Invalid email address format."}
    buyer_name = name.strip() or clean_email.split("@")[0].title()
    time_str = time.strftime("%Y-%m-%d %I:%M %p")
    REQUESTS_FILE = Path(BASE_DIR) / "memory" / "license_requests.json"
    requests_list = []
    if REQUESTS_FILE.exists():
        try:
            requests_list = json.loads(REQUESTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    key = ""
    status = "PENDING"
    if auto_approve:
        res = register_buyer(clean_email, buyer_name, notes=f"Auto-approved ({payment_ref})")
        if res.get("ok"):
            key = res["buyer"]["license_key"]
            status = "APPROVED"
        else:
            key = res.get("buyer", {}).get("license_key", "")
            status = "EXISTING" if key else "FAILED"
    req_entry = {
        "timestamp": time.time(),
        "time_str": time_str,
        "email": clean_email,
        "name": buyer_name,
        "payment_ref": payment_ref,
        "status": status,
        "license_key": key
    }
    requests_list.append(req_entry)
    try:
        REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        REQUESTS_FILE.write_text(json.dumps(requests_list[-100:], indent=2), encoding="utf-8")
    except Exception:
        pass

    # Post real-time alert to Faisal's desktop HUD via Qt bridge (port 9876)
    try:
        spoken = (
            f"Faisal, a new license activation request has arrived from {buyer_name}. Lifetime key {key} has been generated."
            if auto_approve and key else
            f"Faisal, a new license activation request has arrived from {buyer_name}."
        )
        card = (
            f"### 🔔 License Activation Request\n\n"
            f"- **Buyer:** `{buyer_name}` (`{clean_email}`)\n"
            f"- **Payment Reference:** `{payment_ref}`\n"
            f"- **Status:** `{'✅ ' + status if auto_approve else '⏳ PENDING'}`\n"
            f"- **Generated Key:** `{key}`\n"
            f"- **Time:** `{time_str}`\n\n"
            f"License registered in your commercial buyer database."
        )
        alert_req = urllib.request.Request(
            "http://127.0.0.1:9876/panel",
            data=json.dumps({"title": f"🔔 LICENSE REQUEST: {buyer_name}", "text": card, "speak": spoken}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(alert_req, timeout=1.5)
    except Exception:
        pass

    return {
        "ok": True,
        "status": status,
        "email": clean_email,
        "name": buyer_name,
        "license_key": key,
        "plan": "KruxoAI Lifetime Access ($20)",
        "domain": "kruxoai.com"
    }


# ── Multi-Threaded HTTP Server ───────────────────────────────────────────────


# --- Kruxo AI phone call (PWA) routes ---------------------------------------
# Added 2026-11-26 for the mobile PWA at kruxoai.com/call/. All reads are
# file reads only; /call/chat runs the brain + Edge TTS (Swara, Zara's
# fallback voice) and returns the reply as base64 mp3. No execute_command
# is exposed here — the open MCP endpoint's risk is unchanged.

CALL_REQUEST_FILE = Path(BASE_DIR) / "memory" / "call_request.json"


def _read_json_file(path, default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _call_state() -> dict:
    """Live panel data for the phone: awareness, mood, memory, system, voice."""
    living = _read_json_file(Path(BASE_DIR) / "memory" / "living_state.json", {})
    character = _read_json_file(Path(BASE_DIR) / "memory" / "character.json", {})
    personal = _read_json_file(Path(BASE_DIR) / "memory" / "personal_memory.json", {})
    call_req = _call_request_get()
    voice = {"enrolled": [], "last_verification": None, "sentry_active": False,
             "last_speech": None}
    try:
        from core.voice_engine import voice_manager
        voice["enrolled"] = [s.get("speaker") for s in voice_manager.list_speakers()]
        reg = voice_manager._get_registry()
        voice["last_verification"] = reg.get("last_verification")
    except Exception:
        pass
    try:
        from core.room_sentry import room_sentry
        voice["sentry_active"] = bool(room_sentry.is_active())
        last = float(getattr(room_sentry, "_last_speech_time", 0.0) or 0.0)
        if last:
            voice["last_speech"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last))
    except Exception:
        pass
    return {
        "ok": True,
        "server": "KruxoAI MCP Server",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "living": living,
        "character": {"name": character.get("name", "Zara")},
        "people": [p.get("name") for p in (personal.get("people") or [])],
        "moments_count": len(personal.get("moments") or []),
        "voice": voice,
        "call_request": call_req,
    }


def _call_request_get() -> dict:
    req = _read_json_file(CALL_REQUEST_FILE, {})
    if req.get("pending"):
        return {"pending": True, "from": req.get("from", "KruxoAI"),
                "reason": req.get("reason", ""), "at": req.get("at", "")}
    return {"pending": False}


def _call_request(action: str, reason: str = "") -> dict:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if action == "request":
        data = {"pending": True, "from": "KruxoAI", "reason": reason, "at": now}
        try:
            CALL_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
            CALL_REQUEST_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, **data}
    # answer / decline / clear: close the pending request
    try:
        CALL_REQUEST_FILE.write_text(json.dumps(
            {"pending": False, "status": action, "at": now}, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"ok": True, "pending": False, "status": action}


def _call_chat(text: str, history=None) -> dict:
    """One voice-chat turn: brain reply + Edge TTS audio (base64 mp3)."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Empty message."}
    turns = []
    try:
        for h in (history or [])[-6:]:
            role = "user" if str(h.get("role", "user")) == "user" else "assistant"
            turns.append({"role": role, "text": str(h.get("text", ""))[:500]})
    except Exception:
        turns = []
    turns.append({"role": "user", "text": text})
    system = (
        "You are Zara, the emotional character that lives inside Faisal's PC "
        "(Kruxo AI). You are formal, warm and caring. Reply in 1-2 short "
        "sentences, plain and human. No pet names, no romantic words, no "
        "emojis. Never guess how Faisal feels — say only what you know. "
        "If he sounds tired or stressed, keep it short and gentle."
    )
    reply = ""
    try:
        from core.tasks.brain import ask as brain_ask
        result = brain_ask(system, turns, None)
        reply = str((result or {}).get("text", "") or "").strip()
    except Exception:
        reply = ""
    if not reply:
        reply = "I am here, Faisal. The line is quiet right now — please try again in a moment."
    # TTS: Edge TTS. ur-PK-SwaraNeural does NOT exist (Edge lists only
    # ur-PK-AsadNeural / ur-PK-UzmaNeural) — that is why the first version
    # returned no audio. Try Aria (female, English) then Uzma (female Urdu).
    audio_b64 = ""
    voice_used = ""
    try:
        import asyncio
        import base64
        import tempfile
        import os
        import edge_tts

        async def _tts(txt: str):
            for v in ("en-US-AriaNeural", "ur-PK-UzmaNeural"):
                comm = edge_tts.Communicate(txt, voice=v)
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp_path = tmp.name
                tmp.close()
                try:
                    await comm.save(tmp_path)
                    with open(tmp_path, "rb") as f:
                        data = f.read()
                    if data:
                        return base64.b64encode(data).decode("ascii"), v
                except Exception:
                    pass
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            return "", ""

        audio_b64, voice_used = asyncio.run(_tts(reply))
    except Exception:
        audio_b64, voice_used = "", ""
    return {"ok": True, "reply": reply, "audio_base64": audio_b64,
            "audio_mime": "audio/mpeg", "voice": voice_used or "none"}

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        """Suppress noisy broken pipe / connection aborted tracebacks."""
        import sys
        exctype = sys.exc_info()[0]
        if exctype and issubclass(exctype, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class MCPHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet standard HTTP logs; error output preserved
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send_json(self, data: dict, status: int = 200):
        try:
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, ngrok-skip-browser-warning")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            pass

    def _check_auth(self) -> bool:
        global AUTH_TOKEN
        if not AUTH_TOKEN:
            return True  # Open auth
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            return token == AUTH_TOKEN
        # Also check query param ?token=
        if f"token={AUTH_TOKEN}" in self.path:
            return True
        return False

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, ngrok-skip-browser-warning")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if not self._check_auth():
            self._send_json({"error": "Unauthorized: Invalid or missing Bearer token."}, status=401)
            return

        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path in ("", "/health", "/status"):
            self._send_json({
                "status": "online",
                "server": "KruxoAI MCP Server",
                "brand": "KruxoAI",
                "domain": "kruxoai.com",
                "official_website": "https://kruxoai.com",
                "version": "1.0.0",
                "transport": "Streamable HTTP (JSON-RPC 2.0)",
                "endpoints": {
                    "mcp_rpc": "/mcp",
                    "tools_list": "/tools",
                    "health": "/health"
                },
                "tools_available": len(TOOLS_SCHEMA),
                "auth_required": bool(AUTH_TOKEN)
            })
        elif clean_path in ("/tools", "/tools/list"):
            self._send_json({"tools": TOOLS_SCHEMA})
        elif clean_path == "/sse":
            # Server-Sent Events endpoint for clients negotiating SSE transport
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                # Send endpoint discovery event
                init_event = f"event: endpoint\ndata: /mcp\n\n"
                self.wfile.write(init_event.encode("utf-8"))
                self.wfile.flush()
                while True:
                    time.sleep(15)
                    ping = "event: ping\ndata: {}\n\n"
                    self.wfile.write(ping.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, Exception):
                pass
        elif clean_path == "/license_check":
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            email = query.get("email", [""])[0]
            key = query.get("key", [""])[0]
            try:
                from core.license_manager import is_banned, verify_license_key
                banned, reason = is_banned(email)
                if not banned and key:
                    banned, reason = is_banned(key)
                valid = verify_license_key(email, key) if (email and key and not banned) else False
                self._send_json({"valid": valid, "banned": banned, "reason": reason if banned else ""})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        elif clean_path in ("/request_license", "/license_request"):
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            email = query.get("email", [""])[0]
            name = query.get("name", [""])[0]
            payment_ref = query.get("payment_ref", ["kruxoai.com checkout"])[0]
            auto_approve = query.get("auto", ["true"])[0].lower() in ("true", "1", "yes")
            res = _handle_incoming_license_request(email, name, payment_ref, auto_approve=auto_approve)
            self._send_json(res, status=200 if res.get("ok") else 400)
        elif clean_path == "/call/state":
            self._send_json(_call_state())
        elif clean_path == "/call/request":
            self._send_json(_call_request_get())
        else:
            self._send_json({"error": "Not Found", "available_paths": ["/mcp", "/tools", "/health", "/sse", "/license_check", "/request_license", "/call/state", "/call/request"]}, status=404)

    def do_POST(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path in ("/request_license", "/license_request"):
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                email = payload.get("email", "")
                name = payload.get("name", "")
                payment_ref = payload.get("payment_ref", "kruxoai.com checkout")
                auto_approve = payload.get("auto_approve", True)
                res = _handle_incoming_license_request(email, name, payment_ref, auto_approve=auto_approve)
                self._send_json(res, status=200 if res.get("ok") else 400)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        if clean_path == "/security_alert":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                alerts_file = Path(BASE_DIR) / "memory" / "tamper_alerts.json"
                alerts = []
                if alerts_file.exists():
                    try:
                        alerts = json.loads(alerts_file.read_text(encoding="utf-8"))
                    except Exception:
                        alerts = []
                alert_type = str(payload.get("alert_type", "REMOTE_SECURITY_ALERT"))
                alerts.append({
                    "timestamp": time.time(),
                    "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "alert_type": alert_type,
                    "payload": payload
                })
                alerts_file.parent.mkdir(parents=True, exist_ok=True)
                alerts_file.write_text(json.dumps(alerts[-100:], indent=2), encoding="utf-8")

                # Forward single clean notification to HUD without re-dispatching to network
                try:
                    alert_req = urllib.request.Request(
                        "http://127.0.0.1:9876/panel",
                        data=json.dumps({
                            "title": f"🚨 CLIENT ALERT: {alert_type}",
                            "text": f"Remote Client Security Alert:\n{json.dumps(payload, indent=2)}",
                            "speak": "Security alert recorded from remote client."
                        }).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    urllib.request.urlopen(alert_req, timeout=1)
                except Exception:
                    pass

                self._send_json({"ok": True, "alert_logged": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        if not self._check_auth():
            self._send_json({"error": "Unauthorized: Invalid or missing Bearer token."}, status=401)
            return

        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path == "/call/chat":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                res = _call_chat(str(payload.get("text", "")), payload.get("history") or [])
                self._send_json(res, status=200 if res.get("ok") else 400)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return
        if clean_path == "/call/request":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                res = _call_request(str(payload.get("action", "get")), str(payload.get("reason", "")))
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return
        if clean_path not in ("", "/mcp"):
            self._send_json({"error": f"Endpoint not found: {clean_path}. Use /mcp"}, status=404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            req = json.loads(raw_body)
        except Exception as e:
            self._send_json({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"}
            }, status=400)
            return

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        # Standard MCP / JSON-RPC 2.0 Dispatcher
        if method == "initialize":
            self._send_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "jarvis-mcp-server",
                        "version": "1.0.0"
                    }
                }
            })
        elif method == "notifications/initialized":
            self._send_json({"jsonrpc": "2.0", "id": req_id, "result": {}})
        elif method == "ping":
            self._send_json({"jsonrpc": "2.0", "id": req_id, "result": {}})
        elif method in ("tools/list", "mcp/tools"):
            self._send_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOLS_SCHEMA
                }
            })
        elif method in ("tools/call", "mcp/call"):
            from core.license_manager import get_license_status
            if not get_license_status().get("activated"):
                self._send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32001,
                        "message": "KruxoAI commercial license activation required. Purchase lifetime access at https://kruxoai.com ($20)."
                    }
                }, status=403)
                return

            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                output_str = _handle_tool_call(tool_name, tool_args)
                self._send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": output_str
                            }
                        ],
                        "isError": False
                    }
                })
            except Exception as e:
                self._send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: {e}"
                            }
                        ],
                        "isError": True
                    }
                })
        else:
            self._send_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }, status=404)


# ── Permanent Static Tunnel Runner ───────────────────────────────────────────

PERMANENT_STATIC_DOMAIN = "stabilize-gladly-possibly.ngrok-free.dev"
PERMANENT_STATIC_URL = f"https://{PERMANENT_STATIC_DOMAIN}"


def _get_active_tunnel_url() -> Optional[str]:
    """Check if an ngrok tunnel is already active."""
    try:
        req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for tun in data.get("tunnels", []):
                if tun.get("proto") == "https":
                    return tun.get("public_url")
    except Exception:
        pass
    return None


def start_permanent_tunnel(port: int = DEFAULT_PORT) -> str:
    """
    Ensures ngrok is locked to the permanent static domain.
    Never assigns a random or ephemeral URL.
    """
    active_url = _get_active_tunnel_url()
    if active_url and PERMANENT_STATIC_DOMAIN in active_url:
        return active_url

    # Terminate any conflicting or stale ngrok process
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], capture_output=True)
        time.sleep(1.0)
    except Exception:
        pass

    # Launch with permanent domain lock
    try:
        cmd = ["ngrok", "start", "jarvis"]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if subprocess.mswindows else 0
        )
        time.sleep(2.0)
    except Exception:
        try:
            cmd = ["ngrok", "http", str(port), "--url", PERMANENT_STATIC_URL]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if subprocess.mswindows else 0
            )
            time.sleep(2.0)
        except Exception as e:
            print(f"[Tunnel Error]: {e}")

    return PERMANENT_STATIC_URL


def run_server(port: int = DEFAULT_PORT, token: str = "", enable_tunnel: bool = True):
    global AUTH_TOKEN
    AUTH_TOKEN = token.strip()

    server = ThreadedHTTPServer(("0.0.0.0", port), MCPHTTPHandler)
    local_url = f"http://localhost:{port}/mcp"

    if enable_tunnel:
        pub_url = start_permanent_tunnel(port)
        final_mcp_url = f"{pub_url}/mcp"
    else:
        final_mcp_url = local_url

    print(f"\n=======================================================")
    print(f"🚀 KruxoAI MCP HTTP Server Active (kruxoai.com)!")
    print(f"• Domain:          kruxoai.com")
    print(f"• Local Endpoint:  {local_url}")
    print(f"• Health Check:    http://localhost:{port}/health")
    print(f"• Transport:       Streamable HTTP (JSON-RPC 2.0)")
    print(f"• Tools Count:     {len(TOOLS_SCHEMA)}")
    print(f"• Auth:            {'Bearer ' + AUTH_TOKEN if AUTH_TOKEN else 'None (Open)'}")
    print(f"-------------------------------------------------------")
    print(f"✨ PERMANENT STATIC PUBLIC MCP URL (NEVER CHANGES):")
    print(f"👉 {final_mcp_url}")
    print(f"=======================================================\n")

    while True:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            break
        except Exception as e:
            time.sleep(1.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS HTTP / Streamable MCP Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on (default: 9877)")
    parser.add_argument("--token", type=str, default="", help="Optional Bearer token for authentication")
    parser.add_argument("--tunnel", action="store_true", default=True, help="Launch permanent static ngrok tunnel")
    args = parser.parse_args()

    run_server(port=args.port, token=args.token, enable_tunnel=args.tunnel)
