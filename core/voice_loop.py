"""
ハンズフリー会話ループ（Voice Conversation Loop）

起動後、以下を繰り返す:
  1. STT（無音検出で発話終了判定）
  2. AiChan.chat() で応答生成
  3. TTS 再生
  4. TTS 終了 → 即 STT 再開
  5. 終話ワード検出 or アイドルタイムアウトでスリープへ復帰

使い方:
    loop = VoiceLoop(ai_chan, tts, stt, config)
    loop.wake()          # 起動（挨拶TTS → STTループ）
    ...
    loop.sleep()         # 外から停止
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_END_PHRASES = ["またね", "おやすみ", "バイバイ", "終わり", "ありがとう、終わり"]
DEFAULT_GREETING = "はい、なあに？"
DEFAULT_IDLE_TIMEOUT = 30.0  # 秒


class VoiceLoop:
    """ハンズフリー音声会話のオーケストレータ。"""

    def __init__(
        self,
        ai_chan: Any,          # core.ai_chan.AiChan
        tts: Any,              # NeuralTTS or EmotionalTTS
        stt: Any,              # core.stt.STTEngine
        config: Optional[dict] = None,
    ):
        self._ai = ai_chan
        self._tts = tts
        self._stt = stt
        cfg = (config or {}).get("voice_activation", {})
        self._greeting = cfg.get("greeting_on_wake", DEFAULT_GREETING)
        self._end_phrases = cfg.get("end_phrases", DEFAULT_END_PHRASES)
        self._idle_timeout = float(cfg.get("idle_timeout_sec", DEFAULT_IDLE_TIMEOUT))
        self._hands_free = cfg.get("hands_free_mode", True)

        self._active = False
        self._last_interaction = 0.0
        self._idle_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ─── 外部 API ───────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    def wake(self, trigger_word: str = "") -> None:
        """
        ウェイクワード検出時に呼ばれるエントリポイント。
        挨拶 TTS → STT ループを開始。
        """
        with self._lock:
            if self._active:
                logger.info("VoiceLoop は既にアクティブです")
                return
            self._active = True
            self._last_interaction = time.time()

        logger.info("🌟 VoiceLoop 起動 (trigger='%s')", trigger_word)

        # 起動挨拶
        self._speak(self._greeting)

        if self._hands_free:
            # アイドル監視スレッド
            self._idle_thread = threading.Thread(
                target=self._idle_watcher, name="VoiceLoopIdle", daemon=True
            )
            self._idle_thread.start()

            # STT 連続リスニング開始（既存の start_continuous_listening を使用）
            self._start_continuous_stt()

    def sleep(self) -> None:
        """会話ループを停止してスリープへ戻す。"""
        with self._lock:
            if not self._active:
                return
            self._active = False

        logger.info("💤 VoiceLoop スリープへ復帰")
        try:
            if hasattr(self._stt, "stop_continuous_listening"):
                self._stt.stop_continuous_listening()
            elif hasattr(self._stt, "stop"):
                self._stt.stop()
        except Exception as e:
            logger.warning("STT 停止失敗: %s", e)

    # ─── 内部 ───────────────────────────────────────────────

    def _start_continuous_stt(self) -> None:
        """core.stt.STTEngine.start_continuous_listening にコールバックを登録。"""
        if not hasattr(self._stt, "start_continuous_listening"):
            logger.error(
                "STT エンジンが continuous_listening 非対応です。ハンズフリー不可。"
            )
            self._active = False
            return

        try:
            self._stt.start_continuous_listening(
                on_text=self._on_user_text,
                silence_threshold=0.01,
                silence_duration=1.5,
                min_speech_duration=0.3,
            )
        except TypeError:
            # シグネチャが違う場合のフォールバック
            try:
                self._stt.start_continuous_listening(on_text=self._on_user_text)
            except Exception as e:
                logger.exception("STT 連続リスニング開始失敗: %s", e)
                self._active = False

    def _on_user_text(self, text: str) -> None:
        """STT が発話を確定したら呼ばれる。"""
        if not self._active:
            return

        text = (text or "").strip()
        if not text:
            return

        self._last_interaction = time.time()
        logger.info("👤 ユーザー: %s", text)

        # 終話ワード判定
        if self._is_end_phrase(text):
            self._speak("またね、呼んでね。")
            time.sleep(1.0)
            self.sleep()
            return

        # AiChan に渡して応答生成
        try:
            response = self._ai.chat(text)
        except Exception as e:
            logger.exception("AiChan.chat 失敗: %s", e)
            response = "ごめん、うまく返せなかった"

        # chat() 内で既に TTS 発話済みのため、ここでは追加発話しない。
        # ただし ai_chan.chat() の実装で TTS 失敗時に備え、空でないか確認だけ。
        if not response:
            logger.warning("AiChan.chat が空文字を返しました")

        self._last_interaction = time.time()

    def _idle_watcher(self) -> None:
        """一定時間発話がなければスリープへ復帰。"""
        while self._active:
            time.sleep(1.0)
            if time.time() - self._last_interaction > self._idle_timeout:
                logger.info(
                    "⏰ %.0f秒無音 → スリープ復帰", self._idle_timeout
                )
                self._speak("また呼んでね。")
                time.sleep(0.8)
                self.sleep()
                return

    def _is_end_phrase(self, text: str) -> bool:
        t = text.replace(" ", "").replace("、", "").replace("。", "")
        return any(p.replace(" ", "") in t for p in self._end_phrases)

    def _speak(self, text: str) -> None:
        """TTS の単発発話。複数の API を順に試す。"""
        if not text or not self._tts:
            return
        try:
            if hasattr(self._tts, "speak_with_emotion_analysis"):
                emotion = {}
                if hasattr(self._ai, "emotion") and hasattr(self._ai.emotion, "state"):
                    state = self._ai.emotion.state
                    emotion = state.to_dict() if hasattr(state, "to_dict") else {}
                self._tts.speak_with_emotion_analysis(text, emotion)
            elif hasattr(self._tts, "speak_sentence_by_sentence"):
                self._tts.speak_sentence_by_sentence(text)
            elif hasattr(self._tts, "speak"):
                self._tts.speak(text)
        except Exception as e:
            logger.warning("TTS 発話失敗: %s", e)
