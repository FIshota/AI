"""family-dialog suite (Phase 1).

ai-chan 固有の家族対話評価セット。rule + semantic で採点。
Phase 1 は 30 問のシード、Phase 2 で 100 問に拡張。
"""

from __future__ import annotations

from dataclasses import dataclass

from bench.datasets import load_family_dialog
from bench.evaluator import EvalConfig, aggregate, evaluate_suite
from bench.judges.rule_judge import RuleJudge

NAME = "family_dialog"
LICENSE = "MIT (ai-chan 固有)"
SOURCE = "bench/datasets.py::FAMILY_DIALOG_SEED"


@dataclass(frozen=True)
class FamilyDialogResult:
    item_id: str
    metric: str
    value: float


def describe() -> dict:
    return {
        "name": NAME,
        "license": LICENSE,
        "source": SOURCE,
        "status": "phase1",
        "judges": ["rule", "semantic (optional)"],
    }


def _load_judges() -> list:
    judges: list = [RuleJudge()]
    try:
        from bench.judges.semantic_judge import SemanticJudge
        judges.append(SemanticJudge())
    except Exception:
        pass
    return judges


def run(model_family: str, limit: int | None = None) -> list[FamilyDialogResult]:
    items = load_family_dialog(limit=limit)
    cfg = EvalConfig(model_family=model_family, max_tokens=256, temperature=0.8)
    records = evaluate_suite(items, cfg, judges=_load_judges())
    agg = aggregate(records)

    results: list[FamilyDialogResult] = []
    for judge_name, mean in agg["means"].items():
        results.append(
            FamilyDialogResult(
                item_id="aggregate",
                metric=f"{judge_name}_mean",
                value=float(mean),
            )
        )
    results.append(
        FamilyDialogResult(
            item_id="aggregate",
            metric="latency_sec_mean",
            value=float(agg["latency_mean"]),
        )
    )
    return results
