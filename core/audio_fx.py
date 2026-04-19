"""
音声エフェクト・変換ユーティリティ

EmotionalTTSEngine が使用するオーディオ処理関数群。
numpy / librosa / soundfile が利用可能な場合にのみ実効的に動作し、
不在時はノーオペレーションで元の AudioChunk をそのまま返す。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# ─── Optional heavy imports (graceful degradation) ───────────

_HAS_NUMPY = False
_HAS_SOUNDFILE = False
_HAS_SOUNDDEVICE = False
_HAS_LIBROSA = False

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import soundfile as sf

    _HAS_SOUNDFILE = True
except ImportError:
    sf = None  # type: ignore[assignment]

try:
    import sounddevice as sd

    _HAS_SOUNDDEVICE = True
except ImportError:
    sd = None  # type: ignore[assignment]

try:
    import librosa

    _HAS_LIBROSA = True
except ImportError:
    librosa = None  # type: ignore[assignment]


# ─── Data container ──────────────────────────────────────────


@dataclass(frozen=True)
class AudioChunk:
    """Immutable container for an audio segment."""

    data: Any  # np.ndarray — typed as Any for graceful degradation
    sample_rate: int


# ─── Transform functions ─────────────────────────────────────


def pitch_shift(chunk: AudioChunk, semitones: float) -> AudioChunk:
    """Shift pitch by the given number of semitones using librosa."""
    if not _HAS_LIBROSA or not _HAS_NUMPY or abs(semitones) < 0.01:
        return chunk
    shifted = librosa.effects.pitch_shift(
        y=chunk.data.astype(np.float32),
        sr=chunk.sample_rate,
        n_steps=semitones,
    )
    return AudioChunk(data=shifted, sample_rate=chunk.sample_rate)


def time_stretch(chunk: AudioChunk, rate: float) -> AudioChunk:
    """Time-stretch audio. rate > 1.0 = faster, < 1.0 = slower."""
    if not _HAS_LIBROSA or not _HAS_NUMPY or abs(rate - 1.0) < 0.01:
        return chunk
    clamped_rate = max(0.5, min(2.0, rate))
    stretched = librosa.effects.time_stretch(
        y=chunk.data.astype(np.float32),
        rate=clamped_rate,
    )
    return AudioChunk(data=stretched, sample_rate=chunk.sample_rate)


def apply_volume(chunk: AudioChunk, volume: float) -> AudioChunk:
    """Scale amplitude by volume factor."""
    if not _HAS_NUMPY or abs(volume - 1.0) < 0.01:
        return chunk
    clamped = max(0.1, min(2.0, volume))
    scaled = chunk.data * clamped
    # Prevent clipping
    peak = np.max(np.abs(scaled))
    if peak > 1.0:
        scaled = scaled / peak
    return AudioChunk(data=scaled, sample_rate=chunk.sample_rate)


def apply_breathiness(chunk: AudioChunk, amount: float) -> AudioChunk:
    """Add a soft noise layer to simulate breathiness."""
    if not _HAS_NUMPY or amount < 0.01:
        return chunk
    clamped = min(0.3, amount)
    rng = np.random.default_rng(42)
    noise = rng.normal(0, clamped * 0.08, size=chunk.data.shape).astype(
        chunk.data.dtype
    )
    mixed = chunk.data + noise
    peak = np.max(np.abs(mixed))
    if peak > 1.0:
        mixed = mixed / peak
    return AudioChunk(data=mixed, sample_rate=chunk.sample_rate)


def apply_reverb(chunk: AudioChunk, mix: float) -> AudioChunk:
    """Simple convolution reverb using a synthetic impulse response."""
    if not _HAS_NUMPY or mix < 0.01:
        return chunk
    clamped = min(0.4, mix)
    sr = chunk.sample_rate
    # Synthetic impulse: exponential decay over 0.3s
    ir_len = int(sr * 0.3)
    t = np.arange(ir_len, dtype=np.float32) / sr
    impulse = np.exp(-6.0 * t) * 0.3
    impulse[0] = 1.0

    data_f32 = chunk.data.astype(np.float32)
    convolved = np.convolve(data_f32, impulse, mode="full")[: len(data_f32)]
    # Normalize
    peak = np.max(np.abs(convolved))
    if peak > 0:
        convolved = convolved / peak
    blended = data_f32 * (1.0 - clamped) + convolved * clamped
    peak2 = np.max(np.abs(blended))
    if peak2 > 1.0:
        blended = blended / peak2
    return AudioChunk(data=blended, sample_rate=chunk.sample_rate)


def apply_whisper_effect(chunk: AudioChunk) -> AudioChunk:
    """Create a whisper-like effect: reduced volume + breathiness."""
    if not _HAS_NUMPY:
        return chunk
    result = apply_volume(chunk, 0.55)
    result = apply_breathiness(result, 0.25)
    return result


def generate_silence(duration_sec: float, sample_rate: int) -> AudioChunk:
    """Generate a silent audio chunk for pauses."""
    if not _HAS_NUMPY:
        return AudioChunk(data=None, sample_rate=sample_rate)
    n_samples = int(duration_sec * sample_rate)
    return AudioChunk(
        data=np.zeros(n_samples, dtype=np.float32), sample_rate=sample_rate
    )


def concatenate_chunks(chunks: Sequence[AudioChunk]) -> AudioChunk | None:
    """Concatenate multiple AudioChunks into one."""
    if not _HAS_NUMPY or not chunks:
        return None
    valid = [c for c in chunks if c.data is not None and len(c.data) > 0]
    if not valid:
        return None
    sr = valid[0].sample_rate
    arrays = [c.data.astype(np.float32) for c in valid]
    return AudioChunk(data=np.concatenate(arrays), sample_rate=sr)


def play_chunk(chunk: AudioChunk, lock: Any = None) -> None:
    """Play an AudioChunk through sounddevice (blocking).

    Args:
        chunk: The audio data to play.
        lock: Optional threading.Lock for exclusive playback.
    """
    if not _HAS_SOUNDDEVICE or chunk.data is None or len(chunk.data) == 0:
        return
    try:
        if lock is not None:
            lock.acquire()
        sd.play(chunk.data, samplerate=chunk.sample_rate)
        sd.wait()
    except Exception as exc:
        logger.warning("sounddevice 再生エラー: %s", exc)
    finally:
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass


def can_post_process() -> bool:
    """Return True if all audio post-processing dependencies are available."""
    return _HAS_NUMPY and _HAS_SOUNDFILE and _HAS_SOUNDDEVICE and _HAS_LIBROSA


def read_audio_file(path: str) -> AudioChunk | None:
    """Read an audio file and return an AudioChunk."""
    if not _HAS_SOUNDFILE or not _HAS_NUMPY:
        return None
    try:
        data, sr = sf.read(path)
        return AudioChunk(data=data.astype(np.float32), sample_rate=sr)
    except Exception as exc:
        logger.warning("音声ファイル読み込みエラー: %s", exc)
        return None


def stop_playback() -> None:
    """Stop any active sounddevice playback."""
    if _HAS_SOUNDDEVICE:
        try:
            sd.stop()
        except Exception:
            pass
