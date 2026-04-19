"""
感情豊かな音声合成エンジン

macOS say コマンドをベースに、numpy/librosa/sounddevice による
音声後処理で感情表現を実現する3層アーキテクチャ。

Layer 1: Enhanced macOS say — 感情別プロソディ制御
Layer 2: Audio post-processing — ピッチ・速度・音量・エフェクト (core/audio_fx)
Layer 3: Neural TTS stub — 将来の VITS/XTTS 用インターフェース
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable

from core.audio_fx import (
    AudioChunk,
    apply_breathiness,
    apply_reverb,
    apply_volume,
    apply_whisper_effect,
    can_post_process,
    pitch_shift,
    play_chunk,
    read_audio_file,
    stop_playback,
)

logger = logging.getLogger(__name__)

IS_MAC = __import__("platform").system() == "Darwin"

# ─── Emotion parameter definitions ──────────────────────────

EMOTION_PARAMS: dict[str, dict[str, float]] = {
    "happy": {
        "rate_offset": 15,
        "pitch_semitones": 1.5,
        "volume": 1.1,
        "pause_factor": 0.8,
        "breathiness": 0.0,
        "reverb_mix": 0.0,
    },
    "sad": {
        "rate_offset": -25,
        "pitch_semitones": -1.0,
        "volume": 0.85,
        "pause_factor": 1.4,
        "breathiness": 0.15,
        "reverb_mix": 0.1,
    },
    "excited": {
        "rate_offset": 25,
        "pitch_semitones": 2.0,
        "volume": 1.2,
        "pause_factor": 0.6,
        "breathiness": 0.0,
        "reverb_mix": 0.0,
    },
    "calm": {
        "rate_offset": -10,
        "pitch_semitones": 0.0,
        "volume": 0.95,
        "pause_factor": 1.1,
        "breathiness": 0.05,
        "reverb_mix": 0.05,
    },
    "angry": {
        "rate_offset": 10,
        "pitch_semitones": 0.5,
        "volume": 1.3,
        "pause_factor": 0.9,
        "breathiness": 0.0,
        "reverb_mix": 0.0,
    },
    "loving": {
        "rate_offset": -15,
        "pitch_semitones": 0.5,
        "volume": 0.9,
        "pause_factor": 1.2,
        "breathiness": 0.2,
        "reverb_mix": 0.08,
    },
}

# Mapping from EmotionState dominant fields to emotion keys
_DOMINANT_TO_EMOTION: dict[str, str] = {
    "happiness": "happy",
    "curiosity": "excited",
    "affection": "loving",
    "energy": "excited",
}

# ─── Sentence splitter / cleaner (shared logic with tts.py) ──

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？\n])")

# チャット表示と TTS の内容を一致させるため、
# 絵文字と Markdown 記号のみ除去（英単語・記号類は残す）
_MARKDOWN_RE = re.compile(r"[*_`~#>\[\]]")
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF"
    r"\U00002600-\U000027BF"
    r"\U0001F000-\U0001F02F"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA70-\U0001FAFF]"
)


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in parts if s.strip()]


def _clean_for_tts(text: str) -> str:
    """TTS 前の最小限クリーニング。チャット表示とほぼ一致させる。"""
    cleaned = _EMOJI_RE.sub("", text)
    cleaned = _MARKDOWN_RE.sub("", cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


# ─── Layer 1: macOS say helpers ──────────────────────────────


def _say_to_file(text: str, voice: str, rate: int, output_path: str) -> bool:
    """Run macOS say command and save output to an AIFF file."""
    if not IS_MAC:
        return False
    clamped_rate = max(80, min(300, rate))
    try:
        result = subprocess.run(
            ["say", "-v", voice, "-r", str(clamped_rate), "-o", output_path, text],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("say コマンド実行失敗: %s", exc)
        return False


# ─── Sentence-level emotion detection ────────────────────────

_SAD_WORDS = re.compile(r"悲し|辛い|つらい|寂し|ごめん|泣")
_HAPPY_WORDS = re.compile(r"嬉し|楽し|やった|素敵|すごい|わーい|好き|大好き")
_ANGRY_WORDS = re.compile(r"怒|むかつく|イライラ|うざ|ひどい|最悪")
_TENDER_WORDS = re.compile(r"愛し|大切|守|ありがとう|感謝|温か")
_WHISPER_WORDS = re.compile(r"秘密|内緒|こっそり|ひそひそ|小声")


def _detect_sentence_emotion(sentence: str, base_emotion: str) -> str:
    """Detect per-sentence emotion override from content."""
    if _WHISPER_WORDS.search(sentence):
        return "whisper"
    if _SAD_WORDS.search(sentence):
        return "sad"
    if _HAPPY_WORDS.search(sentence):
        return "happy"
    if _ANGRY_WORDS.search(sentence):
        return "angry"
    if _TENDER_WORDS.search(sentence):
        return "loving"
    return base_emotion


# ─── Configuration ───────────────────────────────────────────


@dataclass
class EmotionalTTSConfig:
    """Configuration for the emotional TTS engine."""

    enabled: bool = True
    voice: str = "Kyoko"
    base_rate: int = 175
    enable_post_processing: bool = True
    enable_fillers: bool = False
    enable_pauses: bool = True
    whisper_enabled: bool = True


# ─── Main Engine ─────────────────────────────────────────────


class EmotionalTTSEngine:
    """感情豊かな音声合成エンジン

    6つの感情状態に応じて音声パラメータを動的に調整:
    - happy: 明るく高めのピッチ、やや速い
    - sad: 低めのピッチ、ゆっくり、間が多い
    - excited: 高ピッチ、速い、エネルギッシュ
    - calm: 穏やかなピッチ、ゆったり
    - angry: 強い声、やや速い
    - loving: 柔らかく温かい声

    audio_mode:
      "post_process" -- say -> file -> numpy transform -> sounddevice playback
      "direct"       -- say command only (no librosa/sounddevice needed)
    """

    def __init__(self, config: dict | EmotionalTTSConfig | None = None) -> None:
        if config is None:
            cfg = EmotionalTTSConfig()
        elif isinstance(config, dict):
            cfg = EmotionalTTSConfig(**{
                k: v for k, v in config.items() if hasattr(EmotionalTTSConfig, k)
            })
        else:
            cfg = config

        self.enabled: bool = cfg.enabled
        self.voice: str = cfg.voice
        self.base_rate: int = cfg.base_rate
        self.enable_post_processing: bool = cfg.enable_post_processing
        self.enable_fillers: bool = cfg.enable_fillers
        self.enable_pauses: bool = cfg.enable_pauses
        self.whisper_enabled: bool = cfg.whisper_enabled

        self._emotion: str = "calm"
        self._intensity: float = 0.7
        self._warmth: float = 0.7
        self._energy: float = 0.5
        self._intimacy: float = 0.5

        self._lock = threading.Lock()
        self._playback_lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._stop_event = threading.Event()

        self._can_post_process: bool = can_post_process()

        logger.info(
            "EmotionalTTS 初期化: post_process=%s, voice=%s",
            self._can_post_process and self.enable_post_processing,
            self.voice,
        )

    # ─── Properties ──────────────────────────────────────────

    @property
    def emotion(self) -> str:
        return self._emotion

    @property
    def intensity(self) -> float:
        return self._intensity

    @property
    def audio_mode(self) -> str:
        if self._can_post_process and self.enable_post_processing:
            return "post_process"
        return "direct"

    # ─── Public API ──────────────────────────────────────────

    def set_emotion(self, emotion: str, intensity: float = 0.7) -> None:
        """感情と強度を設定する。

        Args:
            emotion: 感情キー ("happy", "sad", "excited", "calm", "angry", "loving")
            intensity: 強度 0.0-1.0
        """
        if emotion not in EMOTION_PARAMS:
            logger.warning("未知の感情キー '%s', 'calm' にフォールバック", emotion)
            emotion = "calm"
        self._emotion = emotion
        self._intensity = max(0.0, min(1.0, intensity))

    def set_expressiveness(
        self,
        warmth: float | None = None,
        energy: float | None = None,
        intimacy: float | None = None,
    ) -> None:
        """表現パラメータを個別に設定する。

        Args:
            warmth: 温かみ係数 (0-1)
            energy: エネルギー感 (0-1)
            intimacy: 親密さレベル (0-1)
        """
        if warmth is not None:
            self._warmth = max(0.0, min(1.0, warmth))
        if energy is not None:
            self._energy = max(0.0, min(1.0, energy))
        if intimacy is not None:
            self._intimacy = max(0.0, min(1.0, intimacy))

    def speak(self, text: str, blocking: bool = False) -> None:
        """感情を込めてテキストを読み上げる。

        Args:
            text: 読み上げるテキスト
            blocking: True の場合は読み上げ完了までブロック
        """
        if not self.enabled or not IS_MAC:
            return
        clean = _clean_for_tts(text)
        if not clean:
            return

        self._stop_event.clear()

        if blocking:
            self._speak_emotional(clean)
        else:
            threading.Thread(
                target=self._speak_emotional, args=(clean,), daemon=True
            ).start()

    def speak_sentence_by_sentence(
        self, text: str, blocking: bool = False
    ) -> None:
        """文単位で感情を込めて逐次読み上げる。

        各文の内容に応じて感情パラメータを微調整し、
        文間に感情に応じたポーズを挿入する。

        Args:
            text: 読み上げるテキスト全体
            blocking: True の場合は全文完了までブロック
        """
        if not self.enabled or not IS_MAC:
            return
        if not text or not text.strip():
            return

        self._stop_event.clear()

        if blocking:
            self._speak_sentences_emotional(text)
        else:
            threading.Thread(
                target=self._speak_sentences_emotional,
                args=(text,),
                daemon=True,
            ).start()

    def speak_with_callback(
        self,
        text: str,
        on_done: Callable[[], None] | None = None,
        sentence_mode: bool = True,
    ) -> None:
        """テキストを読み上げ、完了後に on_done を呼ぶ。

        Args:
            text: 読み上げるテキスト
            on_done: 読み上げ完了後に呼ばれるコールバック
            sentence_mode: True の場合は文単位逐次読み上げ
        """
        if not self.enabled or not IS_MAC:
            if on_done:
                on_done()
            return

        def _worker() -> None:
            if sentence_mode:
                self._speak_sentences_emotional(text)
            else:
                clean = _clean_for_tts(text)
                if clean:
                    self._speak_emotional(clean)
            if on_done:
                on_done()

        self._stop_event.clear()
        threading.Thread(target=_worker, daemon=True).start()

    def speak_with_emotion_analysis(
        self, text: str, emotion_state: dict
    ) -> None:
        """テキストの内容と現在の感情状態から自動で表現を決定して読み上げる。

        emotion_state は EmotionState.to_dict() の形式:
          {"happiness": 0.8, "curiosity": 0.6, "affection": 0.7,
           "energy": 0.9, "anxiety": 0.1}

        Args:
            text: 読み上げるテキスト
            emotion_state: EmotionState の辞書表現
        """
        mapped_emotion = self._map_emotion_state(emotion_state)
        intensity = self._compute_intensity(emotion_state)
        self.set_emotion(mapped_emotion, intensity)

        self.set_expressiveness(
            warmth=emotion_state.get("affection", 0.5),
            energy=emotion_state.get("energy", 0.5),
            intimacy=min(1.0, emotion_state.get("affection", 0.5) * 1.3),
        )

        self.speak_sentence_by_sentence(text)

    def stop(self) -> None:
        """現在の読み上げを停止する。"""
        self._stop_event.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc = None
        stop_playback()

    def is_speaking(self) -> bool:
        """読み上げ中かどうか。"""
        return self._proc is not None and self._proc.poll() is None

    # ─── Emotion mapping helpers ─────────────────────────────

    @staticmethod
    def _map_emotion_state(emotion_state: dict) -> str:
        """EmotionState dict to emotion key for TTS parameters."""
        positives = {
            k: v
            for k, v in emotion_state.items()
            if k in ("happiness", "curiosity", "affection", "energy")
        }
        if not positives:
            return "calm"

        dominant = max(positives, key=positives.get)  # type: ignore[arg-type]
        anxiety = emotion_state.get("anxiety", 0.0)

        if anxiety > 0.6:
            happiness = emotion_state.get("happiness", 0.5)
            return "sad" if happiness < 0.4 else "angry"

        return _DOMINANT_TO_EMOTION.get(dominant, "calm")

    @staticmethod
    def _compute_intensity(emotion_state: dict) -> float:
        """Compute expression intensity from the emotion state spread."""
        values = [
            v
            for k, v in emotion_state.items()
            if k in ("happiness", "curiosity", "affection", "energy", "anxiety")
        ]
        if not values:
            return 0.5
        deviations = [abs(v - 0.5) for v in values]
        return min(1.0, max(deviations) * 2.0)

    # ─── Internal: emotional speech pipeline ─────────────────

    def _get_blended_params(self, emotion: str) -> dict[str, float]:
        """Get emotion parameters blended by intensity."""
        params = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["calm"])
        neutral = EMOTION_PARAMS["calm"]
        intensity = self._intensity

        blended: dict[str, float] = {}
        for key in params:
            neutral_val = neutral.get(key, 0.0)
            emotional_val = params[key]
            blended[key] = neutral_val + (emotional_val - neutral_val) * intensity
        return blended

    def _compute_effective_rate(self, params: dict[str, float]) -> int:
        """Compute say command rate from blended parameters."""
        offset = params.get("rate_offset", 0.0)
        raw = self.base_rate + offset
        return max(80, min(300, int(raw)))

    def _speak_emotional(self, text: str) -> None:
        """Speak a single cleaned text segment with emotion."""
        if self._stop_event.is_set():
            return

        params = self._get_blended_params(self._emotion)
        rate = self._compute_effective_rate(params)

        if self.audio_mode == "post_process":
            self._speak_with_post_processing(text, rate, params)
        else:
            self._speak_direct(text, rate)

    def _speak_direct(self, text: str, rate: int) -> None:
        """Fallback: say command with no post-processing."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            try:
                self._proc = subprocess.Popen(
                    ["say", "-v", self.voice, "-r", str(rate), text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._proc.wait()
            except (FileNotFoundError, OSError) as exc:
                logger.warning("say 直接実行失敗: %s", exc)

    def _speak_with_post_processing(
        self, text: str, rate: int, params: dict[str, float]
    ) -> None:
        """Full pipeline: say -> file -> transform -> playback."""
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".aiff", prefix="ai_tts_")
            os.close(fd)

            success = _say_to_file(text, self.voice, rate, tmp_path)
            if not success:
                self._speak_direct(text, rate)
                return

            chunk = read_audio_file(tmp_path)
            if chunk is None:
                self._speak_direct(text, rate)
                return

            chunk = self._apply_emotion_transforms(chunk, params)
            play_chunk(chunk, lock=self._playback_lock)

        except Exception as exc:
            logger.warning("音声後処理エラー、直接再生にフォールバック: %s", exc)
            self._speak_direct(text, rate)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _apply_emotion_transforms(
        self, chunk: AudioChunk, params: dict[str, float]
    ) -> AudioChunk:
        """Apply the full chain of audio transforms for the current emotion."""
        semitones = params.get("pitch_semitones", 0.0)
        chunk = pitch_shift(chunk, semitones)

        breathiness = params.get("breathiness", 0.0)
        breathiness_total = breathiness + self._intimacy * 0.05
        chunk = apply_breathiness(chunk, breathiness_total)

        reverb = params.get("reverb_mix", 0.0)
        chunk = apply_reverb(chunk, reverb)

        volume = params.get("volume", 1.0)
        chunk = apply_volume(chunk, volume)

        return chunk

    # ─── Sentence-by-sentence with emotion ───────────────────

    def _speak_sentences_emotional(self, text: str) -> None:
        """Split text into sentences, detect per-sentence emotion, and speak."""
        sentences = _split_sentences(text)
        if not sentences:
            return

        base_emotion = self._emotion
        base_params = self._get_blended_params(base_emotion)
        pause_factor = base_params.get("pause_factor", 1.0)

        for idx, sentence in enumerate(sentences):
            if self._stop_event.is_set():
                return

            clean = _clean_for_tts(sentence)
            if not clean:
                continue

            sent_emotion = _detect_sentence_emotion(clean, base_emotion)

            is_whisper = sent_emotion == "whisper" and self.whisper_enabled
            if is_whisper:
                sent_params = self._get_blended_params("loving")
            elif sent_emotion != base_emotion:
                sent_params = self._get_blended_params(sent_emotion)
            else:
                sent_params = base_params

            sent_rate = self._compute_effective_rate(sent_params)

            if self.audio_mode == "post_process":
                chunk = self._render_sentence(clean, sent_rate, sent_params)
                if chunk is None:
                    self._speak_direct(clean, sent_rate)
                    continue

                if is_whisper:
                    chunk = apply_whisper_effect(chunk)

                play_chunk(chunk, lock=self._playback_lock)

                if self.enable_pauses and idx < len(sentences) - 1:
                    pause_dur = 0.25 * pause_factor
                    if self._stop_event.wait(pause_dur):
                        return
            else:
                self._speak_direct(clean, sent_rate)
                if self.enable_pauses and idx < len(sentences) - 1:
                    pause_dur = 0.15 * pause_factor
                    if self._stop_event.wait(pause_dur):
                        return

    def _render_sentence(
        self, text: str, rate: int, params: dict[str, float]
    ) -> AudioChunk | None:
        """Render a single sentence to an AudioChunk via say + post-processing."""
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".aiff", prefix="ai_tts_s_")
            os.close(fd)

            success = _say_to_file(text, self.voice, rate, tmp_path)
            if not success:
                return None

            chunk = read_audio_file(tmp_path)
            if chunk is None:
                return None

            return self._apply_emotion_transforms(chunk, params)

        except Exception as exc:
            logger.warning("文レンダリングエラー: %s", exc)
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # ─── Utility: available voices ───────────────────────────

    @staticmethod
    def available_japanese_voices() -> list[str]:
        """インストール済みの日本語音声一覧を返す。"""
        if not IS_MAC:
            return []
        try:
            res = subprocess.run(
                ["say", "-v", "?"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            voices: list[str] = []
            for line in res.stdout.splitlines():
                if "ja_JP" in line or "ja-JP" in line:
                    name = line.split()[0]
                    voices.append(name)
            return voices or ["Kyoko", "Otoya"]
        except Exception:
            return ["Kyoko", "Otoya"]


# ─── Layer 3: Neural TTS stub ────────────────────────────────


class NeuralTTSBackend:
    """将来の VITS/XTTS 統合用スタブ。

    このクラスは Coqui TTS や他のニューラル音声合成が
    利用可能になった際のインターフェースを定義する。
    現在は NotImplementedError を送出する。
    """

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path
        self._model: object = None
        self._loaded = False

    def load_model(self) -> None:
        """モデルをロードする（未実装）。"""
        raise NotImplementedError(
            "Neural TTS backend is not yet available. "
            "Install Coqui TTS and provide a model path."
        )

    def synthesize(
        self,
        text: str,
        emotion: str = "calm",
        speaker_id: int = 0,
    ) -> AudioChunk | None:
        """テキストから音声を合成する（未実装）。"""
        raise NotImplementedError("Neural TTS synthesis not yet implemented.")

    @property
    def is_available(self) -> bool:
        """ニューラルバックエンドが利用可能か。"""
        return False


# ─── Factory ─────────────────────────────────────────────────


def create_tts_engine(config: dict) -> EmotionalTTSEngine:
    """設定に応じて最適なTTSエンジンを返す。

    常に EmotionalTTSEngine を返す。audio ライブラリが不足している
    環境では自動的に direct モード（say コマンドのみ）にフォールバック。

    Args:
        config: tts セクションの設定辞書
            {
                "enabled": True,
                "voice": "Kyoko",
                "rate": 175,
                "enable_post_processing": True,
                ...
            }

    Returns:
        EmotionalTTSEngine インスタンス
    """
    mapped = dict(config)
    if "rate" in mapped and "base_rate" not in mapped:
        mapped["base_rate"] = mapped.pop("rate")

    return EmotionalTTSEngine(mapped)
