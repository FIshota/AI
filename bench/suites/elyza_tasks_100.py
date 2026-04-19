"""ELYZA-tasks-100 suite stub (Phase 0).

ELYZA-tasks-100 は ELYZA 社が公開する 100 問の日本語生成タスク評価セット。
judge model (GPT-4 / Claude) による 5 段階採点が一般的。

Phase 0 ではスケルトンのみ。Phase 1 で
- dataset: `elyza/ELYZA-tasks-100` (HuggingFace)
- judge   : GPT-4o (OpenAI API) もしくは Claude 3.5 Sonnet
を呼び出すよう拡張する。
"""

from __future__ import annotations

from dataclasses import dataclass

NAME = "elyza_tasks_100"
LICENSE = "Apache 2.0 (judge model 側の利用規約は別途)"
SOURCE = "https://huggingface.co/datasets/elyza/ELYZA-tasks-100"


@dataclass(frozen=True)
class ElyzaResult:
    task_id: int
    score: float  # 1.0 - 5.0
    reason: str


def describe() -> dict:
    return {
        "name": NAME,
        "license": LICENSE,
        "source": SOURCE,
        "status": "stub",
        "judge": "unset — Phase 1 で GPT-4o or Claude 3.5",
    }


def run(model_family: str, limit: int | None = None) -> list[ElyzaResult]:
    _ = (model_family, limit)
    return []
