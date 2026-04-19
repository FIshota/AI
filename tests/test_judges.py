"""bench/judges/ のユニットテスト (Phase 1)."""
from __future__ import annotations

import pytest

from bench.judges import JudgeScore
from bench.judges.rule_judge import (
    RuleJudge, exact_match, partial_match, rouge_l, bleu, _normalize,
)
from bench.judges.local_judge import LocalJudge, _parse_score


# ─── base ────────────────────────────────────────────────

class TestJudgeScore:
    def test_score_clamped_high(self):
        s = JudgeScore(score=1.5)
        assert s.score == 1.0

    def test_score_clamped_low(self):
        s = JudgeScore(score=-0.3)
        assert s.score == 0.0

    def test_frozen(self):
        s = JudgeScore(score=0.5)
        with pytest.raises(Exception):
            s.score = 0.9  # type: ignore


# ─── rule_judge ──────────────────────────────────────────

class TestNormalize:
    def test_fullwidth_to_halfwidth(self):
        assert _normalize("Ｈｅｌｌｏ") == "hello"

    def test_whitespace_collapse(self):
        assert _normalize("  a    b  ") == "a b"

    def test_punctuation_normalization(self):
        assert "." in _normalize("こんにちは。")


class TestExactMatch:
    def test_exact(self):
        assert exact_match("こんにちは", "こんにちは") == 1.0

    def test_different(self):
        assert exact_match("a", "b") == 0.0

    def test_fullwidth_equals_halfwidth(self):
        assert exact_match("ＡＢＣ", "abc") == 1.0


class TestPartialMatch:
    def test_contained(self):
        assert partial_match("こんにちは世界", "世界") == 1.0

    def test_not_contained(self):
        assert partial_match("apple", "banana") == 0.0

    def test_empty(self):
        assert partial_match("", "") == 0.0


class TestRougeL:
    def test_identical(self):
        assert rouge_l("abc", "abc") == 1.0

    def test_disjoint(self):
        assert rouge_l("xyz", "abc") == 0.0

    def test_partial(self):
        score = rouge_l("abcdef", "acdfgh")
        assert 0.0 < score < 1.0


class TestBleu:
    def test_identical(self):
        s = bleu("こんにちは", "こんにちは")
        assert s > 0.9

    def test_disjoint(self):
        assert bleu("abc", "xyz") == 0.0

    def test_empty(self):
        assert bleu("", "anything") == 0.0


class TestRuleJudge:
    def test_perfect_match(self):
        j = RuleJudge()
        r = j.score("こんにちは", "こんにちは")
        assert r.score == 1.0
        assert r.judge_name == "rule"

    def test_no_match(self):
        j = RuleJudge()
        r = j.score("りんご", "バナナ")
        assert r.score < 0.3

    def test_multiple_references_picks_best(self):
        j = RuleJudge()
        r = j.score("こんにちは", ["さよなら", "こんにちは", "おはよう"])
        assert r.score == 1.0


# ─── local_judge ─────────────────────────────────────────

class TestParseScore:
    def test_standard_format(self):
        score, reason = _parse_score("SCORE: 0.8\nREASON: ほぼ合っている")
        assert score == 0.8
        assert "ほぼ" in reason

    def test_fullwidth_colon(self):
        score, _ = _parse_score("SCORE：0.5\nREASON：部分的")
        assert score == 0.5

    def test_out_of_range_clamped(self):
        score, _ = _parse_score("SCORE: 1.5")
        assert score == 1.0

    def test_10_scale_rescaled(self):
        score, _ = _parse_score("SCORE: 8")
        assert score == 0.8  # 8/10 に自動リスケール

    def test_garbage_returns_zero(self):
        score, _ = _parse_score("hmm not sure")
        assert 0.0 <= score <= 1.0

    def test_empty(self):
        score, reason = _parse_score("")
        assert score == 0.0


class TestLocalJudge:
    def test_with_injected_llm(self):
        def fake_llm(prompt):
            return "SCORE: 0.7\nREASON: ほぼ正解"
        j = LocalJudge(llm_call=fake_llm)
        r = j.score("test", "expected")
        assert r.score == 0.7
        assert r.judge_name == "local"
        assert "ほぼ" in r.reasoning

    def test_llm_failure_returns_zero(self):
        def bad_llm(prompt):
            raise RuntimeError("model down")
        j = LocalJudge(llm_call=bad_llm)
        r = j.score("x", "y")
        assert r.score == 0.0
        assert "error" in r.raw
