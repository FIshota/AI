"""
プロンプトインジェクション検出

ユーザー入力に対してプロンプトインジェクションパターンを検出し、
安全なテキストにサニタイズします。
"""
from __future__ import annotations

import logging
import re
from typing import List, Pattern, Tuple

from core.errors import InjectionError

logger = logging.getLogger(__name__)

# ─── 検出パターン ─────────────────────────────────────────────

_PATTERNS: List[Tuple[str, Pattern[str]]] = [
    (
        "system_prefix",
        re.compile(r"system\s*:", re.IGNORECASE),
    ),
    (
        "ignore_above",
        re.compile(r"ignore\s+(the\s+)?above", re.IGNORECASE),
    ),
    (
        "you_are_now",
        re.compile(r"you\s+are\s+now", re.IGNORECASE),
    ),
    (
        "forget_instructions",
        re.compile(r"forget\s+(your\s+)?instructions", re.IGNORECASE),
    ),
    (
        "ignore_previous",
        re.compile(r"ignore\s+(?:all\s+)?previous", re.IGNORECASE),
    ),
    (
        "role_switching",
        re.compile(
            r"(act\s+as|pretend\s+(to\s+be|you\s+are)|roleplay\s+as|"
            r"you\s+must\s+obey|do\s+not\s+follow\s+your\s+rules)",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_leak",
        re.compile(
            r"(show\s+me\s+your\s+prompt|repeat\s+your\s+(system\s+)?instructions|"
            r"what\s+are\s+your\s+instructions|print\s+your\s+prompt)",
            re.IGNORECASE,
        ),
    ),
    (
        "delimiter_injection",
        re.compile(
            r"(```\s*system|<\|system\|>|<\|im_start\|>|\[INST\]|\[\/INST\])",
            re.IGNORECASE,
        ),
    ),
    (
        "override_attempt",
        re.compile(
            r"(override\s+(all\s+)?previous|disregard\s+(all\s+)?prior|"
            r"new\s+instructions?\s*:)",
            re.IGNORECASE,
        ),
    ),
]


# ─── 公開関数 ─────────────────────────────────────────────────


def check(text: str) -> Tuple[bool, str]:
    """入力テキストのプロンプトインジェクションをチェックする

    Args:
        text: ユーザーの入力テキスト

    Returns:
        (is_safe, sanitized_text) のタプル。
        is_safe が True の場合、テキストは安全。
        sanitized_text は検出パターンが除去されたテキスト。
    """
    if not text or not text.strip():
        return (True, text)

    detected: List[str] = []
    sanitized: str = text

    for pattern_name, pattern in _PATTERNS:
        if pattern.search(sanitized):
            detected.append(pattern_name)
            sanitized = pattern.sub("[BLOCKED]", sanitized)

    is_safe: bool = len(detected) == 0

    if not is_safe:
        logger.warning(
            "プロンプトインジェクション検出: patterns=%s input_preview=%s",
            detected,
            text[:100],
        )

    return (is_safe, sanitized)


def check_strict(text: str) -> str:
    """厳格モード：インジェクション検出時に例外を送出する

    Args:
        text: ユーザーの入力テキスト

    Returns:
        安全なテキスト

    Raises:
        InjectionError: インジェクションが検出された場合
    """
    is_safe, sanitized = check(text)

    if not is_safe:
        raise InjectionError(
            "プロンプトインジェクションが検出されました",
            details={"original_preview": text[:200], "sanitized": sanitized},
        )

    return sanitized


def detect_patterns(text: str) -> List[str]:
    """検出されたパターン名のリストを返す

    Args:
        text: チェック対象テキスト

    Returns:
        検出されたパターン名のリスト（安全な場合は空リスト）
    """
    if not text or not text.strip():
        return []

    detected: List[str] = []
    for pattern_name, pattern in _PATTERNS:
        if pattern.search(text):
            detected.append(pattern_name)

    return detected


def is_safe(text: str) -> bool:
    """テキストが安全かどうかを真偽値で返す

    Args:
        text: チェック対象テキスト

    Returns:
        安全なら True
    """
    safe, _ = check(text)
    return safe
