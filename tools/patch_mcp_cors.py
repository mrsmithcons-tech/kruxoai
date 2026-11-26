"""Add ngrok-skip-browser-warning to the MCP server's CORS Allow-Headers
(both _send_json and do_OPTIONS), so a browser PWA can send that header
and ngrok's free-tier browser warning page stops intercepting the calls.
Idempotent. Backs up the file first.
"""
import shutil
from pathlib import Path

D = Path(__file__).resolve().parent
F = D / "core" / "jarvis_mcp_http.py"
OLD = '"Content-Type, Authorization"'
NEW = '"Content-Type, Authorization, ngrok-skip-browser-warning"'
text = F.read_text(encoding="utf-8")
if NEW in text and OLD not in text:
    print("ALREADY FIXED")
else:
    n = text.count(OLD)
    shutil.copyfile(F, F.with_suffix(".py.bak-20261126-cors"))
    F.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print("PATCHED " + str(n) + " occurrences, backup .bak-20261126-cors")
