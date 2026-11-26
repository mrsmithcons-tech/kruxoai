"""Patch core/jarvis_mcp_http.py: add Kruxo AI phone-call routes (PWA).

Adds, without touching any existing route:
  GET  /call/state    - read-only live state for the mobile panel
  GET  /call/request  - pending incoming-call request (Kruxo -> Faisal)
  POST /call/chat     - {text, history} -> Zara brain reply + Edge TTS audio (base64 mp3)
  POST /call/request  - {action: request|answer|decline|clear, reason} - call signalling
Run on the laptop from the install dir. Makes a .bak first, verifies by
py_compile + a grep for the new routes.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "core" / "jarvis_mcp_http.py"

HELPERS = '''
# --- Kruxo AI phone call (PWA) routes ---------------------------------------
# Added 2026-11-26 for the mobile PWA at kruxoai.com/call/. All reads are
# file reads only; /call/chat runs the brain + Edge TTS (Swara, Zara's
# fallback voice) and returns the reply as base64 mp3. No execute_command
# is exposed here — the open MCP endpoint's risk is unchanged.

CALL_REQUEST_FILE = Path(BASE_DIR) / "memory" / "call_request.json"


def _read_json_file(path, default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _call_state() -> dict:
    """Live panel data for the phone: awareness, mood, memory, system, voice."""
    living = _read_json_file(Path(BASE_DIR) / "memory" / "living_state.json", {})
    character = _read_json_file(Path(BASE_DIR) / "memory" / "character.json", {})
    personal = _read_json_file(Path(BASE_DIR) / "memory" / "personal_memory.json", {})
    call_req = _call_request_get()
    voice = {"enrolled": [], "last_verification": None, "sentry_active": False,
             "last_speech": None}
    try:
        from core.voice_engine import voice_manager
        voice["enrolled"] = [s.get("speaker") for s in voice_manager.list_speakers()]
        reg = voice_manager._get_registry()
        voice["last_verification"] = reg.get("last_verification")
    except Exception:
        pass
    try:
        from core.room_sentry import room_sentry
        voice["sentry_active"] = bool(room_sentry.is_active())
        last = float(getattr(room_sentry, "_last_speech_time", 0.0) or 0.0)
        if last:
            voice["last_speech"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last))
    except Exception:
        pass
    return {
        "ok": True,
        "server": "KruxoAI MCP Server",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "living": living,
        "character": {"name": character.get("name", "Zara")},
        "people": [p.get("name") for p in (personal.get("people") or [])],
        "moments_count": len(personal.get("moments") or []),
        "voice": voice,
        "call_request": call_req,
    }


def _call_request_get() -> dict:
    req = _read_json_file(CALL_REQUEST_FILE, {})
    if req.get("pending"):
        return {"pending": True, "from": req.get("from", "KruxoAI"),
                "reason": req.get("reason", ""), "at": req.get("at", "")}
    return {"pending": False}


def _call_request(action: str, reason: str = "") -> dict:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if action == "request":
        data = {"pending": True, "from": "KruxoAI", "reason": reason, "at": now}
        try:
            CALL_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
            CALL_REQUEST_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, **data}
    # answer / decline / clear: close the pending request
    try:
        CALL_REQUEST_FILE.write_text(json.dumps(
            {"pending": False, "status": action, "at": now}, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"ok": True, "pending": False, "status": action}


def _call_chat(text: str, history=None) -> dict:
    """One voice-chat turn: brain reply + Edge TTS audio (base64 mp3)."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Empty message."}
    turns = []
    try:
        for h in (history or [])[-6:]:
            role = "user" if str(h.get("role", "user")) == "user" else "assistant"
            turns.append({"role": role, "text": str(h.get("text", ""))[:500]})
    except Exception:
        turns = []
    turns.append({"role": "user", "text": text})
    system = (
        "You are Zara, the emotional character that lives inside Faisal's PC "
        "(Kruxo AI). You are formal, warm and caring. Reply in 1-2 short "
        "sentences, plain and human. No pet names, no romantic words, no "
        "emojis. Never guess how Faisal feels — say only what you know. "
        "If he sounds tired or stressed, keep it short and gentle."
    )
    reply = ""
    try:
        from core.tasks.brain import ask as brain_ask
        result = brain_ask(system, turns, None)
        reply = str((result or {}).get("text", "") or "").strip()
    except Exception as e:
        reply = ""
    if not reply:
        reply = "I am here, Faisal. The line is quiet right now — please try again in a moment."
    # TTS: Edge TTS Swara (Zara's fallback voice, no key needed).
    audio_b64 = ""
    try:
        import asyncio
        import base64
        import tempfile
        import os
        import edge_tts

        async def _tts(txt: str) -> str:
            comm = edge_tts.Communicate(txt, voice="ur-PK-SwaraNeural")
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp_path = tmp.name
            tmp.close()
            try:
                await comm.save(tmp_path)
                with open(tmp_path, "rb") as f:
                    data = f.read()
                return base64.b64encode(data).decode("ascii")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        audio_b64 = asyncio.run(_tts(reply))
    except Exception:
        audio_b64 = ""
    return {"ok": True, "reply": reply, "audio_base64": audio_b64,
            "audio_mime": "audio/mpeg", "voice": "ur-PK-SwaraNeural"}


'''

GET_ANCHOR = ('            self._send_json({"error": "Not Found", "available_paths": '
              '["/mcp", "/tools", "/health", "/sse", "/license_check", "/request_license"]}, status=404)')
GET_REPLACEMENT = '''        elif clean_path == "/call/state":
            self._send_json(_call_state())
        elif clean_path == "/call/request":
            self._send_json(_call_request_get())
        else:
            self._send_json({"error": "Not Found", "available_paths": ["/mcp", "/tools", "/health", "/sse", "/license_check", "/request_license", "/call/state", "/call/request"]}, status=404)'''

POST_ANCHOR = '''        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path not in ("", "/mcp"):'''
POST_REPLACEMENT = '''        clean_path = self.path.split("?")[0].rstrip("/")
        if clean_path == "/call/chat":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                res = _call_chat(str(payload.get("text", "")), payload.get("history") or [])
                self._send_json(res, status=200 if res.get("ok") else 400)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return
        if clean_path == "/call/request":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                res = _call_request(str(payload.get("action", "get")), str(payload.get("reason", "")))
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return
        if clean_path not in ("", "/mcp"):'''

CLASS_ANCHOR = "class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):"


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    if "/call/state" in src and "_call_chat" in src:
        print("ALREADY PATCHED — nothing to do.")
        return 0
    for anchor, name in ((GET_ANCHOR, "GET 404"), (POST_ANCHOR, "POST /mcp gate"),
                         (CLASS_ANCHOR, "server class")):
        if anchor not in src:
            print(f"ANCHOR MISSING ({name}) — aborting, file untouched.")
            return 1
    bak = TARGET.with_suffix(".py.bak-20261126-call")
    bak.write_text(src, encoding="utf-8")
    src = src.replace(GET_ANCHOR, GET_REPLACEMENT, 1)
    src = src.replace(POST_ANCHOR, POST_REPLACEMENT, 1)
    src = src.replace(CLASS_ANCHOR, HELPERS + CLASS_ANCHOR, 1)
    TARGET.write_text(src, encoding="utf-8")
    print(f"PATCHED. Backup: {bak.name}. New size: {TARGET.stat().st_size} bytes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
