"""Detached /call/chat test: writes the result to call_test_out.txt."""
import json
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "call_test_out.txt"
t0 = time.time()
try:
    req = urllib.request.Request(
        "http://127.0.0.1:9877/call/chat",
        data=json.dumps({
            "text": "Hello Zara, can you hear me? This is a test.",
            "history": [],
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))
    OUT.write_text(
        "OK: " + str(res.get("ok")) + "\n"
        "REPLY: " + str(res.get("reply")) + "\n"
        "AUDIO_B64_LEN: " + str(len(res.get("audio_base64") or "")) + "\n"
        "VOICE: " + str(res.get("voice")) + "\n"
        "SECS: " + str(round(time.time() - t0, 1)) + "\n"
        "ERROR: " + str(res.get("error")) + "\n",
        encoding="utf-8")
except Exception as e:
    OUT.write_text("EXCEPTION: " + str(e) + "\nSECS: " + str(round(time.time() - t0, 1)) + "\n",
                   encoding="utf-8")
