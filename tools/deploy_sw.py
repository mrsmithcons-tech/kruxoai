"""Deploy the fixed sw.js (v2, network-first) to both Firebase hosting targets.
Downloads sw.js into both public/call/ dirs, deploys, verifies.
Writes to deploy_sw_out.txt in the install dir.
"""
import subprocess
import urllib.request
from pathlib import Path

INSTALL = Path(__file__).resolve().parent
SCRATCH = Path(r"C:\Users\Faisal\.gemini\antigravity\scratch\kruxo-website")
SW_URL = "https://muse.ai/files/1392950990570491/2696336697551594/5nmaq0yasco0fpzppwl91udl/sw.js"
OUT = INSTALL / "deploy_sw_out.txt"

lines = []


def log(s):
    lines.append(s)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


try:
    for dest in (SCRATCH / "public" / "call" / "sw.js",
                 SCRATCH / "website" / "public" / "call" / "sw.js"):
        urllib.request.urlretrieve(SW_URL, str(dest))
        log("wrote " + str(dest) + " (" + str(dest.stat().st_size) + " B, v2 present: " +
            str("kruxo-call-v2" in dest.read_text(encoding="utf-8")) + ")")
    for target in ("kruxoaiapp", "kruxoai-web"):
        log("Deploying hosting:" + target + "...")
        r = subprocess.run(
            ["firebase.cmd", "deploy", "--only", "hosting:" + target],
            cwd=str(SCRATCH / "website"), capture_output=True, text=True, timeout=300)
        log("--- " + target + " exit " + str(r.returncode) + " ---")
        log((r.stdout or "")[-800:])
        log((r.stderr or "")[-400:])
    for url in ("https://kruxoaiapp.web.app/call/sw.js",
                "https://kruxoai-web.web.app/call/sw.js"):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                body = resp.read().decode("utf-8", "ignore")
                log(url + " -> " + str(resp.status) +
                    " v2 present: " + str("kruxo-call-v2" in body))
        except Exception as e:
            log(url + " -> FAILED: " + str(e))
    log("DONE")
except Exception as e:
    log("DEPLOY EXCEPTION: " + str(e))
