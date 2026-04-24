"""Tests for core.conversation_search (Sprint 5.7)."""
from __future__ import annotations

import time
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.conversation_search import (
    ConversationSearchIndex,
    SearchHit,
    SearchQuery,
    to_bigrams,
)


@pytest.fixture
def idx(tmp_path: Path) -> ConversationSearchIndex:
    return ConversationSearchIndex(tmp_path / "search.db")


def _ts(y: int, m: int, d: int, h: int = 12) -> datetime:
    return datetime(y, m, d, h, 0, 0, tzinfo=timezone.utc)


def _seed_basic(idx: ConversationSearchIndex) -> None:
    items = [
        ("t1", _ts(2027, 3, 10), "papa", "今日はペットの話をしました。犬が好きです。"),
        ("t2", _ts(2027, 3, 11), "ai", "ペットを飼うのは素敵ですね。"),
        ("t3", _ts(2027, 3, 12), "papa", "猫も可愛いと思う。"),
        ("t4", _ts(2025, 1, 5), "mama", "pets are wonderful companions"),
        ("t5", _ts(2026, 6, 6), "ai", "Hello world from ai-chan"),
    ]
    idx.index_bulk(items)


def test_empty_index_returns_empty(idx: ConversationSearchIndex) -> None:
    hits = idx.search(SearchQuery(keywords=("anything",)))
    assert hits == ()


def test_single_keyword_match_english(idx: ConversationSearchIndex) -> None:
    _seed_basic(idx)
    hits = idx.search(SearchQuery(keywords=("pets",)))
    assert any(h.turn_id == "t4" for h in hits)


def test_japanese_bigram_pet(idx: ConversationSearchIndex) -> None:
    _seed_basic(idx)
    hits = idx.search(SearchQuery(keywords=("ペット",)))
    ids = {h.turn_id for h in hits}
    assert "t1" in ids and "t2" in ids
    # "ペット" must decompose into bigrams "ペッ" + "ット"
    bg = to_bigrams("ペット")
    assert "ペッ" in bg.split() and "ット" in bg.split()


def test_date_range_filter(idx: ConversationSearchIndex) -> None:
    _seed_basic(idx)
    hits = idx.search(
        SearchQuery(
            keywords=("ペット",),
            date_from=date(2027, 3, 1),
            date_to=date(2027, 3, 31),
        )
    )
    ids = {h.turn_id for h in hits}
    assert ids == {"t1", "t2"}


def test_speaker_filter(idx: ConversationSearchIndex) -> None:
    _seed_basic(idx)
    hits = idx.search(SearchQuery(keywords=("ペット",), speaker="papa"))
    assert {h.turn_id for h in hits} == {"t1"}


def test_multi_keyword_and(idx: ConversationSearchIndex) -> None:
    _seed_basic(idx)
    hits = idx.search(SearchQuery(keywords=("ペット", "犬"), mode="AND"))
    assert {h.turn_id for h in hits} == {"t1"}


def test_multi_keyword_or(idx: ConversationSearchIndex) -> None:
    _seed_basic(idx)
    hits = idx.search(SearchQuery(keywords=("犬", "猫"), mode="OR"))
    ids = {h.turn_id for h in hits}
    assert "t1" in ids and "t3" in ids


def test_recency_boost_orders_newer_first(
    idx: ConversationSearchIndex,
) -> None:
    idx.index_bulk(
        [
            ("old", _ts(2018, 1, 1), "papa", "memory token alpha"),
            ("new", _ts(2026, 1, 1), "papa", "memory token alpha"),
        ]
    )
    hits = idx.search(SearchQuery(keywords=("alpha",)))
    assert hits[0].turn_id == "new"


def test_limit_is_respected(idx: ConversationSearchIndex) -> None:
    items = [
        (f"r{i}", _ts(2027, 3, 10 + (i % 10)), "papa", f"alpha common {i}")
        for i in range(30)
    ]
    idx.index_bulk(items)
    hits = idx.search(SearchQuery(keywords=("common",), limit=7))
    assert len(hits) == 7


def test_context_before_after(idx: ConversationSearchIndex) -> None:
    items = [
        ("a", _ts(2027, 3, 10, 9), "papa", "one"),
        ("b", _ts(2027, 3, 10, 10), "ai", "two"),
        ("c", _ts(2027, 3, 10, 11), "papa", "target alpha"),
        ("d", _ts(2027, 3, 10, 12), "ai", "four"),
        ("e", _ts(2027, 3, 10, 13), "papa", "five"),
    ]
    idx.index_bulk(items)
    hits = idx.search(SearchQuery(keywords=("alpha",)))
    assert hits
    h = hits[0]
    assert h.turn_id == "c"
    assert len(h.context_before) == 2
    assert len(h.context_after) == 2
    assert "one" in h.context_before[0]
    assert "five" in h.context_after[1]


def test_sql_injection_safe(idx: ConversationSearchIndex) -> None:
    _seed_basic(idx)
    hostile = "'; DROP TABLE turns; --"
    hits = idx.search(SearchQuery(keywords=(hostile,)))
    # Should not raise; and the table must still exist.
    assert isinstance(hits, tuple)
    # Re-query to confirm data is intact.
    hits2 = idx.search(SearchQuery(keywords=("ペット",)))
    assert len(hits2) >= 1


def test_bulk_10k_perf(idx: ConversationSearchIndex) -> None:
    base = _ts(2020, 1, 1)
    items = [
        (
            f"b{i}",
            base + timedelta(minutes=i),
            "papa" if i % 2 == 0 else "ai",
            f"message number {i} alpha" if i % 100 == 0 else f"message {i}",
        )
        for i in range(10_000)
    ]
    t0 = time.perf_counter()
    idx.index_bulk(items)
    elapsed = time.perf_counter() - t0
    # Generous sanity bound; on a typical dev machine this is <5s.
    assert elapsed < 30.0, f"10k index took {elapsed:.2f}s"
    hits = idx.search(SearchQuery(keywords=("alpha",), limit=5))
    assert len(hits) == 5


def test_frozen_dataclasses_py39() -> None:
    q = SearchQuery(keywords=("x",))
    h = SearchHit(
        turn_id="t",
        timestamp=_ts(2027, 1, 1),
        speaker="papa",
        text="hi",
        score=1.0,
    )
    with pytest.raises(FrozenInstanceError):
        q.keywords = ("y",)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        h.score = 2.0  # type: ignore[misc]
