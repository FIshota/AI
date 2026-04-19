"""
PII（個人情報）マスキング

電話番号・メールアドレス・郵便番号・クレジットカード番号・マイナンバーを
検出し、マスクします。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Pattern, Tuple

logger = logging.getLogger(__name__)

# ─── PII カテゴリ ─────────────────────────────────────────────

CATEGORY_PHONE: str = "phone"
CATEGORY_EMAIL: str = "email"
CATEGORY_POSTAL: str = "postal_code"
CATEGORY_CREDIT_CARD: str = "credit_card"
CATEGORY_MY_NUMBER: str = "my_number"

# ─── マスク文字列 ─────────────────────────────────────────────

MASK_PHONE: str = "***-****-****"
MASK_EMAIL: str = "****@****"
MASK_POSTAL: str = "***-****"
MASK_CREDIT_CARD: str = "****-****-****-****"
MASK_MY_NUMBER: str = "************"

# ─── 検出パターン ─────────────────────────────────────────────

# 日本の電話番号: 090-1234-5678, 09012345678, 03-1234-5678 等
_PHONE_PATTERN: Pattern[str] = re.compile(
    r"(?<!\d)"
    r"(?:0[789]0[-\s]?\d{4}[-\s]?\d{4})"  # 携帯
    r"|(?:0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{4})"  # 固定
    r"(?!\d)"
)

# メールアドレス
_EMAIL_PATTERN: Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# 郵便番号: 〒123-4567, 123-4567
_POSTAL_PATTERN: Pattern[str] = re.compile(
    r"〒?\s?\d{3}[-\s]\d{4}"
)

# クレジットカード番号: 1234-5678-9012-3456, 1234567890123456
_CREDIT_CARD_PATTERN: Pattern[str] = re.compile(
    r"(?<!\d)"
    r"(?:\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4})"
    r"(?!\d)"
)

# マイナンバー: 12桁の数字
_MY_NUMBER_PATTERN: Pattern[str] = re.compile(
    r"(?<!\d)\d{12}(?!\d)"
)

# パターンとカテゴリ・マスクの対応
_DETECTION_RULES: List[Tuple[str, Pattern[str], str]] = [
    (CATEGORY_CREDIT_CARD, _CREDIT_CARD_PATTERN, MASK_CREDIT_CARD),
    (CATEGORY_MY_NUMBER, _MY_NUMBER_PATTERN, MASK_MY_NUMBER),
    (CATEGORY_PHONE, _PHONE_PATTERN, MASK_PHONE),
    (CATEGORY_EMAIL, _EMAIL_PATTERN, MASK_EMAIL),
    (CATEGORY_POSTAL, _POSTAL_PATTERN, MASK_POSTAL),
]


# ─── 検出結果 ─────────────────────────────────────────────────


@dataclass(frozen=True)
class PIIMatch:
    """PII 検出結果

    Attributes:
        category: PII カテゴリ
        matched_text: マッチしたテキスト
        start: 開始位置
        end: 終了位置
    """

    category: str
    matched_text: str
    start: int
    end: int


# ─── 公開関数 ─────────────────────────────────────────────────


def mask(text: str) -> str:
    """テキスト中の PII をマスクする

    Args:
        text: 入力テキスト

    Returns:
        PII がマスクされたテキスト
    """
    if not text:
        return text

    result: str = text

    for category, pattern, mask_str in _DETECTION_RULES:
        matches = list(pattern.finditer(result))
        if matches:
            logger.debug(
                "PII検出(%s): %d 件", category, len(matches)
            )
        # 後方から置換して位置ずれを防ぐ
        for match in reversed(matches):
            result = result[:match.start()] + mask_str + result[match.end():]

    return result


def detect(text: str) -> List[Dict[str, object]]:
    """テキスト中の PII を検出する（マスクはしない）

    Args:
        text: 入力テキスト

    Returns:
        検出された PII のリスト。各要素は以下のキーを持つ辞書:
        - category: PII カテゴリ
        - matched_text: マッチしたテキスト
        - start: 開始位置
        - end: 終了位置
    """
    if not text:
        return []

    results: List[Dict[str, object]] = []

    for category, pattern, _mask_str in _DETECTION_RULES:
        for match in pattern.finditer(text):
            results.append({
                "category": category,
                "matched_text": match.group(),
                "start": match.start(),
                "end": match.end(),
            })

    # 開始位置でソート
    results.sort(key=lambda x: x["start"])  # type: ignore[arg-type]

    if results:
        logger.info("PII検出: %d 件", len(results))

    return results


def has_pii(text: str) -> bool:
    """テキストに PII が含まれるかを判定する

    Args:
        text: 入力テキスト

    Returns:
        PII が含まれる場合 True
    """
    return len(detect(text)) > 0


def mask_with_report(text: str) -> Tuple[str, List[Dict[str, object]]]:
    """テキストをマスクし、検出結果も返す

    Args:
        text: 入力テキスト

    Returns:
        (マスク済みテキスト, 検出結果リスト) のタプル
    """
    detections: List[Dict[str, object]] = detect(text)
    masked: str = mask(text)
    return (masked, detections)
