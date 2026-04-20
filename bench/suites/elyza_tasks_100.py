"""ELYZA-tasks-100 suite (Phase 1, zero-cost 版).

オリジナル評価は GPT-4 judge が想定だが、本実装では
無料の rule_judge + semantic_judge で代替する。
Phase 2 で local_judge (Sarashina2 self-eval) を追加予定。
"""

from __future__ import annotations

from dataclasses import dataclass

from bench.dataset_loaders import load_elyza_tasks_100
from bench.evaluator import EvalConfig, aggregate, evaluate_suite
from bench.judges.rule_judge import RuleJudge

NAME = "elyza_tasks_100"
LICENSE = "CC BY-SA 4.0"
SOURCE = "https://huggingface.co/datasets/elyza/ELYZA-tasks-100"


@dataclass(frozen=True)
class ElyzaResult:
    task_id: str
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
        # sentence-transformers 未インストールなら rule のみ
        pass
    return judges


def run(
    model_family: str,
    limit: int | None = None,
    qid_prefix: str | None = None,
) -> list[ElyzaResult]:
    items = load_elyza_tasks_100(limit=None if qid_prefix else limit)
    if qid_prefix:
        items = [it for it in items if it.qid.startswith(qid_prefix)]
        if limit is not None:
            items = items[:limit]
    cfg = EvalConfig(model_family=model_family, max_tokens=384)
    records = evaluate_suite(items, cfg, judges=_load_judges())
    agg = aggregate(records)

    results: list[ElyzaResult] = []
    for judge_name, mean in agg["means"].items():
        results.append(
            ElyzaResult(
                task_id="aggregate",
                metric=f"{judge_name}_mean",
                value=float(mean),
            )
        )
    results.append(
        ElyzaResult(
            task_id="aggregate",
            metric="latency_sec_mean",
            value=float(agg["latency_mean"]),
        )
    )
    return results
