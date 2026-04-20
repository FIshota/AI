"""bench.evaluator と suites の配線テスト (Phase 1).

LLM は重いので、dry_run モード (LLM なし) と fake judge で配線のみ確認する。
"""
from __future__ import annotations

import pytest

from bench.dataset_loaders import QAItem, load_family_dialog
from bench.evaluator import EvalConfig, EvalRecord, aggregate, evaluate_suite
from bench.judges.base import JudgeScore


class _FakeJudge:
    name = "fake"

    def __init__(self, fixed: float = 0.42):
        self.fixed = fixed

    def score(self, prediction, reference, **kwargs):
        return JudgeScore(score=self.fixed, judge_name=self.name)


def _mk_items(n: int = 3) -> list[QAItem]:
    return [
        QAItem(qid=f"t{i}", question=f"q{i}", reference=f"r{i}")
        for i in range(n)
    ]


class TestEvaluatorDryRun:
    def test_returns_one_record_per_item(self):
        items = _mk_items(3)
        recs = evaluate_suite(items, EvalConfig(), [_FakeJudge()], dry_run=True)
        assert len(recs) == 3
        assert all(isinstance(r, EvalRecord) for r in recs)

    def test_dry_run_sets_error_and_empty_prediction(self):
        items = _mk_items(1)
        recs = evaluate_suite(items, EvalConfig(), [_FakeJudge()], dry_run=True)
        assert recs[0].prediction == ""
        assert recs[0].error == "dry_run"

    def test_fake_judge_scored(self):
        items = _mk_items(2)
        recs = evaluate_suite(items, EvalConfig(), [_FakeJudge(0.7)], dry_run=True)
        for r in recs:
            assert r.scores["fake"] == 0.7

    def test_multiple_judges(self):
        items = _mk_items(1)
        recs = evaluate_suite(
            items, EvalConfig(),
            [_FakeJudge(0.3), _FakeJudge(0.9)],
            dry_run=True,
        )
        # 2 つの judge 名衝突 → 後勝ちでも実行は完了する
        assert recs[0].scores  # 非空


class TestAggregate:
    def test_empty(self):
        agg = aggregate([])
        assert agg["n"] == 0
        assert agg["means"] == {}

    def test_mean_calculation(self):
        items = _mk_items(3)
        recs = evaluate_suite(items, EvalConfig(), [_FakeJudge(0.5)], dry_run=True)
        agg = aggregate(recs)
        assert agg["n"] == 3
        assert agg["means"]["fake"] == 0.5
        assert agg["errors"] == 3  # dry_run なので全件 error


class TestSuiteDescribe:
    def test_jglue(self):
        from bench.suites import jglue
        info = jglue.describe()
        assert info["status"] == "phase1"
        assert "jcommonsenseqa" in info["subtasks"]

    def test_elyza(self):
        from bench.suites import elyza_tasks_100
        info = elyza_tasks_100.describe()
        assert info["status"] == "phase1"

    def test_family_dialog(self):
        from bench.suites import family_dialog
        info = family_dialog.describe()
        assert info["status"] == "phase1"


class TestFamilyDialogDatasetWiring:
    """suite.run() を dry-run パスで叩けることを確認する."""

    def test_family_dialog_has_seed(self):
        items = load_family_dialog(limit=5)
        assert len(items) == 5
        assert items[0].qid == "greet_morning_01"
