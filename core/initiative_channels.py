"""
自発性メッセージ配信チャネル（Initiative Channels）

アイが自分から発したメッセージを、起動モード別に適切な経路で配信する。

配信先:
  - CLIChannel      : ターミナル出力（プロンプトを邪魔しない差し込み）
  - DesktopChannel  : デスクトップペットの吹き出し + TTS
  - WebChannel      : Web UI へ SSE/ポーリングで配信（キューに積む）
  - VoiceChannel    : ハンズフリーモードで TTS 直接発話
  - BroadcastChannel: 複数チャネルに同時配信
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

logger = logging.getLogger(__name__)


# ─── Message ─────────────────────────────────────────────────

@dataclass
class InitiativeMessage:
    """自発メッセージ。"""
    text: str
    desire_type: str = ""        # 欲求タイプ (CARE/CURIOSITY/...)
    urgency: float = 0.5         # 0.0〜1.0
    emotion: str = "calm"
    allow_voice: bool = True     # 音声出力を許可するか
    expires_at: float = 0.0      # UNIX 時刻。0なら期限なし
    metadata: dict = field(default_factory=dict)

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at <= 0:
            return False
        return (now or time.time()) > self.expires_at


# ─── Protocol ────────────────────────────────────────────────

class InitiativeChannel(Protocol):
    """配信チャネル共通インターフェース。"""

    def deliver(self, message: InitiativeMessage) -> bool:
        """メッセージを配信する。配信できたら True。"""
        ...

    @property
    def channel_name(self) -> str:
        ...


# ─── CLI ─────────────────────────────────────────────────────

class CLIChannel:
    """ターミナル出力。"""
    channel_name = "cli"

    def __init__(self, prefix: str = "\n💭 アイ: ", bell: bool = True):
        self._prefix = prefix
        self._bell = bell

    def deliver(self, message: InitiativeMessage) -> bool:
        try:
            bell = "\a" if self._bell else ""
            sys.stdout.write(f"{bell}{self._prefix}{message.text}\n")
            sys.stdout.flush()
            return True
        except Exception as e:
            logger.warning("CLIChannel 配信失敗: %s", e)
            return False


# ─── Desktop Pet ─────────────────────────────────────────────

class DesktopChannel:
    """
    デスクトップペットの吹き出し + TTS。

    desktop_pet 側で show_bubble(text) / speak(text) を提供している想定。
    無ければコールバックで注入も可。
    """
    channel_name = "desktop"

    def __init__(
        self,
        show_bubble: Optional[Callable[[str], None]] = None,
        tts: Any = None,
        speak_aloud: bool = True,
    ):
        self._show_bubble = show_bubble
        self._tts = tts
        self._speak_aloud = speak_aloud

    def deliver(self, message: InitiativeMessage) -> bool:
        delivered = False
        try:
            if self._show_bubble:
                self._show_bubble(message.text)
                delivered = True
        except Exception as e:
            logger.warning("Desktop 吹き出し失敗: %s", e)

        if self._speak_aloud and message.allow_voice and self._tts:
            try:
                if hasattr(self._tts, "set_emotion"):
                    self._tts.set_emotion(message.emotion, message.urgency)
                if hasattr(self._tts, "speak_sentence_by_sentence"):
                    self._tts.speak_sentence_by_sentence(message.text)
                elif hasattr(self._tts, "speak"):
                    self._tts.speak(message.text)
                delivered = True
            except Exception as e:
                logger.warning("Desktop TTS 失敗: %s", e)
        return delivered


# ─── Web ─────────────────────────────────────────────────────

class WebChannel:
    """
    Web UI 配信。キューに積んでおき、`/api/initiative/poll` で取得させる。
    サーバー側で SSE/WebSocket にアップグレードしても同じキューを使う。
    """
    channel_name = "web"

    def __init__(self, maxsize: int = 100):
        self._q: queue.Queue[InitiativeMessage] = queue.Queue(maxsize=maxsize)

    def deliver(self, message: InitiativeMessage) -> bool:
        try:
            # 古いメッセージは破棄
            while self._q.full():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            self._q.put_nowait(message)
            return True
        except Exception as e:
            logger.warning("WebChannel enqueue 失敗: %s", e)
            return False

    def drain(self, max_items: int = 10) -> list[InitiativeMessage]:
        """サーバー API から呼ばれ、未配信メッセージを取り出す。"""
        out: list[InitiativeMessage] = []
        now = time.time()
        for _ in range(max_items):
            try:
                m = self._q.get_nowait()
            except queue.Empty:
                break
            if not m.is_expired(now):
                out.append(m)
        return out


# ─── Voice (hands-free) ──────────────────────────────────────

class VoiceChannel:
    """
    ハンズフリー音声モード用。TTS で直接発話。
    voice_loop がアクティブな時だけ配信する。
    """
    channel_name = "voice"

    def __init__(
        self,
        tts: Any,
        is_active_fn: Optional[Callable[[], bool]] = None,
    ):
        self._tts = tts
        self._is_active_fn = is_active_fn or (lambda: True)

    def deliver(self, message: InitiativeMessage) -> bool:
        if not message.allow_voice:
            return False
        if not self._is_active_fn():
            # VoiceLoop が非アクティブなら配信しない
            return False
        if not self._tts:
            return False
        try:
            if hasattr(self._tts, "set_emotion"):
                self._tts.set_emotion(message.emotion, message.urgency)
            if hasattr(self._tts, "speak_sentence_by_sentence"):
                self._tts.speak_sentence_by_sentence(message.text)
            elif hasattr(self._tts, "speak"):
                self._tts.speak(message.text)
            return True
        except Exception as e:
            logger.warning("VoiceChannel 発話失敗: %s", e)
            return False


# ─── Broadcast ───────────────────────────────────────────────

class BroadcastChannel:
    """複数チャネルに同時配信。"""
    channel_name = "broadcast"

    def __init__(self, channels: list[InitiativeChannel]):
        self._channels = list(channels)
        self._lock = threading.Lock()

    def add(self, ch: InitiativeChannel) -> None:
        with self._lock:
            self._channels.append(ch)

    def remove(self, ch: InitiativeChannel) -> None:
        with self._lock:
            try:
                self._channels.remove(ch)
            except ValueError:
                pass

    def deliver(self, message: InitiativeMessage) -> bool:
        with self._lock:
            targets = list(self._channels)
        any_ok = False
        for ch in targets:
            try:
                if ch.deliver(message):
                    any_ok = True
            except Exception as e:
                logger.warning("%s 配信失敗: %s", getattr(ch, "channel_name", "?"), e)
        return any_ok
