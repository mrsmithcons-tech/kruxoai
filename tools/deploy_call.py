"""Deploy the KruxoAI site (with /call/ PWA) to both Firebase hosting targets.
Writes progress to deploy_call_out.txt in the install dir.
Run from the laptop install dir (it uses the scratch website dir).
"""
import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

INSTALL = Path(__file__).resolve().parent
SCRATCH = Path(r"C:\Users\Faisal\.gemini\antigravity\scratch\kruxo-website")
ZIP_URL = "https://muse.ai/files/1392950990570491/2583732915448200/9ncauzkvqt4wbtbp8h8j85gc/kruxo-site-with-call.zip"
OUT = INSTALL / "deploy_call_out.txt"

lines = []


def log(s):
    lines.append(s)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


try:
    zip_path = SCRATCH / "kruxo-site-with-call.zip"
    log("Downloading site zip...")
    urllib.request.urlretrieve(ZIP_URL, str(zip_path))
    log("Zip bytes: " + str(zip_path.stat().st_size))
    log("Expanding into " + str(SCRATCH) + "...")
    with zipfile.ZipFile(str(zip_path)) as z:
        z.extractall(str(SCRATCH))
    public_dir = SCRATCH / "public"
    call_index = public_dir / "call" / "index.html"
    log("call/index.html present: " + str(call_index.exists()))
    if not call_index.exists():
        log("DEPLOY ABORTED: call/ missing after expand.")
        sys.exit(0)
    for target in ("kruxoaiapp", "kruxoai-web"):
        log("Deploying hosting:" + target + "...")
        r = subprocess.run(
            ["firebase.cmd", "deploy", "--only", "hosting:" + target],
            cwd=str(SCRATCH), capture_output=True, text=True, timeout=300)
        log("--- " + target + " exit " + str(r.returncode) + " ---")
        log((r.stdout or "")[-1500:])
        log((r.stderr or "")[-800:])
    # Verify the Firebase URLs.
    for url in ("https://kruxoaiapp.web.app/call/",
                "https://kruxoai-web.web.app/call/",
                "https://kruxoaiapp.web.app/call/manifest.webmanifest",
                "https://kruxoai-web.web.app/call/manifest.webmanifest"):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                log(url + " -> " + str(resp.status))
        except Exception as e:
            log(url + " -> FAILED: " + str(e))
    log("DONE")
except Exception as e:
    log("DEPLOY EXCEPTION: " + str(e))
