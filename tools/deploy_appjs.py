"""Deploy just the fixed app.js to both Firebase hosting targets.
Downloads app.js into both public/call/ dirs, deploys, verifies.
Writes to deploy_appjs_out.txt in the install dir.
"""
import subprocess
import urllib.request
from pathlib import Path

INSTALL = Path(__file__).resolve().parent
SCRATCH = Path(r"C:\Users\Faisal\.gemini\antigravity\scratch\kruxo-website")
APPJS_URL = "https://muse.ai/files/1392950990570491/1167062876183088/1933vkpn0mhfaixgle5mnr3j/app.js"
OUT = INSTALL / "deploy_appjs_out.txt"

lines = []


def log(s):
    lines.append(s)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


try:
    for dest in (SCRATCH / "public" / "call" / "app.js",
                 SCRATCH / "website" / "public" / "call" / "app.js"):
        urllib.request.urlretrieve(APPJS_URL, str(dest))
        log("wrote " + str(dest) + " (" + str(dest.stat().st_size) + " B, header present: " +
            str("ngrok-skip-browser-warning" in dest.read_text(encoding="utf-8")) + ")")
    for target in ("kruxoaiapp", "kruxoai-web"):
        log("Deploying hosting:" + target + "...")
        r = subprocess.run(
            ["firebase.cmd", "deploy", "--only", "hosting:" + target],
            cwd=str(SCRATCH / "website"), capture_output=True, text=True, timeout=300)
        log("--- " + target + " exit " + str(r.returncode) + " ---")
        log((r.stdout or "")[-800:])
        log((r.stderr or "")[-400:])
    for url in ("https://kruxoaiapp.web.app/call/app.js",
                "https://kruxoai-web.web.app/call/app.js"):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                body = resp.read().decode("utf-8", "ignore")
                log(url + " -> " + str(resp.status) +
                    " header present: " + str("ngrok-skip-browser-warning" in body))
        except Exception as e:
            log(url + " -> FAILED: " + str(e))
    log("DONE")
except Exception as e:
    log("DEPLOY EXCEPTION: " + str(e))
