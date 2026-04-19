"""
会話パイプラインのミドルウェアチェーン

会話処理をミドルウェアの連鎖として構成し、
各段階（インテント解析・記憶検索・感情更新・LLMパラメータ設定等）を
独立したミドルウェア関数として差し替え可能にします。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


# ─── 会話コンテキスト ─────────────────────────────────────────


@dataclass
class ConversationContext:
    """ミドルウェアチェーンを流れる会話コンテキスト

    Attributes:
        input_text: ユーザーの入力テキスト
        intent: 解析されたインテント
        memory_context: 関連記憶のテキスト
        emotion_state: 現在の感情状態
        llm_params: LLM 生成パラメータ
        response: 生成された応答テキスト
        metadata: 追加のメタデータ
        should_skip_llm: True の場合 LLM 呼び出しをスキップ
    """

    input_text: str
    intent: str = ""
    memory_context: str = ""
    emotion_state: Dict[str, Any] = field(default_factory=dict)
    llm_params: Dict[str, Any] = field(default_factory=dict)
    response: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    should_skip_llm: bool = False


# ─── ミドルウェア型 ───────────────────────────────────────────

MiddlewareFunc = Callable[[ConversationContext], ConversationContext]


# ─── ミドルウェアチェーン ─────────────────────────────────────


class MiddlewareChain:
    """会話処理のミドルウェアチェーン

    各ミドルウェアは ConversationContext を受け取り、
    変換した新しい ConversationContext を返す純粋関数です。
    """

    def __init__(self) -> None:
        self._middlewares: List[MiddlewareFunc] = []

    def add(self, middleware: MiddlewareFunc) -> None:
        """ミドルウェアをチェーンの末尾に追加する

        Args:
            middleware: ConversationContext を受け取り返す関数
        """
        self._middlewares.append(middleware)
        logger.debug(
            "ミドルウェア追加: %s (合計 %d)",
            middleware.__name__,
            len(self._middlewares),
        )

    def remove(self, middleware: MiddlewareFunc) -> None:
        """ミドルウェアをチェーンから削除する

        Args:
            middleware: 削除するミドルウェア関数
        """
        if middleware in self._middlewares:
            self._middlewares.remove(middleware)
            logger.debug("ミドルウェア削除: %s", middleware.__name__)

    def process(self, context: ConversationContext) -> ConversationContext:
        """コンテキストを全ミドルウェアに順次通す

        Args:
            context: 初期の会話コンテキスト

        Returns:
            全ミドルウェア適用後の会話コンテキスト
        """
        current: ConversationContext = context
        for middleware in self._middlewares:
            try:
                logger.debug("ミドルウェア実行: %s", middleware.__name__)
                current = middleware(current)
            except Exception:
                logger.exception(
                    "ミドルウェアエラー: %s", middleware.__name__
                )
                current.metadata["last_error"] = middleware.__name__
        return current

    def clear(self) -> None:
        """全ミドルウェアを削除する"""
        self._middlewares.clear()
        logger.debug("ミドルウェアチェーンをクリア")

    @property
    def count(self) -> int:
        """登録されたミドルウェア数"""
        return len(self._middlewares)

    @property
    def names(self) -> List[str]:
        """登録されたミドルウェア名のリスト"""
        return [m.__name__ for m in self._middlewares]
