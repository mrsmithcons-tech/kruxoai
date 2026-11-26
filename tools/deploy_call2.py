"""Fix the Firebase deploy: copy the expanded public/ (with call/) into the
real Firebase project dir (website/, which holds firebase.json), then deploy
both hosting targets and verify the live URLs. Writes to deploy_call_out2.txt.
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

INSTALL = Path(__file__).resolve().parent
SCRATCH = Path(r"C:\Users\Faisal\.gemini\antigravity\scratch\kruxo-website")
SRC = SCRATCH / "public"
DST = SCRATCH / "website" / "public"
OUT = INSTALL / "deploy_call_out2.txt"

lines = []


def log(s):
    lines.append(s)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


try:
    log("Copying public/ -> website/public/ ...")
    shutil.copytree(str(SRC), str(DST), dirs_exist_ok=True)
    log("website/public/call/index.html present: " + str((DST / "call" / "index.html").exists()))
    for target in ("kruxoaiapp", "kruxoai-web"):
        log("Deploying hosting:" + target + "...")
        r = subprocess.run(
            ["firebase.cmd", "deploy", "--only", "hosting:" + target],
            cwd=str(SCRATCH / "website"), capture_output=True, text=True, timeout=300)
        log("--- " + target + " exit " + str(r.returncode) + " ---")
        log((r.stdout or "")[-1500:])
        log((r.stderr or "")[-800:])
    for url in ("https://kruxoaiapp.web.app/call/",
                "https://kruxoai-web.web.app/call/",
                "https://kruxoaiapp.web.app/call/manifest.webmanifest",
                "https://kruxoai-web.web.app/call/manifest.webmanifest",
                "https://kruxoaiapp.web.app/call/sw.js",
                "https://kruxoai-web.web.app/call/sw.js"):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                log(url + " -> " + str(resp.status))
        except Exception as e:
            log(url + " -> FAILED: " + str(e))
    log("DONE")
except Exception as e:
    log("DEPLOY EXCEPTION: " + str(e))
