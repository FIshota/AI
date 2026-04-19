"""
ニューラル音声合成バックエンド v2

edge-tts (Microsoft Neural TTS) を使用した高品質な日本語音声合成。
感情パラメータを SSML のプロソディ制御にマッピングし、
人間らしい自然な音声を生成する。

v2 改善点:
- SSML <break> タグによる自然なポーズ挿入（句読点・三点リーダー）
- 文位置に応じたピッチ変化（文頭↑ 文末↓）で棒読み防止
- 複数文バッチ合成でネットワーク呼び出し削減 → 長文の高速化
- 専用イベントループスレッドで asyncio 安定化 → 途中停止防止
- タイムアウト保護で無限ブロック防止

ネットワーク接続が必要。オフライン時は macOS say にフォールバック。
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

IS_MAC = __import__("platform").system() == "Darwin"

# ─── edge-tts availability ──────────────────────────────────

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    edge_tts = None  # type: ignore[assignment]
    EDGE_TTS_AVAILABLE = False


# ─── Emotion → prosody mapping ──────────────────────────────

@dataclass(frozen=True)
class VoiceProsody:
    """SSML プロソディパラメータ"""
    rate: str        # e.g. "+10%", "-20%", "+0%"
    pitch: str       # e.g. "+5Hz", "-3Hz", "+0Hz"
    volume: str      # e.g. "+10%", "-15%", "+0%"


EMOTION_PROSODY: dict[str, VoiceProsody] = {
    "happy":   VoiceProsody(rate="+8%",  pitch="+8Hz",  volume="+5%"),
    "sad":     VoiceProsody(rate="-15%", pitch="-5Hz",  volume="-10%"),
    "excited": VoiceProsody(rate="+15%", pitch="+12Hz", volume="+10%"),
    "calm":    VoiceProsody(rate="-5%",  pitch="+0Hz",  volume="+0%"),
    "angry":   VoiceProsody(rate="+5%",  pitch="+3Hz",  volume="+15%"),
    "loving":  VoiceProsody(rate="-10%", pitch="+3Hz",  volume="-5%"),
    "whisper": VoiceProsody(rate="-20%", pitch="-2Hz",  volume="-25%"),
    "neutral": VoiceProsody(rate="+0%",  pitch="+0Hz",  volume="+0%"),
}

# 文末感情検出パターン
import re
_SAD_WORDS = re.compile(r"悲し|辛い|つらい|寂し|ごめん|泣")
_HAPPY_WORDS = re.compile(r"嬉し|楽し|やった|素敵|すごい|わーい|好き|大好き")
_ANGRY_WORDS = re.compile(r"怒|むかつく|イライラ|うざ|ひどい|最悪")
_TENDER_WORDS = re.compile(r"愛し|大切|守|ありがとう|感謝|温か")
_WHISPER_WORDS = re.compile(r"秘密|内緒|こっそり|ひそひそ|小声")
_EXCITED_WORDS = re.compile(r"わあ|すごい|やばい|めっちゃ|超|最高|！！")

# ─── Voice profiles ─────────────────────────────────────────

# 利用可能なニューラル日本語音声
NEURAL_VOICES = {
    "nanami": "ja-JP-NanamiNeural",   # 女性・自然で温かい
    "keita": "ja-JP-KeitaNeural",     # 男性・落ち着いた
}

# アイちゃんのデフォルト音声
DEFAULT_VOICE = "ja-JP-NanamiNeural"


# ─── Sentence utilities ─────────────────────────────────────

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


def _detect_sentence_emotion(sentence: str, base_emotion: str) -> str:
    """文の内容から感情を検出する。"""
    if _WHISPER_WORDS.search(sentence):
        return "whisper"
    if _EXCITED_WORDS.search(sentence):
        return "excited"
    if _SAD_WORDS.search(sentence):
        return "sad"
    if _HAPPY_WORDS.search(sentence):
        return "happy"
    if _ANGRY_WORDS.search(sentence):
        return "angry"
    if _TENDER_WORDS.search(sentence):
        return "loving"
    return base_emotion


# ─── SSML break injection for natural pauses ────────────────

def _inject_breaks(
    text: str,
    short_ms: int = 200,
    thought_ms: int = 450,
    soft_ms: int = 150,
) -> str:
    """句読点の後に自然なポーズを挿入する SSML <break> タグ。

    ポーズ長はプロソディ学習結果で上書きできる。
    デフォルトは人間の平均的な間の取り方。
    """
    # 読点 → 短いポーズ（人間の呼吸間に近い）
    text = re.sub(r'、', f'、<break time="{short_ms}ms"/>', text)
    # 三点リーダー → 思考の間
    text = re.sub(r'…+', f'<break time="{thought_ms}ms"/>', text)
    # 「・・・」も同様
    text = re.sub(r'・{{2,}}', f'<break time="{thought_ms - 50}ms"/>', text)
    # 「〜」→ 少し柔らかい間
    text = re.sub(r'〜', f'〜<break time="{soft_ms}ms"/>', text)
    return text


# ─── Sentence-position pitch micro-variation ─────────────────

def _position_pitch_offset(
    idx: int, total: int, emotion: str,
    learned_start: int = 0, learned_end: int = 0,
) -> int:
    """文の位置に応じたピッチ微調整（Hz）。

    日本語の自然なイントネーション:
    - 文頭: 少し高め（話し始めのエネルギー）
    - 中盤: ニュートラル
    - 文末: 少し下がる（文の終わりの安定感）
    - 疑問・興奮: 文末も上がる

    learned_start/learned_end: プロソディ学習から得たオフセット (Hz)。
    学習データがある場合、デフォルト値に加算される。
    """
    if total <= 1:
        return learned_start  # 単文の場合は文頭補正のみ

    position_ratio = idx / max(total - 1, 1)

    if emotion in ("excited", "happy"):
        base = int(3 * (1.0 - position_ratio * 0.5))
    elif emotion in ("sad", "loving", "whisper"):
        base = int(-2 * position_ratio)
    else:
        base = int(2 - 3 * position_ratio)

    # 学習値をブレンド: 文頭→文末にかけて線形補間
    learned = int(learned_start * (1.0 - position_ratio) + learned_end * position_ratio)

    return base + learned


# ─── Dedicated event loop thread ─────────────────────────────

class _AsyncRunner:
    """専用スレッドで asyncio イベントループを安全に実行する。

    問題: asyncio.run_until_complete() をスレッドプールから呼ぶと
    「loop already running」や「no current event loop」で不安定。
    解決: 専用スレッドで1つのループを永続実行し、
    run_coroutine() で外部から安全にコルーチンを投入する。
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="neural-tts-loop"
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run_coroutine(self, coro, timeout: float = 30.0):
        """コルーチンをイベントループに投入し、結果を待つ。タイムアウト付き。"""
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def shutdown(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)


# モジュールレベルのランナー（遅延初期化）
_runner: Optional[_AsyncRunner] = None
_runner_lock = threading.Lock()


def _get_runner() -> _AsyncRunner:
    """シングルトンの AsyncRunner を取得する。"""
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = _AsyncRunner()
    return _runner


# ─── Neural TTS Engine ──────────────────────────────────────

# バッチ合成の最大文数（これ以上は分割）
_BATCH_MAX_SENTENCES = 6
# edge-tts のタイムアウト（秒）
_TTS_TIMEOUT = 30.0


class NeuralTTSEngine:
    """edge-tts ベースのニューラル音声合成エンジン v2

    特徴:
    - Microsoft Neural TTS による人間らしい自然な音声
    - SSML <break> タグで句読点のポーズ、三点リーダーの思考間
    - 文位置に応じたピッチ微調整で棒読み防止
    - 感情パラメータ→SSMLプロソディの自動マッピング
    - 複数文バッチ合成でネットワーク呼び出し削減
    - 専用イベントループスレッドで安定動作
    - タイムアウト保護（30秒）で途中停止防止
    - ネットワーク不通時は macOS say にフォールバック
    - EmotionalTTSEngine と同じ API を提供
    """

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.enabled: bool = cfg.get("enabled", True)
        self.voice: str = cfg.get("neural_voice", DEFAULT_VOICE)
        self.base_rate: int = cfg.get("rate", 175)

        # macOS say フォールバック用
        self._say_voice: str = cfg.get("voice", "Kyoko")

        self._emotion: str = "calm"
        self._intensity: float = 0.7

        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()

        # edge-tts 可否
        self._neural_available = EDGE_TTS_AVAILABLE
        self._neural_failed_count = 0
        self._max_neural_failures = 3  # 連続失敗でフォールバック

        # プロソディ学習オーバーライド（ProsodyLearner から設定される）
        self._learned_overrides: dict = {}

        # Item #P6: 合成済み音声の LRU キャッシュ（短フレーズの体感レイテンシ削減）
        # key: (voice, rate, pitch, volume, text) → tmp_path
        self._synth_cache: "collections.OrderedDict[tuple, str]" = (
            __import__("collections").OrderedDict()
        )
        self._synth_cache_max = 32
        self._synth_cache_hits = 0

        # ─── ユーザー制御の声質調整 ─────────────────────────
        tuning = cfg.get("voice_tuning", {}) or {}
        self._tuning = {
            # 全体オフセット
            "rate_offset_pct":   float(tuning.get("rate_offset_pct",   0.0)),  # -50..+50
            "pitch_offset_hz":   float(tuning.get("pitch_offset_hz",   0.0)),  # -20..+20
            "volume_offset_pct": float(tuning.get("volume_offset_pct", 0.0)),  # -50..+50
            # 感情表現の強度スケール (1.0 = 標準, 0.0=棒読み, 2.0=大げさ)
            "emotion_intensity_scale": float(tuning.get("emotion_intensity_scale", 1.0)),
            # ポーズ関連
            "pause_scale":       float(tuning.get("pause_scale", 1.0)),
            "breath_pause_ms":   int(tuning.get("breath_pause_ms", 0)),
            # 音色傾向
            "warmth":            float(tuning.get("warmth", 0.0)),      # -1..+1 暖かみ
            "brightness":        float(tuning.get("brightness", 0.0)),  # -1..+1 明るさ
            # 揺らぎ: 0で安定、1で最大揺らぎ（文内のピッチ微変動幅）
            "stability":         float(tuning.get("stability", 0.5)),
        }

        logger.info(
            "NeuralTTS v2 初期化: neural=%s, voice=%s",
            self._neural_available,
            self.voice,
        )

    # ─── Properties ──────────────────────────────────────────

    @property
    def emotion(self) -> str:
        return self._emotion

    @property
    def audio_mode(self) -> str:
        if self._neural_available and self._neural_failed_count < self._max_neural_failures:
            return "neural"
        return "direct"

    # ─── Public API (compatible with EmotionalTTSEngine) ─────

    def set_emotion(self, emotion: str, intensity: float = 0.7) -> None:
        """感情と強度を設定する。"""
        if emotion not in EMOTION_PROSODY:
            emotion = "calm"
        self._emotion = emotion
        self._intensity = max(0.0, min(1.0, intensity))

    def set_expressiveness(
        self,
        warmth: float | None = None,
        energy: float | None = None,
        intimacy: float | None = None,
    ) -> None:
        """表現パラメータを設定する（互換性のため）。"""
        pass  # Neural TTS ではプロソディで自動制御

    def apply_learned_prosody(self, overrides: dict) -> None:
        """ProsodyLearner から得た学習済みパラメータを適用する。

        overrides: ProsodyLearner.get_tts_overrides() の戻り値
        空 dict を渡すと学習適用を解除（デフォルトに戻る）。
        """
        self._learned_overrides = dict(overrides)
        if overrides:
            logger.info(
                "プロソディ学習適用: rate=%+.0f%%, pitch=%+.0fHz, "
                "break_short=%dms, break_long=%dms",
                overrides.get("rate_pct", 0),
                overrides.get("pitch_hz", 0),
                overrides.get("break_short_ms", 200),
                overrides.get("break_long_ms", 400),
            )
        else:
            logger.info("プロソディ学習解除: デフォルトに復帰")

    def speak(self, text: str, blocking: bool = False) -> None:
        """テキストを読み上げる。"""
        if not self.enabled:
            return
        clean = _clean_for_tts(text)
        if not clean:
            return

        self._stop_event.clear()
        if blocking:
            self._speak_neural(clean, self._emotion)
        else:
            threading.Thread(
                target=self._speak_neural,
                args=(clean, self._emotion),
                daemon=True,
            ).start()

    def speak_sentence_by_sentence(
        self, text: str, blocking: bool = False
    ) -> None:
        """文単位で感情を込めて逐次読み上げる。"""
        if not self.enabled:
            return
        if not text or not text.strip():
            return

        self._stop_event.clear()
        if blocking:
            self._speak_sentences(text)
        else:
            threading.Thread(
                target=self._speak_sentences,
                args=(text,),
                daemon=True,
            ).start()

    def speak_with_emotion_analysis(
        self, text: str, emotion_state: dict
    ) -> None:
        """感情状態から自動で表現を決定して読み上げる。"""
        mapped_emotion = self._map_emotion_state(emotion_state)
        intensity = self._compute_intensity(emotion_state)
        self.set_emotion(mapped_emotion, intensity)
        self.speak_sentence_by_sentence(text)

    def speak_with_callback(
        self,
        text: str,
        on_done=None,
        sentence_mode: bool = True,
    ) -> None:
        """読み上げ完了後にコールバックを呼ぶ。"""
        if not self.enabled:
            if on_done:
                on_done()
            return

        def _worker():
            if sentence_mode:
                self._speak_sentences(text)
            else:
                clean = _clean_for_tts(text)
                if clean:
                    self._speak_neural(clean, self._emotion)
            if on_done:
                on_done()

        threading.Thread(target=_worker, daemon=True).start()

    def stop(self) -> None:
        """現在の読み上げを停止する。"""
        self._stop_event.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                self._proc = None

    def is_speaking(self) -> bool:
        """読み上げ中かどうか。"""
        return self._proc is not None and self._proc.poll() is None

    # ─── Emotion mapping ────────────────────────────────────

    _DOMINANT_TO_EMOTION: dict[str, str] = {
        "happiness": "happy",
        "curiosity": "excited",
        "affection": "loving",
        "energy": "excited",
    }

    @staticmethod
    def _map_emotion_state(emotion_state: dict) -> str:
        """EmotionState dict → emotion key"""
        positives = {
            k: v for k, v in emotion_state.items()
            if k in ("happiness", "curiosity", "affection", "energy")
        }
        if not positives:
            return "calm"

        dominant = max(positives, key=positives.get)  # type: ignore[arg-type]
        anxiety = emotion_state.get("anxiety", 0.0)

        if anxiety > 0.6:
            happiness = emotion_state.get("happiness", 0.5)
            return "sad" if happiness < 0.4 else "angry"

        return NeuralTTSEngine._DOMINANT_TO_EMOTION.get(dominant, "calm")

    @staticmethod
    def _compute_intensity(emotion_state: dict) -> float:
        values = [
            v for k, v in emotion_state.items()
            if k in ("happiness", "curiosity", "affection", "energy", "anxiety")
        ]
        if not values:
            return 0.5
        deviations = [abs(v - 0.5) for v in values]
        return min(1.0, max(deviations) * 2.0)

    # ─── Internal: prosody ──────────────────────────────────

    def set_voice_tuning(self, **kwargs) -> None:
        """
        ユーザー制御の声質調整をランタイムで変更する。
        受理キー: rate_offset_pct, pitch_offset_hz, volume_offset_pct,
                 emotion_intensity_scale, pause_scale, breath_pause_ms,
                 warmth, brightness, stability
        """
        for k, v in kwargs.items():
            if k in self._tuning and v is not None:
                try:
                    self._tuning[k] = type(self._tuning[k])(v)
                except (TypeError, ValueError):
                    pass
        logger.info("🎚 voice_tuning 更新: %s", {k: self._tuning[k] for k in kwargs if k in self._tuning})

    def get_voice_tuning(self) -> dict:
        """現在の声質調整パラメータを返す。"""
        return dict(self._tuning)

    def _get_prosody(self, emotion: str, pitch_offset_hz: int = 0) -> VoiceProsody:
        """感情から強度を加味したプロソディを取得。

        pitch_offset_hz: 文位置に応じたピッチ微調整（Hz）
        学習済みオーバーライドがあれば加算される。
        voice_tuning のユーザー調整も反映。
        """
        prosody = EMOTION_PROSODY.get(emotion, EMOTION_PROSODY["neutral"])
        neutral = EMOTION_PROSODY["neutral"]
        # 感情強度スケール適用
        base_factor = self._intensity if self._intensity < 0.8 else 1.0
        factor = max(0.0, min(2.0, base_factor * self._tuning.get("emotion_intensity_scale", 1.0)))

        # 学習オーバーライド + ユーザー調整
        ov = self._learned_overrides
        tn = self._tuning
        # warmth/brightness → ピッチ & 音量への写像
        # warmth > 0: ピッチ下げ・音量やや上げ (温かく低く)
        # brightness > 0: ピッチ上げ (明るく)
        timbre_pitch = -tn["warmth"] * 3.0 + tn["brightness"] * 4.0  # Hz
        timbre_vol = tn["warmth"] * 3.0  # %

        learned_rate = ov.get("rate_pct", 0.0) + tn["rate_offset_pct"]
        learned_pitch = ov.get("pitch_hz", 0.0) + tn["pitch_offset_hz"] + timbre_pitch
        learned_vol = ov.get("volume_pct", 0.0) + tn["volume_offset_pct"] + timbre_vol

        def _blend(emo_str: str, neu_str: str, extra: float = 0.0) -> str:
            try:
                emo_val = float(emo_str.replace("%", "").replace("Hz", ""))
                neu_val = float(neu_str.replace("%", "").replace("Hz", ""))
                blended = neu_val + (emo_val - neu_val) * factor + extra
                unit = "Hz" if "Hz" in emo_str else "%"
                sign = "+" if blended >= 0 else ""
                return f"{sign}{blended:.0f}{unit}"
            except ValueError:
                return emo_str

        return VoiceProsody(
            rate=_blend(prosody.rate, neutral.rate, learned_rate),
            pitch=_blend(prosody.pitch, neutral.pitch, pitch_offset_hz + learned_pitch),
            volume=_blend(prosody.volume, neutral.volume, learned_vol),
        )

    # ─── Internal: neural speech (single utterance) ─────────

    def _speak_neural(self, text: str, emotion: str,
                      pitch_offset_hz: int = 0) -> None:
        """edge-tts でニューラル音声を生成・再生する。"""
        if self._stop_event.is_set():
            return

        if self.audio_mode != "neural":
            self._speak_say_fallback(text)
            return

        prosody = self._get_prosody(emotion, pitch_offset_hz)
        plain_text = text

        # Item #P6: 合成キャッシュチェック — 短フレーズの再発話を高速化
        cache_key = (self.voice, prosody.rate, prosody.pitch, prosody.volume, plain_text)
        cached_path = self._synth_cache.get(cache_key) if len(plain_text) <= 40 else None
        if cached_path and os.path.exists(cached_path):
            self._synth_cache.move_to_end(cache_key)
            self._synth_cache_hits += 1
            try:
                with self._lock:
                    self._proc = subprocess.Popen(
                        ["afplay", cached_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._proc.wait()
                return
            except Exception as e:
                logger.debug("synth cache replay failed: %s", e)

        tmp_path: str | None = None

        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="ai_neural_")
            os.close(fd)

            communicate = edge_tts.Communicate(
                text=plain_text,
                voice=self.voice,
                rate=prosody.rate,
                pitch=prosody.pitch,
                volume=prosody.volume,
            )

            runner = _get_runner()
            runner.run_coroutine(communicate.save(tmp_path), timeout=_TTS_TIMEOUT)

            if self._stop_event.is_set():
                return

            # afplay で再生 (macOS)
            with self._lock:
                self._proc = subprocess.Popen(
                    ["afplay", tmp_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._proc.wait()

            # 成功 — 連続失敗カウントをリセット
            self._neural_failed_count = 0

            # Item #P6: 短フレーズをキャッシュ（評価順・LRU）
            if len(plain_text) <= 40 and tmp_path and os.path.exists(tmp_path):
                try:
                    import shutil as _sh
                    cache_dir = Path(tempfile.gettempdir()) / "ai_tts_cache"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    cached_copy = cache_dir / f"tts_{abs(hash(cache_key))}.mp3"
                    _sh.copyfile(tmp_path, cached_copy)
                    self._synth_cache[cache_key] = str(cached_copy)
                    while len(self._synth_cache) > self._synth_cache_max:
                        _k, _old = self._synth_cache.popitem(last=False)
                        try:
                            os.unlink(_old)
                        except OSError:
                            pass
                except Exception:
                    pass

        except Exception as exc:
            logger.warning(
                "Neural TTS 失敗 (%d回目): %s",
                self._neural_failed_count + 1, exc,
            )
            self._neural_failed_count += 1
            # edge_tts 失敗時は macOS say でフォールバック
            self._speak_say_fallback(text)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _speak_neural_plain(self, text: str, prosody: VoiceProsody,
                            tmp_path: str | None) -> None:
        """SSML break なしのプレーンテキストで再生（フォールバック用）"""
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="ai_neural_fb_")
        os.close(fd)
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=prosody.rate,
                pitch=prosody.pitch,
                volume=prosody.volume,
            )
            runner = _get_runner()
            runner.run_coroutine(communicate.save(tmp_path), timeout=_TTS_TIMEOUT)

            if self._stop_event.is_set():
                return

            with self._lock:
                self._proc = subprocess.Popen(
                    ["afplay", tmp_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._proc.wait()
            self._neural_failed_count = 0
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # ─── Internal: batch sentence synthesis ─────────────────

    def _speak_sentences(self, text: str) -> None:
        """文単位で感情検出しながら読み上げる。

        v2: 同じ感情の連続文はバッチ合成してネットワーク呼び出しを削減。
        文位置に応じたピッチ微調整で棒読みを防止。
        """
        sentences = _split_sentences(text)
        if not sentences:
            return

        base_emotion = self._emotion
        total = len(sentences)

        # 文ごとの感情とピッチオフセットを先に計算
        plans: list[tuple[str, str, int]] = []  # (clean_text, emotion, pitch_offset)
        for idx, sentence in enumerate(sentences):
            clean = _clean_for_tts(sentence)
            if not clean:
                continue
            sent_emotion = _detect_sentence_emotion(clean, base_emotion)
            # 学習済みイントネーションがあれば適用
            ov = self._learned_overrides
            pitch_off = _position_pitch_offset(
                idx, total, sent_emotion,
                learned_start=ov.get("pitch_start_offset", 0),
                learned_end=ov.get("pitch_end_offset", 0),
            )
            plans.append((clean, sent_emotion, pitch_off))

        if not plans:
            return

        # 同じ感情の連続文をバッチにまとめる
        batches = self._group_into_batches(plans)

        for batch in batches:
            if self._stop_event.is_set():
                return

            if len(batch) == 1:
                # 単文: 従来通り
                clean, emotion, pitch_off = batch[0]
                self._speak_neural(clean, emotion, pitch_off)
            else:
                # 複数文バッチ: 文間に <break> を入れて1回の合成
                self._speak_batch(batch)

            # バッチ間ポーズ（文の切れ目の間）
            if batch is not batches[-1]:
                last_emotion = batch[-1][1]
                pause = 0.12
                if last_emotion in ("sad", "loving"):
                    pause = 0.30
                elif last_emotion == "excited":
                    pause = 0.06
                if self._stop_event.wait(pause):
                    return

    def _group_into_batches(
        self, plans: list[tuple[str, str, int]]
    ) -> list[list[tuple[str, str, int]]]:
        """同じ感情の連続文をバッチにグループ化する。"""
        batches: list[list[tuple[str, str, int]]] = []
        current_batch: list[tuple[str, str, int]] = []
        current_emotion: str | None = None

        for item in plans:
            _, emotion, _ = item
            if (
                emotion != current_emotion
                or len(current_batch) >= _BATCH_MAX_SENTENCES
            ):
                if current_batch:
                    batches.append(current_batch)
                current_batch = [item]
                current_emotion = emotion
            else:
                current_batch.append(item)

        if current_batch:
            batches.append(current_batch)

        return batches

    def _speak_batch(self, batch: list[tuple[str, str, int]]) -> None:
        """複数文を文間ブレイク付きで1回の合成にまとめて再生する。"""
        if self._stop_event.is_set():
            return

        if self.audio_mode != "neural":
            # フォールバック: 個別に say で再生
            for clean, _, _ in batch:
                self._speak_say_fallback(clean)
            return

        # edge_tts は SSML <break> タグを文字として読み上げてしまうため、
        # 文を個別に合成し、文間に time.sleep でポーズを入れる。
        ov = self._learned_overrides
        pause_sec = ov.get("break_long_ms", 400) / 1000.0

        for i, (clean, emotion, pitch_off) in enumerate(batch):
            if self._stop_event.is_set():
                return
            self._speak_neural(clean, emotion, pitch_off)
            # 文間ポーズ（最後の文の後は不要）
            if i < len(batch) - 1:
                if self._stop_event.wait(pause_sec):
                    return

    def _speak_say_fallback(self, text: str) -> None:
        """macOS say コマンドによるフォールバック"""
        if not IS_MAC:
            return
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            try:
                self._proc = subprocess.Popen(
                    ["say", "-v", self._say_voice, "-r", str(self.base_rate), text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._proc.wait()
            except (FileNotFoundError, OSError) as exc:
                logger.warning("say フォールバック失敗: %s", exc)

    # ─── Utility ────────────────────────────────────────────

    @staticmethod
    def available_voices() -> list[dict[str, str]]:
        """利用可能なニューラル日本語音声のリストを返す。"""
        if not EDGE_TTS_AVAILABLE:
            return []
        try:
            runner = _get_runner()
            voices = runner.run_coroutine(
                edge_tts.list_voices(), timeout=15.0
            )
            return [
                {
                    "name": v["ShortName"],
                    "gender": v["Gender"],
                    "friendly": v.get("FriendlyName", ""),
                }
                for v in voices
                if v["Locale"].startswith("ja")
            ]
        except Exception:
            return []


# ─── Factory ────────────────────────────────────────────────

def create_neural_tts(config: dict) -> NeuralTTSEngine:
    """設定からNeuralTTSEngineを生成するファクトリ関数。"""
    return NeuralTTSEngine(config)
