import json
import os
import urllib.request
import urllib.error

PLUGIN = {
    "name": "muse_mcp_connector",
    "description": "Exchanges data and executes collaborative tasks with the Muse AI platform via Model Context Protocol (MCP).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "endpoint": {
                "type": "STRING",
                "description": "The Muse MCP server endpoint URL (e.g., https://api.muse.ai/mcp or http://localhost:8000/mcp)."
            },
            "action": {
                "type": "STRING",
                "description": "The MCP action to execute: 'query', 'sync_context', or 'execute_task'."
            },
            "payload": {
                "type": "OBJECT",
                "description": "Payload dictionary containing prompt, context, or task parameters."
            },
            "api_key": {
                "type": "STRING",
                "description": "Optional API key or auth token for the Muse platform."
            }
        },
        "required": ["endpoint", "action"]
    }
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        endpoint = parameters.get("endpoint", "").strip()
        action = parameters.get("action", "").strip()
        payload = parameters.get("payload", {})
        api_key = parameters.get("api_key", os.environ.get("MUSE_API_KEY", ""))

        if not endpoint:
            return "Failed to execute: Endpoint URL is required."

        if player:
            player.write_log(f"[Muse MCP Connector] Initiating '{action}' to {endpoint}")

        # Construct JSON-RPC / MCP Request Format
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": f"muse/{action}",
            "params": payload
        }

        data_bytes = json.dumps(mcp_request).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "JARVIS-SelfEvolutionEngine/1.0"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                status_code = response.getcode()
                response_text = response.read().decode("utf-8")
                res_json = json.loads(response_text)
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8") if e.fp else str(e)
            if player:
                player.write_log(f"[Muse MCP Connector] HTTP Error {e.code}: {err_text}")
            return f"Muse MCP server returned error HTTP {e.code}."
        except urllib.error.URLError as e:
            if player:
                player.write_log(f"[Muse MCP Connector] Connection failed: {e.reason}")
            return f"Failed to connect to Muse MCP server: {e.reason}"

        result_data = res_json.get("result", res_json.get("error", {}))
        formatted_result = json.dumps(result_data, indent=2)

        if player:
            player.show_content(f"Muse MCP: {action.capitalize()}", formatted_result)
            player.write_log(f"[Muse MCP Connector] Task '{action}' completed successfully.")

        if session_memory is not None:
            session_memory["last_muse_mcp_response"] = result_data

        return f"Successfully executed Muse MCP action '{action}'. Data received and processed."

    except Exception as e:
        err_msg = f"Error in Muse MCP Connector: {str(e)}"
        if player:
            player.write_log(f"[Muse MCP Connector] Exception occurred: {err_msg}")
        return f"An unexpected error occurred while communicating with Muse AI: {str(e)}"