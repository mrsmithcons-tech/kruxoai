"""core/audio_lock.py — Global Re-entrant Audio Serialization Lock for PortAudio / sounddevice.

Prevents concurrent audio stream capture, playback, and device queries across background
threads (RoomSentry, VoiceEmotion, TTS, Gemini Live) from corrupting the PortAudio heap.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

_AUDIO_LOCK = threading.RLock()


@contextmanager
def audio_lock(timeout: float = 10.0):
    """Context manager for serializing native PortAudio/sounddevice operations.

    If lock cannot be acquired within timeout, yields False rather than raising,
    allowing the caller to skip or retry safely without deadlocks.
    """
    acquired = _AUDIO_LOCK.acquire(timeout=timeout)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                _AUDIO_LOCK.release()
            except RuntimeError:
                pass


def is_audio_locked() -> bool:
    """Check if any thread (including current thread) currently holds the audio lock."""
    if hasattr(_AUDIO_LOCK, "_is_owned") and _AUDIO_LOCK._is_owned():
        return True
    if not _AUDIO_LOCK.acquire(blocking=False):
        return True
    try:
        _AUDIO_LOCK.release()
    except RuntimeError:
        pass
    return False
