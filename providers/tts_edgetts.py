"""
providers/tts_edgetts.py — Microsoft Edge Neural TTS Provider for KruxoAI.

High-definition natural neural speech synthesis:
- Free & unlimited (no API key or subscription needed).
- Realistic neural voices (Aria, Uzma, Jenny, Guy).
- Instant in-memory streaming at 24,000 Hz 16-bit mono PCM.
- Automatic bilingual routing (English <-> Urdu).
"""
from __future__ import annotations

import asyncio
import io
import re
from importlib.util import find_spec
from typing import AsyncIterator, Optional

from . import audio
from .base import Field

DEFAULT_VOICE = "en-US-AriaNeural"

VOICES = (
    ("en-US-AriaNeural", "Zara (Expressive & Warm - English US)"),
    ("ur-PK-UzmaNeural", "Zara Urdu (Natural Female - Urdu PK)"),
    ("en-US-JennyNeural", "Zara Casual (Conversational - English US)"),
    ("en-GB-SoniaNeural", "Zara British (Refined - English UK)"),
    ("en-US-GuyNeural", "Guy (Male - English US)"),
)

VOICE_IDS = tuple(v[0] for v in VOICES)


class EdgeTTSProvider:
    """Microsoft Edge Neural TTS streaming provider."""

    def __init__(self, cfg: Optional[dict] = None):
        cfg = cfg or {}
        self.default_voice = cfg.get("voice_id") or DEFAULT_VOICE
        self.rate = cfg.get("rate", "+0%")
        self.pitch = cfg.get("pitch", "+0Hz")

    def _select_voice(self, language: str = "") -> str:
        lang = (language or "").lower()
        if lang in ("ur", "urdu", "pk", "pa", "hin", "hi"):
            return "ur-PK-UzmaNeural"
        return self.default_voice

    async def speak(self, text: str, **kwargs) -> AsyncIterator[bytes]:
        """Synthesize text and yield raw 24kHz 16-bit mono PCM chunks."""
        text = (text or "").strip()
        if not text:
            return

        import edge_tts
        import soundfile as sf

        language = kwargs.get("language", "")
        voice = self._select_voice(language)

        comm = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=self.rate,
            pitch=self.pitch,
        )

        mp3_buf = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                mp3_buf.extend(chunk["data"])

        if not mp3_buf:
            return

        # Decode MP3 to 24kHz 16-bit mono PCM in memory
        try:
            data, sr = sf.read(io.BytesIO(mp3_buf), dtype="int16")
        except Exception:
            return

        # Resample if edge-tts returned a different rate (rare, default is 24kHz)
        if sr != audio.SPEAKER_RATE:
            try:
                from scipy import signal
                num_samples = int(len(data) * float(audio.SPEAKER_RATE) / sr)
                data = signal.resample(data.astype("float32"), num_samples).clip(-32768, 32767).astype("int16")
            except Exception:
                pass

        raw_pcm = data.tobytes()

        # Stream in ~100ms frames (2400 samples * 2 bytes = 4800 bytes)
        chunk_size = 4800
        for i in range(0, len(raw_pcm), chunk_size):
            yield raw_pcm[i : i + chunk_size]
            await asyncio.sleep(0.01)


def _make(cfg: dict) -> EdgeTTSProvider:
    return EdgeTTSProvider(cfg)


PROVIDER = {
    "id": "edgetts",
    "kind": "tts",
    "label": "Microsoft Edge Neural (Zara)",
    "hint": "Free natural neural voices — no API key or model download needed",
    "requires": ("edge_tts", "soundfile"),
    "catalog": (
        {"id": "edgetts", "label": "Edge Neural (Zara)",
         "note": "cloud · free & realistic", "local": False,
         "values": {}},
    ),
    "needs": (
        Field("voice_id", "Voice", kind="choice", choices=VOICE_IDS,
              default=DEFAULT_VOICE, required=False,
              hint="en-US-AriaNeural is Zara's primary realistic voice"),
    ),
    "caps": {"audio_out": True},
    "factory": _make,
}


def available() -> bool:
    return find_spec("edge_tts") is not None and find_spec("soundfile") is not None
