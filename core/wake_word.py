"""
ウェイクワード検出（Wake Word Detection）
呼びかけ（「アイちゃん」等）でアイを起動するためのモジュール。

抽象化設計:
  - WakeWordBackend プロトコルに2つの実装を提供
    a) VoskWakeWord: 日本語 Vosk 小型モデル + キーワードマッチ（軽量・高速）
    b) OpenWakeWordBackend: openwakeword ライブラリ（精度重視・オフライン）
  - どちらも同じ API を持ち、settings.json の backend フィールドで切替可能

使い方:
    from core.wake_word import create_wake_word_detector

    detector = create_wake_word_detector(config, on_detected=my_callback)
    detector.start()
    ...
    detector.stop()
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path
from typing import Callable, Optional, Protocol

logger = logging.getLogger(__name__)

DEFAULT_WAKE_WORDS = ["アイちゃん", "アイ", "ねぇアイ", "アイちゃーん"]
DEFAULT_SAMPLE_RATE = 16000


# ─── Protocol ──────────────────────────────────────────────────

class WakeWordBackend(Protocol):
    """Wake word backend インターフェース。"""

    def start(self) -> None:
        """検出ループ開始（非ブロッキング）。"""
        ...

    def stop(self) -> None:
        """検出ループ停止。"""
        ...

    @property
    def is_running(self) -> bool:
        ...


# ─── Vosk backend（軽量・キーワードマッチ） ──────────────────

class VoskWakeWord:
    """
    Vosk small model + キーワード文字列マッチでウェイクワード検出。

    長所: 軽量（モデル~40MB）、モデル取得が容易、日本語ネイティブ
    短所: 発音揺れに弱い、CPU負荷やや高め
    """

    def __init__(
        self,
        wake_words: list[str],
        on_detected: Callable[[str], None],
        model_path: Optional[Path] = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ):
        self._wake_words = [w.lower() for w in wake_words]
        self._on_detected = on_detected
        self._model_path = model_path
        self._sample_rate = sample_rate
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop, name="VoskWakeWord", daemon=True
        )
        self._thread.start()
        logger.info(
            "VoskWakeWord 起動 (words=%s)", self._wake_words
        )

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _match(self, text: str) -> str:
        """認識テキストから wake word を検出する。"""
        if not text:
            return ""
        # Vosk日本語は空白区切りで返すため空白除去 + 小文字化
        normalized = text.replace(" ", "").replace("　", "").lower()
        for w in self._wake_words:
            key = w.replace(" ", "").replace("　", "").lower()
            if key and key in normalized:
                return w
        return ""

    def _listen_loop(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model
        except ImportError as e:
            logger.error(
                "VoskWakeWord: 依存が不足しています (%s)。`pip install vosk sounddevice` を実行してください。",
                e,
            )
            self._running = False
            return

        try:
            model = Model(str(self._model_path)) if self._model_path else Model(lang="ja")
        except Exception as e:
            logger.error(
                "Vosk モデル読み込み失敗: %s。日本語モデルを事前DLしてください: https://alphacephei.com/vosk/models",
                e,
            )
            self._running = False
            return

        rec = KaldiRecognizer(model, self._sample_rate)
        rec.SetWords(False)

        audio_q: queue.Queue = queue.Queue()

        def _callback(indata, frames, time_info, status):
            if status:
                logger.debug("Vosk audio status: %s", status)
            audio_q.put(bytes(indata))

        last_partial = ""
        try:
            with sd.RawInputStream(
                samplerate=self._sample_rate,
                blocksize=8000,
                dtype="int16",
                channels=1,
                callback=_callback,
            ):
                print(f"🎤 ウェイクワード待機中... (words={self._wake_words})", flush=True)
                logger.info("🎤 ウェイクワード待機中... (%s)", self._wake_words)
                while self._running:
                    try:
                        data = audio_q.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result()).get("text", "")
                        if result:
                            print(f"[stt] {result}", flush=True)
                    else:
                        result = json.loads(rec.PartialResult()).get("partial", "")
                        # 部分結果は差分があるときだけ表示
                        if result and result != last_partial:
                            print(f"[stt...] {result}", flush=True, end="\r")
                            last_partial = result
                    if not result:
                        continue
                    hit = self._match(result)
                    if hit:
                        print(f"\n🔔 ウェイクワード検出: 『{hit}』", flush=True)
                        logger.info("🔔 ウェイクワード検出: '%s' (認識: '%s')", hit, result)
                        try:
                            self._on_detected(hit)
                        except Exception as e:
                            logger.exception("on_detected コールバック失敗: %s", e)
                        # 連続検出を防ぐためレコグナイザをリセット
                        rec.Reset()
                        last_partial = ""
        except Exception as e:
            logger.exception("VoskWakeWord ループ異常終了: %s", e)
            print(f"[ERROR] 音声入力ループ異常終了: {e}", flush=True)
            print("        macOSの場合: システム設定 > プライバシーとセキュリティ > マイク で", flush=True)
            print("        Terminal / Python にマイク権限を許可してください。", flush=True)
        finally:
            self._running = False


# ─── openWakeWord backend（精度重視） ─────────────────────────

class OpenWakeWordBackend:
    """
    openwakeword ライブラリを使った高精度検出。

    長所: 発音揺れに強い、TFLite高速推論、カスタムモデル対応
    短所: 初回依存が重い、カスタム「アイちゃん」モデルは別途学習が必要
         （英語既存モデルで音韻近似する or ONNX を事前配置）
    """

    def __init__(
        self,
        wake_words: list[str],
        on_detected: Callable[[str], None],
        model_paths: Optional[list[str]] = None,
        threshold: float = 0.5,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ):
        self._wake_words = wake_words
        self._on_detected = on_detected
        self._model_paths = model_paths or []
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop, name="OpenWakeWord", daemon=True
        )
        self._thread.start()
        logger.info("OpenWakeWordBackend 起動")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _listen_loop(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
            from openwakeword.model import Model
        except ImportError as e:
            logger.error(
                "OpenWakeWord: 依存が不足しています (%s)。`pip install openwakeword sounddevice numpy` を実行してください。",
                e,
            )
            self._running = False
            return

        try:
            if self._model_paths:
                model = Model(wakeword_models=self._model_paths)
            else:
                # 既定モデル（英語）でフォールバック起動
                model = Model()
        except Exception as e:
            logger.error("openwakeword モデル読み込み失敗: %s", e)
            self._running = False
            return

        chunk = 1280  # 80ms @ 16kHz

        audio_q: queue.Queue = queue.Queue()

        def _callback(indata, frames, time_info, status):
            audio_q.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                blocksize=chunk,
                dtype="int16",
                channels=1,
                callback=_callback,
            ):
                logger.info("🎤 openwakeword 待機中...")
                while self._running:
                    try:
                        data = audio_q.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    prediction = model.predict(data.flatten())
                    for name, score in prediction.items():
                        if score >= self._threshold:
                            logger.info("🔔 wake detected: %s score=%.2f", name, score)
                            try:
                                self._on_detected(name)
                            except Exception as e:
                                logger.exception("on_detected コールバック失敗: %s", e)
                            # クールダウン
                            model.reset()
        except Exception as e:
            logger.exception("OpenWakeWord ループ異常終了: %s", e)
        finally:
            self._running = False


# ─── Factory ────────────────────────────────────────────────────

def create_wake_word_detector(
    config: dict,
    on_detected: Callable[[str], None],
    base_dir: Optional[Path] = None,
) -> Optional[WakeWordBackend]:
    """
    settings.json の voice_activation セクションから検出器を生成する。

    設定例:
        "voice_activation": {
            "enabled": true,
            "backend": "vosk",  // "vosk" | "openwakeword"
            "wake_words": ["アイちゃん", "アイ"],
            "vosk_model_path": "models/vosk-small-ja",
            "openwakeword_models": ["models/hey-ai.onnx"],
            "threshold": 0.5
        }
    """
    va = config.get("voice_activation", {})
    if not va.get("enabled", False):
        return None

    wake_words = va.get("wake_words", DEFAULT_WAKE_WORDS)
    backend = (va.get("backend") or "vosk").lower()

    if backend == "vosk":
        model_path = va.get("vosk_model_path")
        if model_path and base_dir:
            model_path = base_dir / model_path
        return VoskWakeWord(
            wake_words=wake_words,
            on_detected=on_detected,
            model_path=Path(model_path) if model_path else None,
        )
    elif backend in ("openwakeword", "oww"):
        model_paths = va.get("openwakeword_models", []) or []
        if base_dir:
            model_paths = [
                str(base_dir / m) if not Path(m).is_absolute() else m
                for m in model_paths
            ]
        return OpenWakeWordBackend(
            wake_words=wake_words,
            on_detected=on_detected,
            model_paths=model_paths,
            threshold=va.get("threshold", 0.5),
        )
    else:
        logger.warning("不明な wake word backend: %s。vosk にフォールバック", backend)
        return VoskWakeWord(wake_words=wake_words, on_detected=on_detected)
