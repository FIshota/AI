"""
イベント駆動コンポーネント間通信

インプロセスの Pub/Sub イベントバスを提供します。
同期・非同期の両方でハンドラを呼び出せます。
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# ─── イベントタイプ定数 ────────────────────────────────────────

EMOTION_CHANGED: str = "emotion_changed"
MEMORY_SAVED: str = "memory_saved"
DIARY_WRITTEN: str = "diary_written"
LEARNING_COMPLETE: str = "learning_complete"
ERROR_OCCURRED: str = "error_occurred"
CONFIG_CHANGED: str = "config_changed"
SECURITY_ALERT: str = "security_alert"


# ─── イベントバス ──────────────────────────────────────────────


class EventBus:
    """スレッドセーフなインプロセス Pub/Sub イベントバス"""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[..., None]]] = {}
        self._lock: threading.Lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Callable[..., None]) -> None:
        """イベントタイプにハンドラを登録する

        Args:
            event_type: イベントタイプ文字列
            handler: イベント発火時に呼ばれるコールバック
        """
        with self._lock:
            handlers = self._subscribers.setdefault(event_type, [])
            if handler not in handlers:
                handlers.append(handler)
                logger.debug(
                    "ハンドラ登録: event=%s handler=%s", event_type, handler.__name__
                )

    def unsubscribe(self, event_type: str, handler: Callable[..., None]) -> None:
        """イベントタイプからハンドラを解除する

        Args:
            event_type: イベントタイプ文字列
            handler: 解除するコールバック
        """
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)
                logger.debug(
                    "ハンドラ解除: event=%s handler=%s",
                    event_type,
                    handler.__name__,
                )

    def emit(self, event_type: str, **data: Any) -> None:
        """同期的にイベントを発火する（現在のスレッドでハンドラを実行）

        Args:
            event_type: イベントタイプ文字列
            **data: ハンドラに渡すキーワード引数
        """
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))

        if not handlers:
            logger.debug("ハンドラなし: event=%s", event_type)
            return

        logger.debug(
            "イベント発火(同期): event=%s handlers=%d", event_type, len(handlers)
        )
        for handler in handlers:
            try:
                handler(**data)
            except Exception:
                logger.exception(
                    "ハンドラ実行エラー: event=%s handler=%s",
                    event_type,
                    handler.__name__,
                )

    def emit_async(self, event_type: str, **data: Any) -> None:
        """非同期的にイベントを発火する（デーモンスレッドでハンドラを実行）

        Args:
            event_type: イベントタイプ文字列
            **data: ハンドラに渡すキーワード引数
        """
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))

        if not handlers:
            logger.debug("ハンドラなし: event=%s", event_type)
            return

        logger.debug(
            "イベント発火(非同期): event=%s handlers=%d", event_type, len(handlers)
        )
        for handler in handlers:
            thread = threading.Thread(
                target=self._safe_call,
                args=(event_type, handler),
                kwargs=data,
                daemon=True,
            )
            thread.start()

    @staticmethod
    def _safe_call(event_type: str, handler: Callable[..., None], **data: Any) -> None:
        """ハンドラを安全に呼び出す（例外をログに記録）"""
        try:
            handler(**data)
        except Exception:
            logger.exception(
                "非同期ハンドラ実行エラー: event=%s handler=%s",
                event_type,
                handler.__name__,
            )

    def clear(self) -> None:
        """全購読を解除する"""
        with self._lock:
            self._subscribers.clear()
            logger.debug("全イベント購読をクリア")

    def subscriber_count(self, event_type: str) -> int:
        """指定イベントタイプの購読者数を返す"""
        with self._lock:
            return len(self._subscribers.get(event_type, []))
