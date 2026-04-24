"""Tests for Lifelong Memory Module (LMM) PoC skeleton."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure project root on path when running pytest from any directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lifelong_memory import (  # noqa: E402
    ALLOWED_KINDS,
    MemoryEvent,
    MemoryStore,
    new_event,
    with_importance,
    _char_ngrams,
    _cosine,
    _tfidf,
)
from core.lifelong_memory_policy import (  # noqa: E402
    RetentionPolicy,
    filter_retainable,
    should_retain,
)


# ── fixtures ────────────────────────────────────────────────────────────
@pytest.fixture
def store(tmp_path):
    s = MemoryStore(tmp_path / "lmm.sqlite3", half_life_days=30.0)
    yield s
    s.close()


def _seed(store: MemoryStore) -> list:
    evs = [
        new_event("yamato", "event", "初めて一緒に散歩した日、桜が満開だった",
                  tags=("散歩", "桜"), importance=0.9),
        new_event("yamato", "preference", "抹茶アイスが大好き",
                  tags=("food",), importance=0.7),
        new_event("yamato", "person", "母と電話で長話をした",
                  tags=("family",), importance=0.6),
        new_event("yamato", "event", "雨の日に図書館で本を読んだ",
                  tags=("読書",), importance=0.5),
        new_event("yamato", "trend", "最近ずっと機嫌が良い",
                  tags=("mood",), importance=0.4),
    ]
    for e in evs:
        store.retain(e)
    return evs


# ── dataclass & validation ──────────────────────────────────────────────
def test_memory_event_is_frozen():
    ev = new_event("s1", "event", "hello")
    with pytest.raises(Exception):
        ev.content = "changed"  # type: ignore[misc]


def test_memory_event_rejects_invalid_kind():
    with pytest.raises(ValueError):
        MemoryEvent(
            id="x", subject_id="s", kind="bogus", content="c",
            ts="2026-01-01T00:00:00+00:00",
        )


def test_memory_event_bounds():
    with pytest.raises(ValueError):
        new_event("s", "event", "c", confidence=1.5)
    with pytest.raises(ValueError):
        new_event("s", "event", "c", importance=-0.1)


def test_with_importance_is_immutable():
    ev = new_event("s", "event", "c", importance=0.5)
    ev2 = with_importance(ev, 0.9)
    assert ev.importance == 0.5
    assert ev2.importance == 0.9
    assert ev.id == ev2.id


# ── TF-IDF helpers ──────────────────────────────────────────────────────
def test_char_ngrams_japanese():
    grams = _char_ngrams("抹茶アイス")
    assert "抹茶" in grams and "茶ア" in grams
    assert all(len(g) == 2 for g in grams)


def test_cosine_identity_and_zero():
    assert _cosine({}, {"a": 1}) == 0.0
    a = {"x": 1.0, "y": 2.0}
    assert _cosine(a, a) == pytest.approx(1.0)


def test_tfidf_shapes():
    q, docs = _tfidf(["a", "b"], [["a", "b"], ["c"]])
    assert set(q.keys()) == {"a", "b"}
    assert len(docs) == 2


# ── retain / recall ─────────────────────────────────────────────────────
def test_retain_and_all_events(store):
    events = _seed(store)
    got = store.all_events(subject_id="yamato")
    assert len(got) == len(events)
    assert {e.id for e in got} == {e.id for e in events}


def test_recall_finds_top_matches(store):
    _seed(store)
    hits = store.recall("抹茶 アイス 好き", k=3)
    assert len(hits) >= 1
    # top hit should be the preference one
    assert "抹茶" in hits[0].content


def test_recall_respects_kind_filter(store):
    _seed(store)
    hits = store.recall("散歩 桜", k=5, kind_filter=["event"])
    assert all(h.kind == "event" for h in hits)
    assert any("桜" in h.content for h in hits)


def test_recall_empty_query_returns_empty(store):
    _seed(store)
    assert store.recall("", k=3) == []


def test_recall_top3_from_5_smoke(store):
    _seed(store)
    hits = store.recall("桜 散歩 図書館", k=3)
    assert 1 <= len(hits) <= 3


# ── forget / purge (kill-switch) ────────────────────────────────────────
def test_forget_single(store):
    events = _seed(store)
    target = events[0]
    assert store.forget(target.id) is True
    remaining = store.all_events(subject_id="yamato")
    assert target.id not in {e.id for e in remaining}
    # idempotent
    assert store.forget(target.id) is False


def test_purge_subject(store):
    _seed(store)
    other = new_event("other", "event", "another subject")
    store.retain(other)
    n = store.purge("yamato")
    assert n >= 5
    assert store.all_events(subject_id="yamato") == []
    assert len(store.all_events(subject_id="other")) == 1


# ── importance decay ────────────────────────────────────────────────────
def test_importance_decay_reduces_old_events(tmp_path):
    s = MemoryStore(tmp_path / "d.sqlite3", half_life_days=10.0)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(timespec="seconds")
    old = new_event("s", "event", "古い記憶", importance=0.8, ts=old_ts)
    fresh = new_event("s", "event", "今の記憶", importance=0.8)
    s.retain(old)
    s.retain(fresh)
    updated = s.importance_decay()
    assert updated >= 1
    ev_map = {e.id: e for e in s.all_events()}
    assert ev_map[old.id].importance < 0.8
    # ~20d with 10d half-life → ~0.25x
    assert ev_map[old.id].importance == pytest.approx(0.8 * 0.25, rel=0.2)
    s.close()


# ── encryption hook ─────────────────────────────────────────────────────
def test_encryption_hooks_round_trip(tmp_path):
    def enc(t: str) -> str:
        return "E:" + t[::-1]

    def dec(t: str) -> str:
        assert t.startswith("E:")
        return t[2:][::-1]

    s = MemoryStore(tmp_path / "enc.sqlite3", encrypt=enc, decrypt=dec)
    ev = new_event("s", "event", "暗号化テスト", importance=0.5)
    s.retain(ev)
    got = s.all_events()[0]
    assert got.content == "暗号化テスト"
    s.close()


# ── policy ──────────────────────────────────────────────────────────────
def test_should_retain_defaults():
    ev = new_event("s", "event", "meaningful", importance=0.5, confidence=0.9)
    assert should_retain(ev) is True


def test_should_retain_rejects_low_importance():
    ev = new_event("s", "event", "c", importance=0.05, confidence=0.9)
    assert should_retain(ev) is False


def test_should_retain_rejects_blocklisted_tag():
    ev = new_event("s", "event", "c", tags=("medical",),
                   importance=0.9, confidence=0.9)
    policy = RetentionPolicy(blocklist_tags=frozenset({"medical"}))
    assert should_retain(ev, policy) is False


def test_should_retain_requires_consent_when_configured():
    ev = new_event("s1", "event", "c", importance=0.9, confidence=0.9)
    policy = RetentionPolicy(consenting_subjects=frozenset({"s2"}))
    assert should_retain(ev, policy) is False
    policy2 = RetentionPolicy(consenting_subjects=frozenset({"s1"}))
    assert should_retain(ev, policy2) is True


def test_filter_retainable_filters():
    evs = [
        new_event("s", "event", "ok", importance=0.9, confidence=0.9),
        new_event("s", "event", "", importance=0.9, confidence=0.9),
        new_event("s", "event", "low", importance=0.01, confidence=0.9),
    ]
    out = list(filter_retainable(evs))
    assert len(out) == 1 and out[0].content == "ok"


def test_allowed_kinds_are_locked_down():
    assert set(ALLOWED_KINDS) == {"event", "person", "preference", "trend"}
