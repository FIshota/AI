"""
クリップボードアシスタント（Sprint 3-A）
コピーされたテキストを自動解析してアイが提案を返す。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# URL 判定パターン
_URL_RE = re.compile(
    r"https?://[^\s]+"
    r"|www\.[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# コード判定パターン（簡易）
_CODE_RE = re.compile(
    r"def\s+\w+\s*\(|class\s+\w+[\s(:]|import\s+\w+|"
    r"function\s+\w+\s*\(|const\s+\w+\s*=|var\s+\w+\s*=|"
    r"#include\s*<|public\s+class\s+|SELECT\s+\w+\s+FROM",
    re.IGNORECASE,
)

_LONG_TEXT_THRESHOLD = 200  # 長文の閾値（文字数）

# 英語判定：ASCII 文字が全体の 60% 以上
_ENGLISH_RATIO = 0.60


def _contains_url(text: str) -> bool:
    return bool(_URL_RE.search(text))


def _looks_like_code(text: str) -> bool:
    return bool(_CODE_RE.search(text))


def _is_mostly_english(text: str) -> bool:
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128 and c.isalpha())
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count == 0:
        return False
    return (ascii_count / alpha_count) >= _ENGLISH_RATIO


def _classify(text: str) -> str:
    """
    テキストの種類を判別する。
    戻り値: "url" | "code" | "long" | "english" | "other"
    """
    stripped = text.strip()
    # URL のみの行が含まれる場合
    if _contains_url(stripped) and len(stripped) < 300:
        return "url"
    if _looks_like_code(stripped):
        return "code"
    if _is_mostly_english(stripped):
        return "english"
    if len(stripped) >= _LONG_TEXT_THRESHOLD:
        return "long"
    return "other"


class ClipboardAssistant:
    """コピーした内容をアイに自動で渡す。"""

    def __init__(self, base_dir: Path, llm_fn: Callable[[str], str]) -> None:
        self._base_dir = Path(base_dir)
        self._llm_fn = llm_fn

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def process_clipboard(self, text: str) -> str:
        """
        コピーされたテキストを解析し、アイらしい提案メッセージを返す。
        """
        try:
            kind = _classify(text)
            if kind == "url":
                return "あ、URL コピーしたんだね！このページ、要約しようか？「要約して」って言ってね😊"
            if kind == "code":
                return "コードをコピーしたみたいだよ！レビューしようか？「コードレビューして」って言ってくれれば見るよ✨"
            if kind == "long":
                return "長い文章をコピーしたね。「要約して」「翻訳して」「添削して」のどれがいい？😄"
            if kind == "english":
                return "英語の文章だね！日本語に訳そうか？「翻訳して」って言ってね🌸"
            # other
            preview = text[:40].replace("\n", " ")
            return f"「{preview}…」コピーしたね。何かしようか？"
        except Exception as e:
            logger.warning("[ClipboardAssistant] process_clipboard error: %s", e)
            return "クリップボードの内容を確認したよ。何かしようか？"

    def summarize(self, text: str) -> str:
        """テキストを日本語で要約する。"""
        try:
            prompt = (
                "以下のテキストを日本語で簡潔に要約してください（3〜5文）。\n\n"
                f"---\n{text[:3000]}\n---"
            )
            return self._llm_fn(prompt)
        except Exception as e:
            logger.warning("[ClipboardAssistant] summarize error: %s", e)
            return "要約中にエラーが発生しちゃった。ごめんね💦"

    def translate_to_ja(self, text: str) -> str:
        """テキストを日本語に翻訳する。"""
        try:
            prompt = (
                "以下のテキストを自然な日本語に翻訳してください。\n\n"
                f"---\n{text[:3000]}\n---"
            )
            return self._llm_fn(prompt)
        except Exception as e:
            logger.warning("[ClipboardAssistant] translate_to_ja error: %s", e)
            return "翻訳中にエラーが発生しちゃった。ごめんね💦"

    def proofread(self, text: str) -> str:
        """テキストを日本語で添削する。"""
        try:
            prompt = (
                "以下のテキストを添削し、修正箇所と理由を説明してください。\n\n"
                f"---\n{text[:3000]}\n---"
            )
            return self._llm_fn(prompt)
        except Exception as e:
            logger.warning("[ClipboardAssistant] proofread error: %s", e)
            return "添削中にエラーが発生しちゃった。ごめんね💦"

    def review_code(self, code: str) -> str:
        """コードをレビューする。"""
        try:
            prompt = (
                "以下のコードをレビューして、問題点・改善案・良い点を日本語で教えてください。\n\n"
                f"```\n{code[:3000]}\n```"
            )
            return self._llm_fn(prompt)
        except Exception as e:
            logger.warning("[ClipboardAssistant] review_code error: %s", e)
            return "コードレビュー中にエラーが発生しちゃった。ごめんね💦"
