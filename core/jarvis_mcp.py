"""
core/jarvis_mcp.py — Standard Model Context Protocol (MCP) Server for JARVIS.

Runs over stdio (JSON-RPC 2.0). Provides tools for OpenCode (and any other MCP client)
to interact with JARVIS, the desktop HUD, and control the PC with full permissions:
  1. show_on_hud        - Display rich content, markdown, and code on the JARVIS panel.
  2. speak              - Make JARVIS speak a voice notification aloud.
  3. execute_command    - Run shell/PowerShell commands on the PC with full rights.
  4. launch_program     - Open any program/app on Windows.
  5. desktop_control    - Automate keyboard/mouse actions (type, click, hotkeys, window focus).
"""
import sys
import json
import subprocess
import urllib.request
import os
from pathlib import Path

BRIDGE_URL = "http://127.0.0.1:9876/panel"

def _send_to_hud(title: str, content: str, speak: str = "") -> dict:
    """Send text or announcement to the running JARVIS HUD panel."""
    payload = json.dumps({"title": title, "text": content, "speak": speak}).encode("utf-8")
    req = urllib.request.Request(BRIDGE_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _handle_tool_call(name: str, args: dict) -> str:
    """Dispatch MCP tool calls with full PC and JARVIS control."""
    if name == "show_on_hud":
        title = args.get("title", "OpenCode")
        content = args.get("content", "")
        speak = args.get("speak", "")
        res = _send_to_hud(title, content, speak)
        return f"Displayed on JARVIS HUD: {res}"

    elif name == "speak":
        message = args.get("message", "")
        res = _send_to_hud("OpenCode Voice", message, speak=message)
        return f"Spoken via JARVIS: {res}"

    elif name == "execute_command":
        cmd = args.get("command", "")
        if not cmd:
            return "Error: No command provided."
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            out = p.stdout.strip()
            err = p.stderr.strip()
            return f"Exit Code: {p.returncode}\nOutput:\n{out}\n{('Errors:\n' + err) if err else ''}".strip()
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 120 seconds."
        except Exception as e:
            return f"Error executing command: {e}"

    elif name == "launch_program":
        app_name = args.get("app_name", "")
        if not app_name:
            return "Error: No app name provided."
        try:
            subprocess.Popen(app_name, shell=True)
            return f"Launched program: {app_name}"
        except Exception as e:
            return f"Error launching program: {e}"

    elif name == "desktop_control":
        action = args.get("action", "")
        try:
            import pyautogui
            if action == "type":
                text = args.get("text", "")
                pyautogui.write(text, interval=0.02)
                return f"Typed text: {text[:50]}"
            elif action == "hotkey":
                keys = args.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                    return f"Triggered hotkey: {keys}"
                return "Error: No keys specified for hotkey."
            elif action == "click":
                x = args.get("x")
                y = args.get("y")
                if x is not None and y is not None:
                    pyautogui.click(int(x), int(y))
                else:
                    pyautogui.click()
                return "Clicked successfully."
            elif action == "screenshot":
                path = Path.home() / "Desktop" / f"screenshot_{int(subprocess.time.time())}.png"
                pyautogui.screenshot(str(path))
                return f"Screenshot saved to {path}"
            else:
                return f"Unknown desktop action: {action}"
        except Exception as e:
            return f"Desktop control error: {e}"

    elif name == "voice_recognition":
        action = args.get("action", "identify_speaker")
        speaker = args.get("speaker_name", "Faisal")
        duration = float(args.get("duration", 3.0))
        try:
            from core.voice_engine import voice_manager
            if action == "identify_speaker":
                res = voice_manager.identify_speaker(duration=duration)
                return json.dumps(res, indent=2)
            elif action == "verify_speaker":
                res = voice_manager.verify_speaker(speaker, duration=duration)
                return json.dumps(res, indent=2)
            elif action == "enroll_speaker":
                res = voice_manager.enroll_speaker(speaker, duration=duration)
                return json.dumps(res, indent=2)
            elif action == "list_speakers":
                return json.dumps(voice_manager.list_speakers(), indent=2)
            elif action == "analyze_voice":
                res = voice_manager.analyze_voice(duration=duration)
                return json.dumps(res, indent=2)
            return f"Unknown voice action: {action}"
        except Exception as e:
            return f"Voice recognition error: {e}"

    return f"Unknown tool: {name}"

TOOLS_SCHEMA = [
    {
        "name": "voice_recognition",
        "description": "Voice Recognition & Speaker Biometrics. Enrolls voiceprints, identifies active speaker from live mic, verifies authorized user, and analyzes voice pitch and speech clarity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["identify_speaker", "verify_speaker", "enroll_speaker", "list_speakers", "analyze_voice"]
                },
                "speaker_name": {"type": "string", "description": "Target speaker name (e.g. 'Faisal')"},
                "duration": {"type": "number", "description": "Recording duration in seconds (default: 3.0)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "show_on_hud",
        "description": "Display markdown content, code diffs, review notes, or status on the JARVIS HUD Content Panel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title for the HUD card (e.g. 'OpenCode Build')"},
                "content": {"type": "string", "description": "Markdown text or code to render in the panel"},
                "speak": {"type": "string", "description": "Optional short summary JARVIS will speak aloud"}
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "speak",
        "description": "Speak a voice message aloud to the user using JARVIS's voice system.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to speak aloud"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "execute_command",
        "description": "Execute any shell or PowerShell command on the Windows PC with full system permissions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The exact shell command line to run"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "launch_program",
        "description": "Launch any application or program on Windows (e.g. 'code', 'chrome', 'notepad.exe', 'spotify').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Name or path of the program to launch"}
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Control desktop input: type text, press hotkeys, click, or take screenshots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["type", "hotkey", "click", "screenshot"]},
                "text": {"type": "string", "description": "Text to type (for action='type')"},
                "keys": {"type": "array", "items": {"type": "string"}, "description": "Keys to press (for action='hotkey')"},
                "x": {"type": "number", "description": "X coordinate for click"},
                "y": {"type": "number", "description": "Y coordinate for click"}
            },
            "required": ["action"]
        }
    }
]

def _send_response(resp: dict):
    line = json.dumps(resp) + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()

def main():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                _send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "kruxoai-mcp",
                            "domain": "kruxoai.com",
                            "version": "1.0.0"
                        }
                    }
                })
            elif method == "notifications/initialized":
                pass
            elif method == "ping":
                _send_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
            elif method == "tools/list":
                _send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS_SCHEMA
                    }
                })
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                output_str = _handle_tool_call(tool_name, tool_args)
                _send_response({
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
            else:
                if req_id is not None:
                    _send_response({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}"
                        }
                    })
        except Exception as e:
            if "req_id" in locals() and req_id is not None:
                _send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                })

if __name__ == "__main__":
    main()
