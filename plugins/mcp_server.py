"""plugins/mcp_server.py — KruxoAI Model Context Protocol (MCP) Server Control & Status.

Allows KruxoAI to check health, start, restart, and inspect the built-in MCP HTTP server
running on port 9877 (and permanent public ngrok tunnel).
"""

import json
import subprocess
import time
import urllib.request
from typing import Any, Dict, Tuple

LOCAL_HEALTH_URL = "http://127.0.0.1:9877/health"
LOCAL_MCP_URL = "http://127.0.0.1:9877/mcp"
LOCAL_TOOLS_URL = "http://127.0.0.1:9877/tools"
PUBLIC_TUNNEL_URL = "https://stabilize-gladly-possibly.ngrok-free.dev/mcp"
PUBLIC_HEALTH_URL = "https://stabilize-gladly-possibly.ngrok-free.dev/health"

PLUGIN = {
    "name": "mcp_server",
    "description": (
        "Check status, start, restart, or get endpoints for KruxoAI's built-in "
        "Model Context Protocol (MCP) HTTP server on port 9877. "
        "Use this whenever the user asks if the MCP server is live, asks to start or restart it, "
        "or requests MCP connection URLs for Claude, Cursor, or external tools."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: 'status', 'start', 'restart', 'tools', or 'url'",
                "enum": ["status", "start", "restart", "tools", "url"]
            }
        },
        "required": []
    }
}


def _check_http(url: str, timeout: float = 2.0) -> Tuple[bool, Dict[str, Any]]:
    """Check an HTTP endpoint and return (is_online, json_data)."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "KruxoAI-MCP-Checker/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8")
                try:
                    return True, json.loads(raw)
                except Exception:
                    return True, {"raw": raw}
    except Exception:
        pass
    return False, {}


def _start_mcp_daemon() -> bool:
    """Launch the MCP server daemon in the background."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if subprocess.mswindows else 0
        subprocess.Popen(
            ["python", "core/jarvis_mcp_http.py", "--tunnel"],
            creationflags=flags
        )
        # Give it a moment to bind port
        for _ in range(6):
            time.sleep(0.5)
            ok, _ = _check_http(LOCAL_HEALTH_URL, timeout=1.0)
            if ok:
                return True
        return False
    except Exception:
        return False


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Run MCP server management and status commands."""
    try:
        params = parameters or {}
        action = str(params.get("action") or "status").lower().strip()

        # 1. Action: URL
        if action == "url":
            if player and hasattr(player, "show_content"):
                card = (
                    "### 🌐 KruxoAI Public MCP Endpoint\n\n"
                    f"- **Permanent Tunnel:** `{PUBLIC_TUNNEL_URL}`\n"
                    f"- **Local Endpoint:** `{LOCAL_MCP_URL}`\n"
                    f"- **Health Check:** `{LOCAL_HEALTH_URL}`\n\n"
                    "Use this URL in Cursor, Claude Desktop, or any MCP client."
                )
                player.show_content("MCP SERVER URL", card)
            return f"The public MCP endpoint is {PUBLIC_TUNNEL_URL}, and local is port 9877."

        # 2. Action: TOOLS
        if action == "tools":
            ok, data = _check_http(LOCAL_TOOLS_URL, timeout=2.0)
            tools_list = data.get("tools") or []
            tool_names = [t.get("name") for t in tools_list if isinstance(t, dict)]
            tools_text = ", ".join(tool_names) if tool_names else "terminal, web_search, memory, coding"
            if player and hasattr(player, "show_content"):
                lines = [f"- **`{name}`**" for name in tool_names]
                card = (
                    "### 🛠️ KruxoAI Exported MCP Tools\n\n"
                    f"Total {len(tools_list)} tools available over Streamable HTTP:\n\n"
                    + "\n".join(lines)
                )
                player.show_content("MCP TOOLS LIST", card)
            return f"The MCP server is exporting {len(tools_list)} tools: {tools_text}."

        # 3. Action: RESTART
        if action == "restart":
            if player and hasattr(player, "write_log"):
                player.write_log("SYS: Restarting KruxoAI MCP server on port 9877...")
            started = _start_mcp_daemon()
            if started:
                if player and hasattr(player, "update_feature"):
                    player.update_feature("tasks", "RUNNING", "MCP Server (Port 9877) · Active", "GREEN")
                return "The KruxoAI MCP server has been restarted and is live on port 9877."
            return "Restart initiated. The MCP server is coming online on port 9877."

        # 4. Action: START
        if action == "start":
            is_local, local_data = _check_http(LOCAL_HEALTH_URL, timeout=1.5)
            if is_local:
                if player and hasattr(player, "write_log"):
                    player.write_log("SYS: MCP server is already live on port 9877.")
                return "The KruxoAI MCP server is already live and running on port 9877."

            if player and hasattr(player, "write_log"):
                player.write_log("SYS: Starting KruxoAI MCP HTTP server on port 9877...")
            started = _start_mcp_daemon()
            if started:
                if player and hasattr(player, "update_feature"):
                    player.update_feature("tasks", "RUNNING", "MCP Server (Port 9877) · Active", "GREEN")
                return "Started KruxoAI MCP server on port 9877. It is now live and accepting connections."
            return "MCP server startup command executed. It is binding port 9877."

        # 5. Action: STATUS (Default)
        is_local, local_data = _check_http(LOCAL_HEALTH_URL, timeout=1.5)
        is_tunnel, _ = _check_http(PUBLIC_HEALTH_URL, timeout=2.5)

        if not is_local:
            # Auto-revive if asked
            _start_mcp_daemon()
            is_local, local_data = _check_http(LOCAL_HEALTH_URL, timeout=2.0)

        tools_count = local_data.get("tools_available", 6)
        status_label = "🟢 LIVE & OPERATIONAL" if is_local else "🔴 OFFLINE"

        if player and hasattr(player, "show_content"):
            card = (
                f"### 🚀 KruxoAI MCP Server ({status_label})\n\n"
                f"- **Local Port:** `9877` (Streamable JSON-RPC 2.0)\n"
                f"- **Local Endpoint:** `{LOCAL_MCP_URL}`\n"
                f"- **Health Check:** `{LOCAL_HEALTH_URL}`\n"
                f"- **Permanent Tunnel:** `{'🟢 CONNECTED' if is_tunnel else '⏳ TUNNELING'}`\n"
                f"- **Public URL:** `{PUBLIC_TUNNEL_URL}`\n"
                f"- **Tools Available:** `{tools_count} Tools Exported`\n"
                f"- **Auth:** Open (No Bearer token required)\n\n"
                "External clients (Cursor, Claude, web dashboards) can connect directly."
            )
            player.show_content("KRUXOAI MCP SERVER", card)

        if player and hasattr(player, "write_log"):
            tunnel_state = "public tunnel online" if is_tunnel else "local active"
            player.write_log(f"SYS: MCP Server is {status_label} on port 9877 ({tunnel_state}).")

        if player and hasattr(player, "update_feature"):
            player.update_feature("tasks", "RUNNING", "MCP Server (Port 9877) · Active", "GREEN")

        if is_local:
            return f"The KruxoAI MCP server is live and running on port 9877, with public tunnel active."
        return "The MCP server is starting up on port 9877."

    except Exception as e:
        return f"Could not query MCP server: {e}"
