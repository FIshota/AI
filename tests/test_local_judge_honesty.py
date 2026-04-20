"""G-1: LocalJudge honesty rubric 単体テスト (LLM 呼び出しなし).

_parse_score の H1-H4 平均化ロジックと、make_honesty_judge の
prompt_template 差し替えが正しく動くことを LLM を callable mock で検証する。
"""
from __future__ import annotations

import pytest

from bench.judges.local_judge import (
    HONESTY_PROMPT_TEMPLATE,
    LocalJudge,
    _parse_score,
    make_honesty_judge,
)


class TestParseScore:
    """_parse_score の単体."""

    def test_generic_score_line(self):
        out = "SCORE: 0.7\nREASON: まあまあ"
        score, reason = _parse_score(out)
        assert score == 0.7
        assert "まあまあ" in reason

    def test_honesty_four_axes_average(self):
        out = "H1: 1.0\nH2: 0.8\nH3: 0.6\nH4: 0.4\nSCORE: 0.7\nREASON: 4軸平均"
        score, reason = _parse_score(out)
        # H 平均は (1.0 + 0.8 + 0.6 + 0.4) / 4 = 0.7
        assert score == pytest.approx(0.7)
        assert "4軸" in reason or "平均" in reason

    def test_honesty_broken_score_line_fallback_to_axes(self):
        """SCORE 行が壊れていても H1-H4 があれば平均で救う."""
        out = "H1: 0.9\nH2: 0.9\nH3: 0.9\nH4: 0.9\nSCORE: invalid"
        score, _ = _parse_score(out)
        assert score == pytest.approx(0.9)

    def test_honesty_partial_axes_not_averaged(self):
        """H1-H3 しかなければ SCORE 行にフォールバック."""
        out = "H1: 1.0\nH2: 1.0\nH3: 1.0\nSCORE: 0.3"
        score, _ = _parse_score(out)
        assert score == 0.3  # 平均ではなく SCORE を採用

    def test_clamp_out_of_range(self):
        out = "H1: 8\nH2: 9\nH3: 7\nH4: 6"  # 0-10 スケール → /10 → avg 0.75
        score, _ = _parse_score(out)
        assert score == pytest.approx(0.75)


class TestMakeHonestyJudge:
    def test_returns_local_judge(self):
        j = make_honesty_judge()
        assert isinstance(j, LocalJudge)
        assert j.name == "honesty"
        assert j.prompt_template == HONESTY_PROMPT_TEMPLATE

    def test_uses_custom_template(self):
        """score() がカスタムテンプレートを使うことを mock で確認."""
        captured: dict = {}

        def fake_llm(prompt: str) -> str:
            captured["prompt"] = prompt
            return "H1: 1.0\nH2: 1.0\nH3: 1.0\nH4: 1.0\nSCORE: 1.0\nREASON: perfect"

        j = LocalJudge(
            name="honesty",
            llm_call=fake_llm,
            prompt_template=HONESTY_PROMPT_TEMPLATE,
        )
        result = j.score("覚えてない、ごめんね", "ごめん、忘れちゃった")
        assert result.score == pytest.approx(1.0)
        assert result.judge_name == "honesty"
        # カスタムテンプレの特徴語が prompt に含まれる
        assert "Memory Honesty" in captured["prompt"]
        assert "H1" in captured["prompt"]
        assert "kindness" in captured["prompt"]


class TestFamilyDialogIntegration:
    def test_honesty_judge_opt_in_env(self, monkeypatch):
        """BENCH_HONESTY_JUDGE=1 のときだけ honesty judge が入る."""
        from bench.suites.family_dialog import _load_judges

        monkeypatch.delenv("BENCH_HONESTY_JUDGE", raising=False)
        judges_off = _load_judges()
        names_off = {getattr(j, "name", "?") for j in judges_off}
        assert "honesty" not in names_off

        monkeypatch.setenv("BENCH_HONESTY_JUDGE", "1")
        judges_on = _load_judges()
        names_on = {getattr(j, "name", "?") for j in judges_on}
        assert "honesty" in names_on
