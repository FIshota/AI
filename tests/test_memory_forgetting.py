"""Tests for core.memory_forgetting (Ebbinghaus + pin)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from core.memory_forgetting import (
    DEFAULT_PARAMS,
    ForgettingCurveParams,
    ForgettingPolicy,
    MemoryEntry,
    retention_score,
)


# ---- retention_score ------------------------------------------------------


@pytest.mark.unit
def test_retention_zero_elapsed_is_one():
    assert retention_score(0.0) == 1.0
    assert retention_score(-3.0) == 1.0


@pytest.mark.unit
def test_retention_monotonic_decreasing():
    prev = 1.0
    for d in [0.5, 1, 2, 4, 8, 16, 32, 64, 128]:
        cur = retention_score(float(d))
        assert cur <= prev
        prev = cur
    assert prev < 0.01


@pytest.mark.unit
def test_retention_bounds():
    for d in [0.0, 1.0, 10.0, 1000.0, 1e9]:
        s = retention_score(d)
        assert 0.0 <= s <= 1.0


@pytest.mark.unit
def test_rehearsal_boosts_retention():
    t = 14.0
    base = retention_score(t, rehearsals=0)
    boosted = retention_score(t, rehearsals=5)
    assert boosted > base


@pytest.mark.unit
def test_negative_rehearsals_clamped():
    t = 14.0
    a = retention_score(t, rehearsals=0)
    b = retention_score(t, rehearsals=-10)
    assert a == pytest.approx(b)


@pytest.mark.unit
def test_retention_matches_closed_form():
    params = ForgettingCurveParams(
        initial_strength=1.0, half_life_days=7.0, rehearsal_boost=0.5
    )
    t = 7.0
    expected = math.exp(-t / (1.0 * 7.0 * 1.0))
    assert retention_score(t, 0, params) == pytest.approx(expected)


# ---- params validation ----------------------------------------------------


@pytest.mark.unit
def test_params_validation():
    with pytest.raises(ValueError):
        ForgettingCurveParams(initial_strength=0)
    with pytest.raises(ValueError):
        ForgettingCurveParams(half_life_days=-1.0)
    with pytest.raises(ValueError):
        ForgettingCurveParams(rehearsal_boost=-0.1)


@pytest.mark.unit
def test_policy_threshold_validation():
    with pytest.raises(ValueError):
        ForgettingPolicy(threshold=-0.1)
    with pytest.raises(ValueError):
        ForgettingPolicy(threshold=1.5)


# ---- ForgettingPolicy -----------------------------------------------------


def _entry(days_old: float, rehearsals: int = 0, pinned: bool = False, eid=1):
    now = datetime(2030, 1, 1, 12, 0, 0)
    created = now - timedelta(days=days_old)
    return MemoryEntry(
        id=eid,
        created_at=created,
        last_rehearsed_at=created,
        rehearsal_count=rehearsals,
        pinned=pinned,
    ), now


@pytest.mark.unit
def test_pinned_never_forgotten():
    entry, now = _entry(days_old=365 * 10, rehearsals=0, pinned=True)
    pol = ForgettingPolicy(threshold=0.99)
    assert pol.should_forget(entry, now) is False
    assert pol.score(entry, now) == 1.0


@pytest.mark.unit
def test_fresh_entry_kept():
    entry, now = _entry(days_old=0.1)
    pol = ForgettingPolicy(threshold=0.2)
    assert pol.should_forget(entry, now) is False


@pytest.mark.unit
def test_old_entry_forgotten():
    entry, now = _entry(days_old=200, rehearsals=0)
    pol = ForgettingPolicy(threshold=0.2)
    assert pol.should_forget(entry, now) is True


@pytest.mark.unit
def test_threshold_boundary():
    # threshold=0 means nothing is ever forgotten (retention < 0 never true).
    entry, now = _entry(days_old=10_000)
    pol = ForgettingPolicy(threshold=0.0)
    assert pol.should_forget(entry, now) is False


@pytest.mark.unit
def test_threshold_one_forgets_everything_unpinned():
    entry, now = _entry(days_old=0.001)
    pol = ForgettingPolicy(threshold=1.0)
    # R < 1 の何でも忘却.
    assert pol.should_forget(entry, now) is True


@pytest.mark.unit
def test_apply_partitions_correctly():
    now = datetime(2030, 1, 1)
    es = [
        MemoryEntry(id=1, created_at=now - timedelta(days=1), last_rehearsed_at=now - timedelta(days=1), rehearsal_count=0, pinned=False),
        MemoryEntry(id=2, created_at=now - timedelta(days=500), last_rehearsed_at=now - timedelta(days=500), rehearsal_count=0, pinned=False),
        MemoryEntry(id=3, created_at=now - timedelta(days=500), last_rehearsed_at=now - timedelta(days=500), rehearsal_count=0, pinned=True),
    ]
    pol = ForgettingPolicy(threshold=0.2)
    kept, forgotten = pol.apply(es, now=now)
    kept_ids = {e.id for e in kept}
    forgotten_ids = {e.id for e in forgotten}
    assert 1 in kept_ids
    assert 3 in kept_ids  # pinned
    assert 2 in forgotten_ids


@pytest.mark.unit
def test_apply_does_not_mutate_input():
    now = datetime(2030, 1, 1)
    es = [
        MemoryEntry(id=i, created_at=now - timedelta(days=500),
                    last_rehearsed_at=now - timedelta(days=500),
                    rehearsal_count=0, pinned=False)
        for i in range(5)
    ]
    original = list(es)
    pol = ForgettingPolicy(threshold=0.2)
    pol.apply(es, now=now)
    assert es == original


@pytest.mark.unit
def test_rehearsal_saves_entry_at_boundary():
    now = datetime(2030, 1, 1)
    created = now - timedelta(days=30)
    no_reh = MemoryEntry(id=1, created_at=created, last_rehearsed_at=created,
                         rehearsal_count=0, pinned=False)
    many_reh = MemoryEntry(id=2, created_at=created, last_rehearsed_at=created,
                           rehearsal_count=20, pinned=False)
    pol = ForgettingPolicy(threshold=0.2)
    assert pol.should_forget(no_reh, now) is True
    assert pol.should_forget(many_reh, now) is False


@pytest.mark.unit
def test_last_rehearsed_drives_decay_not_created():
    now = datetime(2030, 1, 1)
    created = now - timedelta(days=365)
    rehearsed = now - timedelta(days=1)
    e = MemoryEntry(id=1, created_at=created, last_rehearsed_at=rehearsed,
                    rehearsal_count=1, pinned=False)
    pol = ForgettingPolicy(threshold=0.2)
    assert pol.should_forget(e, now) is False


@pytest.mark.unit
def test_score_extreme_age_is_near_zero():
    now = datetime(2030, 1, 1)
    created = now - timedelta(days=100_000)
    e = MemoryEntry(id=1, created_at=created, last_rehearsed_at=created,
                    rehearsal_count=0, pinned=False)
    pol = ForgettingPolicy(threshold=0.2)
    s = pol.score(e, now)
    assert 0.0 <= s < 1e-9
