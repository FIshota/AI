"""core.anniversary_importance のユニットテスト。"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from core.anniversary_importance import (
    BUCKET_THRESHOLD_CRITICAL,
    BUCKET_THRESHOLD_HIGH,
    BUCKET_THRESHOLD_MEDIUM,
    AnniversaryFeatures,
    ImportanceBucket,
    bucket_of,
    estimate_importance,
    score_and_bucket,
)


NOW = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)


def _features(
    *,
    keyword: str = "anniv",
    mention_count: int = 0,
    mean_valence: float = 0.0,
    days_ago: float = 0.0,
    session_total_minutes: float = 0.0,
) -> AnniversaryFeatures:
    last_seen = (NOW - timedelta(days=days_ago)).isoformat()
    first_seen = (NOW - timedelta(days=days_ago + 30)).isoformat()
    return AnniversaryFeatures(
        keyword=keyword,
        mention_count=mention_count,
        mean_valence=mean_valence,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        session_total_minutes=session_total_minutes,
    )


@pytest.mark.unit
def test_frozen_dataclass_is_immutable() -> None:
    f = _features()
    with pytest.raises(FrozenInstanceError):
        f.mention_count = 99  # type: ignore[misc]


@pytest.mark.unit
def test_zero_mention_zero_valence_recent_returns_only_recency() -> None:
    f = _features(mention_count=0, mean_valence=0.0, days_ago=0)
    score = estimate_importance(f, now=NOW)
    # recency は 1.0, 他 0 -> score ≈ 0.20
    assert 0.18 <= score <= 0.22


@pytest.mark.unit
def test_zero_mention_with_unparsable_last_seen_is_zero() -> None:
    f = AnniversaryFeatures(
        keyword="x",
        mention_count=0,
        mean_valence=0.0,
        first_seen_at="",
        last_seen_at="",
        session_total_minutes=0.0,
    )
    score = estimate_importance(f, now=NOW)
    assert score == 0.0
    assert bucket_of(score) is ImportanceBucket.LOW


@pytest.mark.unit
def test_strong_positive_valence_raises_score() -> None:
    f_pos = _features(mean_valence=0.9, days_ago=1000)
    score = estimate_importance(f_pos, now=NOW)
    # valence 0.9 * 0.40 = 0.36 以上
    assert score >= 0.35


@pytest.mark.unit
def test_strong_negative_valence_equivalent_to_positive() -> None:
    """重要度は |valence| で扱うため正負対称。"""
    f_pos = _features(mean_valence=0.8, days_ago=365)
    f_neg = _features(mean_valence=-0.8, days_ago=365)
    assert estimate_importance(f_pos, now=NOW) == pytest.approx(
        estimate_importance(f_neg, now=NOW)
    )


@pytest.mark.unit
def test_high_mention_count_pushes_toward_one() -> None:
    f = _features(
        mention_count=200,
        mean_valence=1.0,
        days_ago=0,
        session_total_minutes=600.0,
    )
    score = estimate_importance(f, now=NOW)
    assert score >= 0.9


@pytest.mark.unit
def test_weight_sum_equals_one() -> None:
    """重みの線形結合が [0,1] に収まることを端値で確認。"""
    # すべて 0
    f_zero = AnniversaryFeatures("x", 0, 0.0, "", "", 0.0)
    assert estimate_importance(f_zero, now=NOW) == 0.0
    # すべて最大 (|valence|=1, mention 大, recency=現在)
    f_max = _features(
        mention_count=10_000,
        mean_valence=1.0,
        days_ago=0,
        session_total_minutes=10_000.0,
    )
    s = estimate_importance(f_max, now=NOW)
    assert 0.99 <= s <= 1.0


@pytest.mark.unit
def test_recency_decay_half_life() -> None:
    """半減期 90 日で recency が半分になること。"""
    f_now = _features(mean_valence=0.0, mention_count=0, days_ago=0)
    f_90 = _features(mean_valence=0.0, mention_count=0, days_ago=90)
    f_180 = _features(mean_valence=0.0, mention_count=0, days_ago=180)
    s_now = estimate_importance(f_now, now=NOW)
    s_90 = estimate_importance(f_90, now=NOW)
    s_180 = estimate_importance(f_180, now=NOW)
    assert s_now > s_90 > s_180
    # 0.20 * 1.0 vs 0.20 * 0.5 vs 0.20 * 0.25
    assert s_90 == pytest.approx(0.10, abs=0.01)
    assert s_180 == pytest.approx(0.05, abs=0.01)


@pytest.mark.unit
def test_bucket_boundaries() -> None:
    assert bucket_of(0.0) is ImportanceBucket.LOW
    assert bucket_of(BUCKET_THRESHOLD_MEDIUM - 1e-6) is ImportanceBucket.LOW
    assert bucket_of(BUCKET_THRESHOLD_MEDIUM) is ImportanceBucket.MEDIUM
    assert bucket_of(BUCKET_THRESHOLD_HIGH - 1e-6) is ImportanceBucket.MEDIUM
    assert bucket_of(BUCKET_THRESHOLD_HIGH) is ImportanceBucket.HIGH
    assert bucket_of(BUCKET_THRESHOLD_CRITICAL - 1e-6) is ImportanceBucket.HIGH
    assert bucket_of(BUCKET_THRESHOLD_CRITICAL) is ImportanceBucket.CRITICAL
    assert bucket_of(1.0) is ImportanceBucket.CRITICAL


@pytest.mark.unit
def test_bucket_clamps_out_of_range_values() -> None:
    assert bucket_of(-0.5) is ImportanceBucket.LOW
    assert bucket_of(5.0) is ImportanceBucket.CRITICAL


@pytest.mark.unit
def test_score_and_bucket_consistency() -> None:
    f = _features(mention_count=50, mean_valence=0.6, days_ago=10)
    score, bucket = score_and_bucket(f, now=NOW)
    assert 0.0 <= score <= 1.0
    assert bucket is bucket_of(score)


@pytest.mark.unit
def test_invalid_valence_raises() -> None:
    with pytest.raises(ValueError):
        estimate_importance(
            AnniversaryFeatures("x", 1, 1.5, NOW.isoformat(), NOW.isoformat(), 0.0),
            now=NOW,
        )


@pytest.mark.unit
def test_invalid_mention_count_raises() -> None:
    with pytest.raises(ValueError):
        estimate_importance(
            AnniversaryFeatures("x", -1, 0.0, NOW.isoformat(), NOW.isoformat(), 0.0),
            now=NOW,
        )


@pytest.mark.unit
def test_session_minutes_boost_is_capped() -> None:
    """session_total_minutes は飽和して青天井にはならない。"""
    f_low_session = _features(mention_count=5, mean_valence=0.0, session_total_minutes=0.0)
    f_high_session = _features(
        mention_count=5, mean_valence=0.0, session_total_minutes=10_000.0
    )
    s_low = estimate_importance(f_low_session, now=NOW)
    s_high = estimate_importance(f_high_session, now=NOW)
    assert s_high > s_low
    assert s_high <= 1.0


@pytest.mark.unit
def test_future_last_seen_treated_as_now() -> None:
    """タイムスタンプが未来でも recency は最大 (= 現在扱い)。"""
    future = (NOW + timedelta(days=10)).isoformat()
    f = AnniversaryFeatures(
        keyword="x",
        mention_count=0,
        mean_valence=0.0,
        first_seen_at=NOW.isoformat(),
        last_seen_at=future,
        session_total_minutes=0.0,
    )
    score = estimate_importance(f, now=NOW)
    assert 0.18 <= score <= 0.22
