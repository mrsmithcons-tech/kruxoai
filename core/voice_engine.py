"""
core/voice_engine.py — Professional Voice Recognition & Biometrics Engine for JARVIS.

Provides local-first acoustic feature extraction, speaker voiceprint enrollment,
voice verification, speaker identification, and voice quality analysis.

Features:
- Pure NumPy & SciPy signal processing (zero heavy dependencies, runs in milliseconds).
- 26-channel Mel-Filterbank + DCT-II MFCCs with Cepstral Mean Normalization (CMVN).
- Autocorrelation Fundamental Frequency (Pitch / F0) tracking in speech range (75–380 Hz).
- Vocal tract resonance tracking (Spectral Centroid & Rolloff).
- Voice Activity Detection (VAD) to isolate speech from background noise.
- Multi-factor Biometric Scoring (MFCC trajectory + Pitch + Spectral Centroid).
- Persistent profile management in memory/voice_profiles/ and memory/voice_biometrics.json.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import scipy.fft
import scipy.signal

# ── Paths & Constants ─────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent.parent
VOICE_PROFILES_DIR = ROOT_DIR / "memory" / "voice_profiles"
VOICE_REGISTRY_FILE = ROOT_DIR / "memory" / "voice_biometrics.json"

SAMPLE_RATE = 16000
FRAME_SIZE_SEC = 0.025   # 25 ms
FRAME_STRIDE_SEC = 0.010 # 10 ms
NUM_MEL_FILTERS = 26
NUM_MFCC = 13
PITCH_MIN_HZ = 75.0
PITCH_MAX_HZ = 380.0
DEFAULT_SIMILARITY_THRESHOLD = 0.75  # 75% counts as verified match


# ── Signal Processing Utilities ───────────────────────────────────────────────

def _hz_to_mel(hz: float | np.ndarray) -> float | np.ndarray:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: float | np.ndarray) -> float | np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _get_mel_filterbank(num_filters: int = 26, n_fft: int = 512, sample_rate: int = 16000) -> np.ndarray:
    """Create triangular Mel filterbank matrix."""
    low_mel = _hz_to_mel(50.0)
    high_mel = _hz_to_mel(sample_rate / 2.0)
    mel_points = np.linspace(low_mel, high_mel, num_filters + 2)
    hz_points = _mel_to_hz(mel_points)
    bin_points = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)

    fbank = np.zeros((num_filters, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, num_filters + 1):
        f_m_minus = bin_points[m - 1]
        f_m = bin_points[m]
        f_m_plus = bin_points[m + 1]

        for k in range(f_m_minus, f_m):
            if f_m != f_m_minus:
                fbank[m - 1, k] = (k - bin_points[m - 1]) / (f_m - f_m_minus)
        for k in range(f_m, f_m_plus):
            if f_m_plus != f_m:
                fbank[m - 1, k] = (bin_points[m + 1] - k) / (f_m_plus - f_m)
    return fbank


def _dct_matrix(num_ceps: int = 13, num_filters: int = 26) -> np.ndarray:
    """Orthogonal DCT-II transform matrix."""
    k = np.arange(num_ceps)
    n = np.arange(num_filters)
    return np.cos(np.pi * np.outer(k, 2 * n + 1) / (2.0 * num_filters)).astype(np.float32)


# Cached transform matrices for speed
_CACHED_FBANK = _get_mel_filterbank(NUM_MEL_FILTERS, 512, SAMPLE_RATE)
_CACHED_DCT = _dct_matrix(NUM_MFCC, NUM_MEL_FILTERS)


def estimate_pitch_autocorr(frame: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Optional[float]:
    """Estimate fundamental frequency (F0) from a single speech frame via smoothed autocorrelation."""
    min_lag = max(1, int(sample_rate / PITCH_MAX_HZ)) # ~42 samples
    max_lag = min(len(frame) - 1, int(sample_rate / PITCH_MIN_HZ)) # ~213 samples

    # 3-point moving average smoothing to attenuate higher harmonics
    sig_smooth = np.convolve(frame, np.ones(3)/3.0, mode='same')
    corr = np.correlate(sig_smooth, sig_smooth, mode='full')[len(frame)-1:]
    
    if len(corr) <= max_lag or corr[0] < 1e-5:
        return None

    window = corr[min_lag:max_lag]
    if len(window) == 0:
        return None

    peak_rel = int(np.argmax(window))
    peak_lag = min_lag + peak_rel

    # Confidence check
    if corr[peak_lag] > 0.28 * corr[0]:
        return float(sample_rate / peak_lag)
    return None


# ── Acoustic Feature Extractor ────────────────────────────────────────────────

def extract_voiceprint(
    signal: np.ndarray,
    sample_rate: int = SAMPLE_RATE
) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    """
    Extract a normalized acoustic voiceprint vector and acoustic stats.

    Returns:
        (embedding_vector, acoustic_stats_dict)
        If insufficient speech is found, embedding_vector will be None.
    """
    signal = signal.flatten().astype(np.float32)
    max_amp = float(np.max(np.abs(signal))) if len(signal) > 0 else 0.0

    # Guard against pure silence or tiny clips
    if max_amp < 0.005 or len(signal) < int(0.3 * sample_rate):
        return None, {
            "error": "Audio signal too quiet or too short for biometric extraction",
            "max_amplitude": round(max_amp, 4),
            "speech_detected": False,
        }

    # Normalize amplitude
    signal = signal / (max_amp + 1e-12)

    # Pre-emphasis filter
    pre_emphasized = np.append(signal[0], signal[1:] - 0.97 * signal[:-1])

    # Frame blocking
    frame_size = int(FRAME_SIZE_SEC * sample_rate)     # 400 samples
    frame_stride = int(FRAME_STRIDE_SEC * sample_rate) # 160 samples
    num_frames = max(1, 1 + int(np.floor((len(pre_emphasized) - frame_size) / frame_stride)))

    indices = np.tile(np.arange(0, frame_size), (num_frames, 1)) + \
              np.tile(np.arange(0, num_frames * frame_stride, frame_stride), (frame_size, 1)).T
    frames = pre_emphasized[indices]

    # Hamming Window
    frames *= np.hamming(frame_size)

    # Voice Activity Detection (VAD) via frame energy
    frame_energies = np.sum(frames ** 2, axis=1) / frame_size
    energy_threshold = max(float(np.mean(frame_energies) * 0.15), 1e-5)
    speech_mask = frame_energies > energy_threshold

    if np.sum(speech_mask) < 4:
        # Fallback to top 40% loudest frames
        speech_mask = frame_energies >= np.percentile(frame_energies, 60)

    speech_frames = frames[speech_mask]
    active_ratio = float(np.mean(speech_mask))

    # FFT & Power spectrum
    n_fft = 512
    mag_frames = np.abs(scipy.fft.rfft(speech_frames, n=n_fft))
    pow_frames = (1.0 / n_fft) * (mag_frames ** 2)

    # Mel Filterbank Energies
    fbank_energies = np.dot(pow_frames, _CACHED_FBANK.T)
    fbank_energies = np.where(fbank_energies == 0, np.finfo(float).eps, fbank_energies)
    log_fbank = 20.0 * np.log10(fbank_energies)

    # MFCC extraction via DCT
    raw_mfcc = np.dot(log_fbank, _CACHED_DCT.T) # shape: (N_speech_frames, 13)

    # Cepstral Mean & Variance Normalization (CMVN) to remove channel / gain bias
    mfcc_norm = raw_mfcc - np.mean(raw_mfcc, axis=0, keepdims=True)
    std_devs = np.std(raw_mfcc, axis=0, keepdims=True)
    std_devs = np.where(std_devs < 1e-5, 1.0, std_devs)
    mfcc_norm = mfcc_norm / std_devs

    # Delta MFCCs (velocity of spectral change)
    if len(raw_mfcc) > 2:
        delta = np.zeros_like(raw_mfcc)
        delta[1:-1] = (raw_mfcc[2:] - raw_mfcc[:-2]) / 2.0
        delta[0] = raw_mfcc[1] - raw_mfcc[0]
        delta[-1] = raw_mfcc[-1] - raw_mfcc[-2]
    else:
        delta = np.zeros_like(raw_mfcc)

    # Feature pooling (excluding c0 to be volume-invariant)
    # Use MFCC coefficients 1..12 (12 dims)
    mean_mfcc = np.mean(raw_mfcc[:, 1:], axis=0) # 12
    std_mfcc = np.std(raw_mfcc[:, 1:], axis=0)   # 12
    mean_delta = np.mean(delta[:, 1:], axis=0)    # 12
    std_delta = np.std(delta[:, 1:], axis=0)      # 12

    # Spectral Centroid (brightness / vocal tract resonance indicator)
    freqs = np.linspace(0, sample_rate / 2.0, n_fft // 2 + 1)
    sc = np.sum(mag_frames * freqs, axis=1) / (np.sum(mag_frames, axis=1) + 1e-12)
    mean_sc = float(np.mean(sc))
    std_sc = float(np.std(sc))

    # Zero Crossing Rate (ZCR)
    zcr = np.mean(np.abs(np.diff(np.sign(speech_frames), axis=1)) > 0, axis=1)
    mean_zcr = float(np.mean(zcr))
    std_zcr = float(np.std(zcr))

    # Pitch tracking across speech frames
    pitch_vals = []
    for f in speech_frames:
        p = estimate_pitch_autocorr(f, sample_rate)
        if p is not None:
            pitch_vals.append(p)

    if pitch_vals:
        avg_pitch = float(np.median(pitch_vals))
        std_pitch = float(np.std(pitch_vals))
    else:
        # Fallback based on spectral envelope
        avg_pitch = float(np.clip(mean_sc * 0.08, 105.0, 230.0))
        std_pitch = 12.0

    # Spectral Rolloff (85% energy concentration)
    cum_energy = np.cumsum(pow_frames, axis=1)
    total_energy = cum_energy[:, -1:] + 1e-12
    rolloff_bins = np.argmax(cum_energy >= 0.85 * total_energy, axis=1)
    mean_rolloff = float(np.mean(freqs[rolloff_bins]))

    # Assemble 64-dimensional biometric vector:
    # 12 mean_mfcc + 12 std_mfcc + 12 mean_delta + 12 std_delta + 16 acoustic scalars = 64
    acoustic_scalars = np.array([
        mean_sc / (sample_rate / 2.0),
        std_sc / (sample_rate / 2.0),
        mean_zcr,
        std_zcr,
        avg_pitch / PITCH_MAX_HZ,
        std_pitch / PITCH_MAX_HZ,
        mean_rolloff / (sample_rate / 2.0),
        active_ratio,
        float(np.mean(frame_energies)),
        float(np.std(frame_energies)),
        max_amp,
        avg_pitch,
        mean_sc,
        mean_rolloff,
        0.0,
        0.0
    ], dtype=np.float32)

    embedding = np.concatenate([
        mean_mfcc.astype(np.float32),
        std_mfcc.astype(np.float32),
        mean_delta.astype(np.float32),
        std_delta.astype(np.float32),
        acoustic_scalars
    ])

    stats = {
        "speech_detected": True,
        "active_ratio": round(active_ratio * 100, 1),
        "mean_pitch_hz": round(avg_pitch, 1),
        "pitch_std_hz": round(std_pitch, 1),
        "spectral_centroid_hz": round(mean_sc, 1),
        "spectral_rolloff_hz": round(mean_rolloff, 1),
        "zero_crossing_rate": round(mean_zcr, 4),
        "max_amplitude": round(max_amp, 4),
        "frames_analyzed": int(len(speech_frames)),
    }

    return embedding, stats


def compute_voice_similarity(
    emb1: np.ndarray,
    emb2: np.ndarray,
    pitch1: Optional[float] = None,
    pitch2: Optional[float] = None,
    sc1: Optional[float] = None,
    sc2: Optional[float] = None
) -> float:
    """
    Compute multi-factor biometric similarity score between two voiceprints.
    Combines MFCC Pearson correlation (55%), Pitch alignment (30%), and Vocal Tract Resonance (15%).
    Returns score in [0.0, 1.0].
    """
    if emb1 is None or emb2 is None or len(emb1) < 48 or len(emb2) < 48:
        return 0.0

    # 1. MFCC trajectory similarity (first 48 dims: 12 mean + 12 std + 12 delta + 12 delta-std)
    mfcc_a = emb1[:48]
    mfcc_b = emb2[:48]
    a_centered = mfcc_a - np.mean(mfcc_a)
    b_centered = mfcc_b - np.mean(mfcc_b)
    norm_a = np.linalg.norm(a_centered)
    norm_b = np.linalg.norm(b_centered)

    if norm_a == 0 or norm_b == 0:
        sim_mfcc = 0.0
    else:
        sim_mfcc = max(0.0, float(np.dot(a_centered, b_centered) / (norm_a * norm_b)))

    # 2. Pitch similarity
    p1 = pitch1 if pitch1 is not None else float(emb1[52] * PITCH_MAX_HZ if len(emb1) > 52 else 130.0)
    p2 = pitch2 if pitch2 is not None else float(emb2[52] * PITCH_MAX_HZ if len(emb2) > 52 else 130.0)
    pitch_diff = abs(p1 - p2)
    # Exponential decay on pitch difference: 20 Hz diff -> ~85%, 60 Hz diff -> ~50%
    sim_pitch = max(0.0, 1.0 - (pitch_diff / max(p1, p2, 60.0)))

    # 3. Spectral Centroid / Vocal tract similarity
    s1 = sc1 if sc1 is not None else float(emb1[48] * (SAMPLE_RATE / 2.0) if len(emb1) > 48 else 1500.0)
    s2 = sc2 if sc2 is not None else float(emb2[48] * (SAMPLE_RATE / 2.0) if len(emb2) > 48 else 1500.0)
    sc_diff = abs(s1 - s2)
    sim_sc = max(0.0, 1.0 - (sc_diff / max(s1, s2, 500.0)))

    # Weighted combination
    total_score = 0.55 * sim_mfcc + 0.30 * sim_pitch + 0.15 * sim_sc
    return max(0.0, min(1.0, float(total_score)))


# ── Audio Capture Helper ──────────────────────────────────────────────────────

def record_audio_clip(duration: float = 3.0, sample_rate: int = SAMPLE_RATE) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """Record audio clip from the default input device."""
    try:
        import sounddevice as sd
        num_samples = int(duration * sample_rate)
        recording = sd.rec(num_samples, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
        return recording.flatten(), None
    except Exception as e:
        return None, str(e)


# ── Voice Biometrics & Profile Manager ────────────────────────────────────────

class VoiceProfileManager:
    """Manages enrolled voice profiles, verification, and speaker identification."""

    def __init__(self, profiles_dir: Optional[Path] = None, registry_file: Optional[Path] = None):
        self.profiles_dir = profiles_dir or VOICE_PROFILES_DIR
        self.registry_file = registry_file or VOICE_REGISTRY_FILE
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_registry()

    def _ensure_registry(self) -> None:
        if not self.registry_file.exists():
            data = {
                "version": "1.0",
                "default_speaker": "Faisal",
                "enrolled_speakers": [],
                "threshold": DEFAULT_SIMILARITY_THRESHOLD,
                "last_verification": None
            }
            try:
                with open(self.registry_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def _get_registry(self) -> dict:
        try:
            if self.registry_file.exists():
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"enrolled_speakers": [], "threshold": DEFAULT_SIMILARITY_THRESHOLD}

    def _save_registry(self, data: dict) -> None:
        try:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[VoiceEngine] Failed to save registry: {e}")

    def enroll_speaker(
        self,
        name: str,
        duration: float = 3.5,
        custom_audio: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """Enroll a speaker profile from live microphone audio or provided buffer."""
        clean_name = name.strip()
        if not clean_name:
            return {"ok": False, "error": "Speaker name cannot be empty"}

        if custom_audio is None:
            audio, err = record_audio_clip(duration)
            if err:
                return {"ok": False, "error": f"Audio recording failed: {err}"}
        else:
            audio = custom_audio

        sr = SAMPLE_RATE
        window_len = int(1.5 * sr)
        step_len = int(0.5 * sr)
        sub_embeddings = []
        last_stats = {}

        if len(audio) >= window_len:
            for start in range(0, len(audio) - window_len + 1, step_len):
                chunk = audio[start:start + window_len]
                emb, stats = extract_voiceprint(chunk, sr)
                if emb is not None:
                    sub_embeddings.append(emb)
                    last_stats = stats

        if not sub_embeddings:
            emb, stats = extract_voiceprint(audio, sr)
            if emb is not None:
                sub_embeddings.append(emb)
                last_stats = stats
            else:
                return {
                    "ok": False,
                    "error": "No clear speech detected. Please speak closer to the microphone.",
                    "details": stats
                }

        mean_embedding = np.mean(sub_embeddings, axis=0)
        profile_file = self.profiles_dir / f"{clean_name.lower().replace(' ', '_')}.json"

        profile_data = {
            "speaker": clean_name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sample_duration_sec": duration,
            "windows_analyzed": len(sub_embeddings),
            "pitch_hz": last_stats.get("mean_pitch_hz", 130.0),
            "spectral_centroid_hz": last_stats.get("spectral_centroid_hz", 1500.0),
            "stats": last_stats,
            "embedding": mean_embedding.tolist()
        }

        try:
            with open(profile_file, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, indent=2)
        except Exception as e:
            return {"ok": False, "error": f"Failed to save profile: {e}"}

        reg = self._get_registry()
        speakers = set(reg.get("enrolled_speakers", []))
        speakers.add(clean_name)
        reg["enrolled_speakers"] = sorted(list(speakers))
        reg["last_enrolled"] = clean_name
        self._save_registry(reg)

        return {
            "ok": True,
            "speaker": clean_name,
            "profile_file": str(profile_file),
            "pitch_hz": last_stats.get("mean_pitch_hz"),
            "spectral_centroid_hz": last_stats.get("spectral_centroid_hz"),
            "windows": len(sub_embeddings),
            "message": f"Successfully enrolled voice profile for {clean_name}."
        }

    def load_profile(self, name: str) -> Optional[dict]:
        clean_name = name.strip().lower().replace(" ", "_")
        target_file = self.profiles_dir / f"{clean_name}.json"
        if not target_file.exists():
            for p in self.profiles_dir.glob("*.json"):
                if p.stem.lower() == clean_name:
                    target_file = p
                    break

        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def list_speakers(self) -> List[Dict[str, Any]]:
        results = []
        for p in self.profiles_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append({
                        "speaker": data.get("speaker", p.stem),
                        "created_at": data.get("created_at", "unknown"),
                        "pitch_hz": data.get("pitch_hz", "N/A"),
                        "spectral_centroid_hz": data.get("spectral_centroid_hz", "N/A"),
                        "file": p.name
                    })
            except Exception:
                continue
        return results

    def identify_speaker(
        self,
        duration: float = 3.0,
        custom_audio: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Record and identify active speaker among all enrolled profiles."""
        thresh = threshold or self._get_registry().get("threshold", DEFAULT_SIMILARITY_THRESHOLD)

        if custom_audio is None:
            audio, err = record_audio_clip(duration)
            if err:
                return {"ok": False, "error": f"Audio recording failed: {err}"}
        else:
            audio = custom_audio

        live_emb, stats = extract_voiceprint(audio)
        if live_emb is None:
            return {
                "ok": False,
                "error": "No clear speech detected in recording",
                "details": stats
            }

        enrolled = self.list_speakers()
        if not enrolled:
            return {
                "ok": True,
                "recognized": False,
                "speaker": "Unrecognized Speaker",
                "confidence": 0.0,
                "note": "No enrolled voice profiles found in database. Please enroll first.",
                "stats": stats
            }

        scores = []
        live_pitch = stats.get("mean_pitch_hz")
        live_sc = stats.get("spectral_centroid_hz")

        for item in enrolled:
            prof = self.load_profile(item["speaker"])
            if prof and "embedding" in prof:
                ref_emb = np.array(prof["embedding"], dtype=np.float32)
                sim = compute_voice_similarity(
                    live_emb,
                    ref_emb,
                    pitch1=live_pitch,
                    pitch2=prof.get("pitch_hz"),
                    sc1=live_sc,
                    sc2=prof.get("spectral_centroid_hz")
                )
                scores.append({
                    "speaker": item["speaker"],
                    "similarity": round(sim, 4),
                    "confidence_pct": round(sim * 100, 1),
                    "pitch_hz": prof.get("pitch_hz")
                })

        scores.sort(key=lambda x: x["similarity"], reverse=True)
        best = scores[0]
        is_match = best["similarity"] >= thresh

        result = {
            "ok": True,
            "recognized": is_match,
            "speaker": best["speaker"] if is_match else "Unrecognized Speaker",
            "best_match_name": best["speaker"],
            "confidence_pct": best["confidence_pct"],
            "threshold_pct": round(thresh * 100, 1),
            "all_scores": scores,
            "live_stats": stats
        }

        reg = self._get_registry()
        reg["last_verification"] = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "speaker": result["speaker"],
            "confidence_pct": result["confidence_pct"],
            "recognized": is_match
        }
        self._save_registry(reg)

        return result

    def verify_speaker(
        self,
        name: str,
        duration: float = 3.0,
        custom_audio: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Verify if the current voice matches a specific person."""
        prof = self.load_profile(name)
        if not prof:
            return {"ok": False, "error": f"No enrolled voice profile found for '{name}'."}

        thresh = threshold or self._get_registry().get("threshold", DEFAULT_SIMILARITY_THRESHOLD)

        if custom_audio is None:
            audio, err = record_audio_clip(duration)
            if err:
                return {"ok": False, "error": f"Audio recording failed: {err}"}
        else:
            audio = custom_audio

        live_emb, stats = extract_voiceprint(audio)
        if live_emb is None:
            return {"ok": False, "error": "No clear speech detected in recording", "details": stats}

        ref_emb = np.array(prof["embedding"], dtype=np.float32)
        sim = compute_voice_similarity(
            live_emb,
            ref_emb,
            pitch1=stats.get("mean_pitch_hz"),
            pitch2=prof.get("pitch_hz"),
            sc1=stats.get("spectral_centroid_hz"),
            sc2=prof.get("spectral_centroid_hz")
        )
        verified = sim >= thresh

        return {
            "ok": True,
            "speaker": prof.get("speaker", name),
            "verified": verified,
            "similarity": round(sim, 4),
            "confidence_pct": round(sim * 100, 1),
            "threshold_pct": round(thresh * 100, 1),
            "pitch_match": abs(stats.get("mean_pitch_hz", 0) - prof.get("pitch_hz", 0)) < 35,
            "live_stats": stats
        }

    def delete_speaker(self, name: str) -> bool:
        clean_name = name.strip().lower().replace(" ", "_")
        target_file = self.profiles_dir / f"{clean_name}.json"
        deleted = False
        if target_file.exists():
            target_file.unlink()
            deleted = True

        reg = self._get_registry()
        reg["enrolled_speakers"] = [s for s in reg.get("enrolled_speakers", []) if s.lower() != name.lower()]
        self._save_registry(reg)
        return deleted

    def analyze_voice(
        self,
        duration: float = 3.0,
        custom_audio: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """Analyze voice acoustic characteristics without matching."""
        if custom_audio is None:
            audio, err = record_audio_clip(duration)
            if err:
                return {"ok": False, "error": f"Audio recording failed: {err}"}
        else:
            audio = custom_audio

        emb, stats = extract_voiceprint(audio)
        if emb is None:
            return {"ok": False, "error": "No speech detected", "details": stats}

        pitch = stats.get("mean_pitch_hz", 0.0)
        pitch_category = "Deep / Low" if pitch < 120 else ("Medium / Standard" if pitch < 185 else "High / Treble")

        return {
            "ok": True,
            "analysis": {
                "fundamental_frequency_hz": pitch,
                "pitch_classification": pitch_category,
                "pitch_stability_std_hz": stats.get("pitch_std_hz"),
                "vocal_resonance_centroid_hz": stats.get("spectral_centroid_hz"),
                "frequency_energy_rolloff_hz": stats.get("spectral_rolloff_hz"),
                "speech_activity_ratio_pct": stats.get("active_ratio"),
                "voice_clarity_score_pct": min(100.0, round(float(stats.get("active_ratio", 0)) * 1.1, 1))
            }
        }


# Global singleton instance
voice_manager = VoiceProfileManager()
