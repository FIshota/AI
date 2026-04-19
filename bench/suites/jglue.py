"""JGLUE suite stub (Phase 0).

JGLUE は Waseda / Yahoo Japan による日本語 GLUE 相当の総合ベンチ。
サブタスク: MARC-ja / JSTS / JNLI / JSQuAD / JCommonsenseQA。

Phase 0 ではスケルトンのみ。Phase 1 で HuggingFace datasets から
`shunk031/JGLUE` を読み込み、各タスクを評価する。
"""

from __future__ import annotations

from dataclasses import dataclass

NAME = "jglue"
SUBTASKS = ("marc_ja", "jsts", "jnli", "jsquad", "jcommonsenseqa")
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
        "status": "stub",
    }


def run(model_family: str, limit: int | None = None) -> list[JGLUEResult]:
    """Phase 1 で実装予定。Phase 0 は空リストを返す。"""
    _ = (model_family, limit)
    return []
