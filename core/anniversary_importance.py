"""記念日の自動重要度推定。

過去会話の emotional valence + 出現頻度 + 会話継続時間から、
Anniversary の重要度スコア (0.0 - 1.0) を推定する。

設計ドキュメント: docs/design/ANNIVERSARY_IMPORTANCE.md
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ── 重み (mention 40% / |valence| 40% / recency 20%) ────────────
WEIGHT_MENTION: float = 0.40
WEIGHT_VALENCE: float = 0.40
WEIGHT_RECENCY: float = 0.20

# 正規化パラメータ
# mention_count は log スケールで飽和させる (30 回で概ね 1.0)
MENTION_LOG_BASE: float = 30.0
# recency: 最後に言及されてから N 日経つと 0 に近づく (半減期 90 日)
RECENCY_HALF_LIFE_DAYS: float = 90.0
# session_total_minutes は 600 分 (= 10h) で飽和
SESSION_SATURATION_MIN: float = 600.0
# session は mention 補助 (寄与率)
SESSION_BONUS_RATIO: float = 0.25


@dataclass(frozen=True)
class AnniversaryFeatures:
    """Anniversary importance 推定の入力特徴量。

    Attributes:
        keyword: 記念日 label / keyword
        mention_count: 過去会話中の出現回数
        mean_valence: 平均感情価 (-1.0 to 1.0)
        first_seen_at: ISO8601 文字列 (UTC 推奨)
        last_seen_at: ISO8601 文字列 (UTC 推奨)
        session_total_minutes: 関連会話の累積分
    """

    keyword: str
    mention_count: int
    mean_valence: float
    first_seen_at: str
    last_seen_at: str
    session_total_minutes: float


class ImportanceBucket(Enum):
    """Importance 連続値をカテゴリ化した bucket。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# bucket 閾値 (下限含む) : [0, T_MED) = LOW, [T_MED, T_HIGH) = MEDIUM, ...
BUCKET_THRESHOLD_MEDIUM: float = 0.25
BUCKET_THRESHOLD_HIGH: float = 0.55
BUCKET_THRESHOLD_CRITICAL: float = 0.80


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # 末尾 'Z' 対応
        normalized = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as exc:
        logger.debug("ISO parse failed: %s (%s)", ts, exc)
        return None


def _normalize_mention(mention_count: int, session_total_minutes: float) -> float:
    """mention_count (log scale) + session bonus を [0,1] に。"""
    if mention_count <= 0:
        base = 0.0
    else:
        base = math.log1p(mention_count) / math.log1p(MENTION_LOG_BASE)
    session_norm = _clamp(session_total_minutes / SESSION_SATURATION_MIN)
    # session は mention に対する補正 (最大 25% 寄与)
    combined = base * (1.0 - SESSION_BONUS_RATIO) + session_norm * SESSION_BONUS_RATIO
    return _clamp(combined)


def _normalize_valence(mean_valence: float) -> float:
    """|valence| を [0,1] に (強い負も強い正も記念日として重要)。"""
    return _clamp(abs(mean_valence), 0.0, 1.0)


def _normalize_recency(
    last_seen_at: str, now: Optional[datetime] = None
) -> float:
    """最後に言及された時点からの減衰スコアを [0,1] で返す。

    半減期モデル: score = 0.5 ** (days / HALF_LIFE)
    last_seen が解析不能なら 0.0。
    """
    last_dt = _parse_iso(last_seen_at)
    if last_dt is None:
        return 0.0
    reference = now if now is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    delta_days = (reference - last_dt).total_seconds() / 86400.0
    if delta_days < 0:
        # 未来タイムスタンプは現在として扱う
        delta_days = 0.0
    score = 0.5 ** (delta_days / RECENCY_HALF_LIFE_DAYS)
    return _clamp(score)


def estimate_importance(
    features: AnniversaryFeatures, now: Optional[datetime] = None
) -> float:
    """Anniversary 重要度を 0.0 - 1.0 で推定する。

    重み付き線形結合:
        score = 0.40 * mention_norm + 0.40 * |valence| + 0.20 * recency
    """
    if features.mention_count < 0:
        raise ValueError("mention_count must be >= 0")
    if not -1.0 <= features.mean_valence <= 1.0:
        raise ValueError("mean_valence must be in [-1.0, 1.0]")
    if features.session_total_minutes < 0:
        raise ValueError("session_total_minutes must be >= 0")

    mention_norm = _normalize_mention(
        features.mention_count, features.session_total_minutes
    )
    valence_norm = _normalize_valence(features.mean_valence)
    recency_norm = _normalize_recency(features.last_seen_at, now=now)

    score = (
        WEIGHT_MENTION * mention_norm
        + WEIGHT_VALENCE * valence_norm
        + WEIGHT_RECENCY * recency_norm
    )
    return _clamp(score)


def bucket_of(score: float) -> ImportanceBucket:
    """連続 importance スコアを Bucket に離散化する。"""
    s = _clamp(score)
    if s >= BUCKET_THRESHOLD_CRITICAL:
        return ImportanceBucket.CRITICAL
    if s >= BUCKET_THRESHOLD_HIGH:
        return ImportanceBucket.HIGH
    if s >= BUCKET_THRESHOLD_MEDIUM:
        return ImportanceBucket.MEDIUM
    return ImportanceBucket.LOW


def score_and_bucket(
    features: AnniversaryFeatures, now: Optional[datetime] = None
) -> Tuple[float, ImportanceBucket]:
    """連続 score と Bucket をまとめて返す便宜関数。"""
    score = estimate_importance(features, now=now)
    return score, bucket_of(score)
