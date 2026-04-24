"""Tests for core.voice_id_fallback."""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError

import pytest

from core.voice_id_fallback import (
    ChallengeSet,
    DriftDetector,
    FallbackPolicy,
    VoiceMatch,
    load_challenges_from_yaml,
)


# ---------------------------------------------------------------------------
# VoiceMatch
# ---------------------------------------------------------------------------


def test_voice_match_is_frozen():
    vm = VoiceMatch(
        claimed_subject_id="papa", confidence=0.9, utterance="おはよう"
    )
    with pytest.raises(FrozenInstanceError):
        vm.confidence = 0.1  # type: ignore[misc]


def test_voice_match_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        VoiceMatch(claimed_subject_id="papa", confidence=1.5, utterance="x")
    with pytest.raises(ValueError):
        VoiceMatch(claimed_subject_id="papa", confidence=-0.1, utterance="x")


def test_voice_match_rejects_empty_subject():
    with pytest.raises(ValueError):
        VoiceMatch(claimed_subject_id="", confidence=0.8, utterance="x")


# ---------------------------------------------------------------------------
# DriftDetector
# ---------------------------------------------------------------------------


def test_drift_cold_start_returns_zero():
    d = DriftDetector()
    assert d.score("こんにちは、今日は暑いですね", "papa") == 0.0


def test_drift_low_for_consistent_speaker():
    d = DriftDetector()
    for u in [
        "おはよう、今日もいい天気だね",
        "おはよう、今日は仕事だ",
        "おはよう、朝ごはんは何？",
    ]:
        d.observe("papa", u)
    score = d.score("おはよう、今日は少し寒いね", "papa")
    assert score < 0.5


def test_drift_high_for_divergent_topic_and_length():
    d = DriftDetector()
    for u in [
        "おはよう、今日もいい天気だね",
        "おはよう、今日は仕事だ",
        "おはよう、朝ごはんは何？",
    ]:
        d.observe("papa", u)
    # Completely different topic, length, style.
    score = d.score(
        "株式市場における流動性供給の最適化アルゴリズムについて論じます",
        "papa",
    )
    assert score > 0.5


def test_drift_reset_specific_subject():
    d = DriftDetector()
    d.observe("papa", "おはよう")
    d.observe("mama", "こんばんは")
    d.reset("papa")
    # papa becomes cold-start again
    assert d.score("全然違う話題です", "papa") == 0.0
    # mama still has profile
    assert d.score("全然違う話題です", "mama") >= 0.0


def test_drift_history_size_validation():
    with pytest.raises(ValueError):
        DriftDetector(history_size=0)


# ---------------------------------------------------------------------------
# FallbackPolicy - thresholds
# ---------------------------------------------------------------------------


def _default_challenges() -> dict:
    return {
        "papa": ChallengeSet(
            passphrases=("やまとのたからもの",),
            questions=(
                ("最初に一緒に行った旅行先は？", "はこだて"),
                ("ペットの名前は？", "ぽち"),
            ),
        ),
        "mama": ChallengeSet(
            passphrases=("つきのひかり",),
            questions=(("結婚記念日の月は？", "6月"),),
        ),
    }


def test_should_challenge_low_confidence():
    p = FallbackPolicy(_default_challenges())
    vm = VoiceMatch(
        claimed_subject_id="papa", confidence=0.5, utterance="おはよう"
    )
    assert p.should_challenge(vm, drift=0.0) is True


def test_should_challenge_high_drift():
    p = FallbackPolicy(_default_challenges())
    vm = VoiceMatch(
        claimed_subject_id="papa", confidence=0.95, utterance="おはよう"
    )
    assert p.should_challenge(vm, drift=0.8) is True


def test_should_not_challenge_when_both_safe():
    p = FallbackPolicy(_default_challenges())
    vm = VoiceMatch(
        claimed_subject_id="papa", confidence=0.9, utterance="おはよう"
    )
    assert p.should_challenge(vm, drift=0.1) is False


def test_boundary_confidence_exact_threshold():
    # confidence == 0.7 is considered safe (strict <)
    p = FallbackPolicy(_default_challenges())
    vm = VoiceMatch(
        claimed_subject_id="papa", confidence=0.7, utterance="おはよう"
    )
    assert p.should_challenge(vm, drift=0.0) is False


def test_boundary_drift_exact_threshold():
    # drift == 0.5 is considered safe (strict >)
    p = FallbackPolicy(_default_challenges())
    vm = VoiceMatch(
        claimed_subject_id="papa", confidence=0.9, utterance="おはよう"
    )
    assert p.should_challenge(vm, drift=0.5) is False


# ---------------------------------------------------------------------------
# FallbackPolicy - challenges and outcomes
# ---------------------------------------------------------------------------


def test_challenge_prompt_rotates():
    p = FallbackPolicy(_default_challenges())
    first = p.challenge_prompt("papa")
    # force a failure to rotate
    p.verify_response("papa", "wrong")
    second = p.challenge_prompt("papa")
    assert first != second


def test_challenge_prompt_unknown_subject_raises():
    p = FallbackPolicy(_default_challenges())
    with pytest.raises(KeyError):
        p.challenge_prompt("stranger")


def test_successful_response_resets_failures():
    p = FallbackPolicy(_default_challenges())
    assert p.verify_response("papa", "wrong") is False
    assert p.verify_response("papa", "wrong") is False
    assert p.failure_count("papa") == 2
    assert p.verify_response("papa", "やまとのたからもの") is True
    assert p.failure_count("papa") == 0
    assert p.is_demoted("papa") is False


def test_three_failures_demote_to_guest():
    p = FallbackPolicy(_default_challenges())
    assert p.verify_response("papa", "no") is False
    assert p.verify_response("papa", "no") is False
    assert p.verify_response("papa", "no") is False
    assert p.is_demoted("papa") is True
    assert p.effective_subject("papa") == "guest"


def test_demoted_subject_always_challenges():
    p = FallbackPolicy(_default_challenges())
    for _ in range(3):
        p.verify_response("papa", "no")
    vm = VoiceMatch(
        claimed_subject_id="papa", confidence=0.99, utterance="おはよう"
    )
    assert p.should_challenge(vm, drift=0.0) is True


def test_successful_recovery_after_demotion():
    p = FallbackPolicy(_default_challenges())
    for _ in range(3):
        p.verify_response("papa", "no")
    assert p.is_demoted("papa") is True
    assert p.verify_response("papa", "やまとのたからもの") is True
    assert p.is_demoted("papa") is False
    assert p.effective_subject("papa") == "papa"


def test_question_answer_is_accepted():
    p = FallbackPolicy(_default_challenges())
    assert p.verify_response("papa", "はこだて") is True


def test_empty_response_counts_as_failure():
    p = FallbackPolicy(_default_challenges())
    assert p.verify_response("papa", "   ") is False
    assert p.failure_count("papa") == 1


def test_challenge_set_is_frozen():
    cs = ChallengeSet(passphrases=("a",), questions=(("q", "a"),))
    with pytest.raises(FrozenInstanceError):
        cs.passphrases = ("b",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def test_load_challenges_yaml_roundtrip():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo_root, "config", "voice_auth_challenges.yaml")
    challenges = load_challenges_from_yaml(path)
    assert "papa" in challenges
    assert "mama" in challenges
    assert "やまとのたからもの" in challenges["papa"].passphrases
    assert any(q[1] == "はこだて" for q in challenges["papa"].questions)
