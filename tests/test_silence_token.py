"""
tests for core/silence_token.py, core/silence_emotion_bridge.py, core/silence_turn.py
"""
from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta

import pytest

from core.emotion import EmotionState
from core.silence_emotion_bridge import apply_silence_to_emotion
from core.silence_token import (
    SilenceCategory,
    SilenceClassifier,
    SilenceDetector,
    SilenceEvent,
)
from core.silence_turn import SILENCE_SPEAKER, silence_event_to_turn


# --------------------------- classifier boundaries ---------------------------

def test_py39_compatible():
    assert sys.version_info >= (3, 9)


def test_classify_below_micro_returns_none():
    assert SilenceClassifier.classify(0.0) is None
    assert SilenceClassifier.classify(2.999) is None


def test_classify_micro_boundary():
    assert SilenceClassifier.classify(3.0) is SilenceCategory.MICRO
    assert SilenceClassifier.classify(14.999) is SilenceCategory.MICRO
    # 15s は MICRO ではなく SHORT
    assert SilenceClassifier.classify(15.0) is SilenceCategory.SHORT


def test_classify_short_boundary():
    assert SilenceClassifier.classify(15.0) is SilenceCategory.SHORT
    assert SilenceClassifier.classify(119.999) is SilenceCategory.SHORT
    assert SilenceClassifier.classify(120.0) is SilenceCategory.MEDIUM


def test_classify_medium_boundary():
    assert SilenceClassifier.classify(120.0) is SilenceCategory.MEDIUM
    assert SilenceClassifier.classify(30 * 60 - 0.001) is SilenceCategory.MEDIUM
    assert SilenceClassifier.classify(30 * 60) is SilenceCategory.LONG


def test_classify_long_boundary():
    assert SilenceClassifier.classify(30 * 60) is SilenceCategory.LONG
    assert SilenceClassifier.classify(3 * 60 * 60 - 0.001) is SilenceCategory.LONG
    assert SilenceClassifier.classify(3 * 60 * 60) is SilenceCategory.ABSENT


def test_classify_absent():
    assert SilenceClassifier.classify(3 * 60 * 60) is SilenceCategory.ABSENT
    assert SilenceClassifier.classify(24 * 60 * 60) is SilenceCategory.ABSENT


# --------------------------- SilenceEvent invariants ---------------------------

def test_silence_event_is_frozen():
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    t1 = t0 + timedelta(seconds=60)
    ev = SilenceEvent(
        started_at=t0, ended_at=t1, duration_s=60.0,
        category=SilenceCategory.SHORT, ambient_context=None,
    )
    with pytest.raises(FrozenInstanceError):
        ev.duration_s = 999  # type: ignore[misc]


def test_silence_event_invariant_started_before_ended():
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    t1 = t0 - timedelta(seconds=1)
    with pytest.raises(ValueError):
        SilenceEvent(
            started_at=t0, ended_at=t1, duration_s=1.0,
            category=SilenceCategory.MICRO,
        )


# --------------------------- Detector state machine ---------------------------

def test_detector_emits_on_activity_after_silence():
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    events = []
    det = SilenceDetector(on_emit=events.append)
    det.on_user_activity(t0)
    # 60 秒後にユーザーが再度喋る → SHORT event が確定
    t1 = t0 + timedelta(seconds=60)
    det.on_user_activity(t1)
    assert len(events) == 1
    assert events[0].category is SilenceCategory.SHORT
    assert events[0].duration_s == pytest.approx(60.0)


def test_detector_activity_resets_state():
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    events = []
    det = SilenceDetector(on_emit=events.append)
    det.on_user_activity(t0)
    # tick で SHORT を emit
    det.on_tick(t0 + timedelta(seconds=30))
    assert len(events) == 1
    # アクティビティで reset (このとき SHORT 区間の確定 event が出る)
    det.on_user_activity(t0 + timedelta(seconds=40))
    # reset 直後の短い間隔は何も emit しない
    det.on_tick(t0 + timedelta(seconds=41))
    # reset 後は last_emitted_category がクリアされている
    assert det._last_emitted_category is None


def test_detector_tick_emits_when_threshold_crossed():
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    events = []
    det = SilenceDetector(on_emit=events.append)
    det.on_user_activity(t0)
    det.on_tick(t0 + timedelta(seconds=5))   # MICRO
    det.on_tick(t0 + timedelta(seconds=20))  # SHORT
    det.on_tick(t0 + timedelta(seconds=200)) # MEDIUM
    cats = [e.category for e in events]
    assert cats == [SilenceCategory.MICRO, SilenceCategory.SHORT, SilenceCategory.MEDIUM]


def test_detector_absent_not_spammed():
    """長時間不在後の ABSENT 復帰で 1 event に集約されること。"""
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    events = []
    det = SilenceDetector(on_emit=events.append)
    det.on_user_activity(t0)
    # 5 時間後に ABSENT 閾値をまたぎつつ、途中で何度 tick されても ABSENT は 1 回
    det.on_tick(t0 + timedelta(hours=4))
    det.on_tick(t0 + timedelta(hours=4, minutes=30))
    det.on_tick(t0 + timedelta(hours=5))
    absent_events = [e for e in events if e.category is SilenceCategory.ABSENT]
    assert len(absent_events) == 1


# --------------------------- emotion bridge ---------------------------

def _mkev(category, duration, context=None):
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    return SilenceEvent(
        started_at=t0,
        ended_at=t0 + timedelta(seconds=duration),
        duration_s=duration,
        category=category,
        ambient_context=context,
    )


def test_absent_during_sleep_has_no_emotional_impact():
    base = EmotionState()
    ev = _mkev(SilenceCategory.ABSENT, 8 * 3600, context="就寝中")
    new = apply_silence_to_emotion(base, ev)
    assert new.anxiety == pytest.approx(base.anxiety)
    assert new.happiness == pytest.approx(base.happiness)


def test_medium_with_working_together_increases_affection():
    base = EmotionState(affection=0.5)
    ev = _mkev(SilenceCategory.MEDIUM, 600, context="作業中同席")
    new = apply_silence_to_emotion(base, ev)
    assert new.affection == pytest.approx(0.55)


def test_absent_default_raises_anxiety_lowers_happiness():
    base = EmotionState(anxiety=0.1, happiness=0.7)
    ev = _mkev(SilenceCategory.ABSENT, 4 * 3600)
    new = apply_silence_to_emotion(base, ev)
    assert new.anxiety == pytest.approx(0.25)
    assert new.happiness == pytest.approx(0.60)


def test_emotion_state_is_not_mutated():
    """immutable update: 原本が壊れないこと。"""
    base = EmotionState(anxiety=0.1, happiness=0.7)
    snapshot = (base.anxiety, base.happiness, base.affection, base.curiosity, base.energy)
    ev = _mkev(SilenceCategory.ABSENT, 4 * 3600)
    new = apply_silence_to_emotion(base, ev)
    assert (base.anxiety, base.happiness, base.affection, base.curiosity, base.energy) == snapshot
    # 別インスタンスであること
    assert new is not base


def test_micro_has_no_effect():
    base = EmotionState()
    ev = _mkev(SilenceCategory.MICRO, 10)
    new = apply_silence_to_emotion(base, ev)
    assert new.to_dict() == base.to_dict()


def test_short_raises_curiosity_slightly():
    base = EmotionState(curiosity=0.5)
    ev = _mkev(SilenceCategory.SHORT, 60)
    new = apply_silence_to_emotion(base, ev)
    assert new.curiosity == pytest.approx(0.52)


def test_long_raises_anxiety_lowers_energy():
    base = EmotionState(anxiety=0.1, energy=0.7)
    ev = _mkev(SilenceCategory.LONG, 60 * 60)
    new = apply_silence_to_emotion(base, ev)
    assert new.anxiety == pytest.approx(0.15)
    assert new.energy == pytest.approx(0.67)


# --------------------------- turn conversion ---------------------------

def test_silence_event_to_turn_format():
    t0 = datetime(2026, 4, 24, 10, 0, 0)
    t1 = t0 + timedelta(seconds=180)
    ev = SilenceEvent(
        started_at=t0, ended_at=t1, duration_s=180.0,
        category=SilenceCategory.MEDIUM, ambient_context="作業中同席",
    )
    turn = silence_event_to_turn(ev)
    assert turn["speaker"] == SILENCE_SPEAKER
    assert turn["speaker"] == "_silence_"
    assert turn["text"] == "<silence:medium:180s>"
    assert turn["timestamp"] == t1.isoformat()
    assert "turn_id" in turn and isinstance(turn["turn_id"], str) and len(turn["turn_id"]) > 0
    meta = turn["meta"]
    assert meta["category"] == "medium"
    assert meta["duration_s"] == pytest.approx(180.0)
    assert meta["ambient_context"] == "作業中同席"
    assert meta["started_at"] == t0.isoformat()
    assert meta["ended_at"] == t1.isoformat()
