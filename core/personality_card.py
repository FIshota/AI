"""
パーソナリティダッシュボードデータ

会話統計・学習状況・感情パターン等を集計し、
アイちゃんの個性を可視化するためのデータ構造を生成します。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ─── パーソナリティカード ─────────────────────────────────────


@dataclass(frozen=True)
class PersonalityCard:
    """アイちゃんのパーソナリティダッシュボードデータ

    Attributes:
        conversation_count: 会話回数
        learning_count: 学習回数
        memory_count: 記憶件数
        emotion_patterns: 感情パターン（感情名 → 出現割合）
        top_topics: よく話すトピック
        active_hours: 活動時間帯（0-23 の整数リスト）
        favorite_words: よく使う言葉
    """

    conversation_count: int = 0
    learning_count: int = 0
    memory_count: int = 0
    emotion_patterns: Dict[str, float] = field(default_factory=dict)
    top_topics: List[str] = field(default_factory=list)
    active_hours: List[int] = field(default_factory=list)
    favorite_words: List[str] = field(default_factory=list)


# ─── 生成関数 ─────────────────────────────────────────────────


def generate(stats: Dict[str, Any]) -> PersonalityCard:
    """統計情報からパーソナリティカードを生成する

    Args:
        stats: 以下のキーを含む辞書（全てオプショナル）
            - conversation_count (int)
            - learning_count (int)
            - memory_count (int)
            - emotion_patterns (dict[str, float])
            - top_topics (list[str])
            - active_hours (list[int])
            - favorite_words (list[str])

    Returns:
        パーソナリティカード
    """
    conversation_count: int = _safe_int(stats.get("conversation_count", 0))
    learning_count: int = _safe_int(stats.get("learning_count", 0))
    memory_count: int = _safe_int(stats.get("memory_count", 0))

    raw_emotions: Any = stats.get("emotion_patterns", {})
    emotion_patterns: Dict[str, float] = _normalize_emotions(raw_emotions)

    raw_topics: Any = stats.get("top_topics", [])
    top_topics: List[str] = _safe_str_list(raw_topics)

    raw_hours: Any = stats.get("active_hours", [])
    active_hours: List[int] = _safe_int_list(raw_hours, min_val=0, max_val=23)

    raw_words: Any = stats.get("favorite_words", [])
    favorite_words: List[str] = _safe_str_list(raw_words)

    card = PersonalityCard(
        conversation_count=conversation_count,
        learning_count=learning_count,
        memory_count=memory_count,
        emotion_patterns=emotion_patterns,
        top_topics=top_topics,
        active_hours=active_hours,
        favorite_words=favorite_words,
    )

    logger.info(
        "パーソナリティカード生成: conversations=%d, memories=%d",
        card.conversation_count,
        card.memory_count,
    )
    return card


def summarize(card: PersonalityCard) -> str:
    """パーソナリティカードのテキスト要約を生成する

    Args:
        card: パーソナリティカード

    Returns:
        テキスト要約
    """
    lines: List[str] = [
        "── パーソナリティカード ──",
        f"  会話回数: {card.conversation_count}",
        f"  学習回数: {card.learning_count}",
        f"  記憶件数: {card.memory_count}",
    ]

    if card.emotion_patterns:
        sorted_emotions = sorted(
            card.emotion_patterns.items(), key=lambda x: x[1], reverse=True
        )
        top_3 = sorted_emotions[:3]
        emotion_str = ", ".join(
            f"{name}({pct:.0%})" for name, pct in top_3
        )
        lines.append(f"  主要感情: {emotion_str}")

    if card.top_topics:
        lines.append(f"  トピック: {', '.join(card.top_topics[:5])}")

    if card.active_hours:
        hour_str = ", ".join(f"{h}時" for h in sorted(card.active_hours)[:5])
        lines.append(f"  活動時間: {hour_str}")

    if card.favorite_words:
        lines.append(f"  よく使う言葉: {', '.join(card.favorite_words[:5])}")

    return "\n".join(lines)


# ─── ヘルパー関数 ─────────────────────────────────────────────


def _safe_int(value: Any) -> int:
    """安全に整数へ変換する（失敗時は 0）"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_str_list(value: Any) -> List[str]:
    """安全に文字列リストへ変換する"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _safe_int_list(value: Any, min_val: int, max_val: int) -> List[int]:
    """安全に整数リストへ変換する（範囲チェック付き）"""
    if not isinstance(value, list):
        return []
    result: List[int] = []
    for item in value:
        try:
            n = int(item)
            if min_val <= n <= max_val:
                result.append(n)
        except (TypeError, ValueError):
            continue
    return result


def _normalize_emotions(raw: Any) -> Dict[str, float]:
    """感情パターンを正規化する（合計 1.0 に）"""
    if not isinstance(raw, dict):
        return {}

    parsed: Dict[str, float] = {}
    for key, val in raw.items():
        try:
            parsed[str(key)] = float(val)
        except (TypeError, ValueError):
            continue

    total: float = sum(parsed.values())
    if total <= 0:
        return parsed

    return {k: v / total for k, v in parsed.items()}
