"""JGLUE JCommonsenseQA suite (Phase 1).

現時点では JCommonsenseQA のみ実装。残り 4 サブタスクは Phase 2 以降。

使い方:
    python3 bench/runner.py --model sarashina2-7b --suite jglue --limit 10
"""

from __future__ import annotations

from dataclasses import dataclass

from bench.datasets import load_jcommonsenseqa
from bench.evaluator import EvalConfig, aggregate, evaluate_suite
from bench.judges.rule_judge import RuleJudge

NAME = "jglue"
SUBTASKS = ("jcommonsenseqa",)  # Phase 1 は 1 タスクのみ
LICENSE = "CC BY-SA 4.0"
SOURCE = "https://github.com/yahoojapan/JGLUE"


@dataclass(frozen=True)
class JGLUEResult:
    subtask: str
    metric: str
    value: float
    n: int


def describe() -> dict:
    return {
        "name": NAME,
        "subtasks": list(SUBTASKS),
        "license": LICENSE,
        "source": SOURCE,
        "status": "phase1",
        "judges": ["rule"],
    }


def run(model_family: str, limit: int | None = None) -> list[JGLUEResult]:
    """JCommonsenseQA を rule_judge で採点."""
    items = load_jcommonsenseqa(limit=limit)
    cfg = EvalConfig(
        model_family=model_family,
        choice_format=True,
        max_tokens=64,
    )
    records = evaluate_suite(items, cfg, judges=[RuleJudge()])
    agg = aggregate(records)

    results: list[JGLUEResult] = []
    for judge_name, mean in agg["means"].items():
        results.append(
            JGLUEResult(
                subtask="jcommonsenseqa",
                metric=f"{judge_name}_mean",
                value=float(mean),
                n=agg["n"],
            )
        )
    # latency も保存
    results.append(
        JGLUEResult(
            subtask="jcommonsenseqa",
            metric="latency_sec_mean",
            value=float(agg["latency_mean"]),
            n=agg["n"],
        )
    )
    return results
