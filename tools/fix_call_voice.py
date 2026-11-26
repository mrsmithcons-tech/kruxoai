"""Fix the /call/chat voice in core/jarvis_mcp_http.py.

ur-PK-SwaraNeural does not exist (Edge TTS lists only ur-PK-AsadNeural and
ur-PK-UzmaNeural) — that is why /call/chat returned audio_base64="".
New behaviour: try en-US-AriaNeural (female, clear for English/Roman Urdu),
then ur-PK-UzmaNeural (female Urdu). Returns the voice that worked.
Replaces the whole _call_chat function (it is the last helper before the
server class). Makes a .bak first, verifies by py_compile.
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "core" / "jarvis_mcp_http.py"

NEW_FN = '''def _call_chat(text: str, history=None) -> dict:
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
    except Exception:
        reply = ""
    if not reply:
        reply = "I am here, Faisal. The line is quiet right now — please try again in a moment."
    # TTS: Edge TTS. ur-PK-SwaraNeural does NOT exist (Edge lists only
    # ur-PK-AsadNeural / ur-PK-UzmaNeural) — that is why the first version
    # returned no audio. Try Aria (female, English) then Uzma (female Urdu).
    audio_b64 = ""
    voice_used = ""
    try:
        import asyncio
        import base64
        import tempfile
        import os
        import edge_tts

        async def _tts(txt: str):
            for v in ("en-US-AriaNeural", "ur-PK-UzmaNeural"):
                comm = edge_tts.Communicate(txt, voice=v)
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp_path = tmp.name
                tmp.close()
                try:
                    await comm.save(tmp_path)
                    with open(tmp_path, "rb") as f:
                        data = f.read()
                    if data:
                        return base64.b64encode(data).decode("ascii"), v
                except Exception:
                    pass
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            return "", ""

        audio_b64, voice_used = asyncio.run(_tts(reply))
    except Exception:
        audio_b64, voice_used = "", ""
    return {"ok": True, "reply": reply, "audio_base64": audio_b64,
            "audio_mime": "audio/mpeg", "voice": voice_used or "none"}

'''

START = "def _call_chat(text: str, history=None) -> dict:"
END_MARKER = "\nclass ThreadedHTTPServer(ThreadingMixIn, HTTPServer):"


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    if "en-US-AriaNeural" in src and "ur-PK-UzmaNeural" in src:
        print("ALREADY FIXED — nothing to do.")
        return 0
    if START not in src or END_MARKER not in src:
        print("ANCHOR MISSING — aborting, file untouched.")
        return 1
    bak = TARGET.with_suffix(".py.bak-20261126-callvoice")
    bak.write_text(src, encoding="utf-8")
    start = src.index(START)
    end = src.index(END_MARKER, start)
    src = src[:start] + NEW_FN + src[end + 1:]
    TARGET.write_text(src, encoding="utf-8")
    print("VOICE FIXED. Backup: " + bak.name + ". New size: " + str(TARGET.stat().st_size) + " bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
