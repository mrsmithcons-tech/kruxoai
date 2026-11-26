"""Debug Edge TTS on the laptop: full traceback to a file."""
import asyncio
import traceback
from pathlib import Path

OUT = Path(__file__).resolve().parent / "tts_debug_out.txt"
try:
    import edge_tts

    async def _run():
        comm = edge_tts.Communicate("Hello Faisal, this is a voice test.", voice="ur-PK-SwaraNeural")
        await comm.save(str(Path(__file__).resolve().parent / "tts_test.mp3"))

    asyncio.run(_run())
    p = Path(__file__).resolve().parent / "tts_test.mp3"
    OUT.write_text("TTS OK, mp3 bytes: " + str(p.stat().st_size if p.exists() else 0) + "\n", encoding="utf-8")
except Exception:
    OUT.write_text("TTS FAILED:\n" + traceback.format_exc(), encoding="utf-8")
