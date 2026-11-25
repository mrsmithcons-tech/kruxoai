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
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.jarvis_mcp import TOOLS_SCHEMA, _handle_tool_call

DEFAULT_PORT = 9877
AUTH_TOKEN = os.environ.get("JARVIS_MCP_TOKEN", "")

# ── Multi-Threaded HTTP Server ───────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class MCPHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet standard HTTP logs; error output preserved
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
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
            except (BrokenPipeError, ConnectionResetError):
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
        else:
            self._send_json({"error": "Not Found", "available_paths": ["/mcp", "/tools", "/health", "/sse", "/license_check"]}, status=404)

    def do_POST(self):
        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path == "/security_alert":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                from core.license_manager import dispatch_tamper_alert
                dispatch_tamper_alert("REMOTE_ALERT_" + str(payload.get("alert_type", "UNKNOWN")), payload)
                self._send_json({"ok": True, "alert_logged": True})
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        if not self._check_auth():
            self._send_json({"error": "Unauthorized: Invalid or missing Bearer token."}, status=401)
            return

        clean_path = self.path.split("?")[0].rstrip("/")
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

    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS HTTP / Streamable MCP Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on (default: 9877)")
    parser.add_argument("--token", type=str, default="", help="Optional Bearer token for authentication")
    parser.add_argument("--tunnel", action="store_true", default=True, help="Launch permanent static ngrok tunnel")
    args = parser.parse_args()

    run_server(port=args.port, token=args.token, enable_tunnel=args.tunnel)
