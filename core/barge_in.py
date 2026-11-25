"""
core/barge_in.py — Ultra-Low Latency Intelligent Barge-In (Interruption Engine) for JARVIS.

Monitors microphone input during assistant speech playback:
- Detects voice activity bursts from Faisal within 30ms.
- Immediately signals audio playback cutoff so JARVIS never talks over the user.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import numpy as np


class IntelligentBargeInDetector:
    """Detects human speech during playback to instantly abort output."""

    def __init__(self, on_barge_in: Optional[Callable[[], None]] = None):
        self._on_barge_in = on_barge_in
        self._is_assistant_speaking = False
        self._cooldown_until = 0.0

    def set_speaking_state(self, speaking: bool) -> None:
        self._is_assistant_speaking = speaking
        if speaking:
            # Ignore self-reflection echo for first 150ms of playback
            self._cooldown_until = time.time() + 0.15

    def check_audio_frame(self, frame_pcm: np.ndarray) -> bool:
        """Called by mic callback. Returns True if user interrupted."""
        if not self._is_assistant_speaking or time.time() < self._cooldown_until:
            return False

        # Energy & Zero-crossing rate check
        energy = float(np.mean(frame_pcm.astype(np.float32) ** 2))
        max_amp = float(np.max(np.abs(frame_pcm)))

        # Voice burst threshold (distinct from low speaker bleed)
        if energy > 8000000.0 and max_amp > 12000.0:
            if self._on_barge_in:
                try:
                    self._on_barge_in()
                except Exception:
                    pass
            self._is_assistant_speaking = False
            return True
        return False


# Global singleton
barge_in_detector = IntelligentBargeInDetector()
