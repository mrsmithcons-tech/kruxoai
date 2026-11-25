"""
core/offline_tts.py — Zero-Latency Offline Speech Synthesis Fallback for JARVIS.

Uses Windows Native SAPI (SpVoice) to guarantee speech output even when:
- Internet drops or packet loss occurs.
- Gemini Live or external speech APIs time out.
- High-priority system and security warnings must be spoken instantly without network lag.
"""
from __future__ import annotations

import sys
import threading
from typing import Optional


class OfflineSpeechEngine:
    """Zero-latency offline TTS using Windows native speech API."""

    def __init__(self, voice_gender: str = "male"):
        self.voice_gender = voice_gender
        self._voice_idx = 0 if voice_gender.lower() == "male" else 1

    def speak(self, text: str, non_blocking: bool = True) -> bool:
        """Speak phrase using native Windows SAPI."""
        clean_text = text.strip()
        if not clean_text:
            return False

        if non_blocking:
            t = threading.Thread(target=self._speak_sync, args=(clean_text,), daemon=True, name="OfflineTTSThread")
            t.start()
            return True
        else:
            return self._speak_sync(clean_text)

    def _speak_sync(self, text: str) -> bool:
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            voices = speaker.GetVoices()
            if voices.Count > self._voice_idx:
                speaker.Voice = voices.Item(self._voice_idx)
            speaker.Rate = 1 # Slightly brisk, natural pace
            # SVSFlagsAsync = 1
            speaker.Speak(text)
            return True
        except Exception as e:
            # Fallback to PowerShell speech synthesis if COM dispatch fails
            try:
                import subprocess
                ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text[:200]}')"
                subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_cmd], timeout=5)
                return True
            except Exception:
                return False


# Global offline TTS fallback instance
offline_tts = OfflineSpeechEngine()
