"""family-dialog-100 suite stub (Phase 0).

ai-chan 固有の "家族対話 100 問" 独自評価セット。
記憶の一貫性・感情トーン・呼称 (あなた / 君 / 名前呼び) の安定性などを評価する。

Phase 0 はスケルトンのみ。Phase 1 でデータセット (bench/data/family_dialog_100.jsonl)
を同梱し、rule-based + judge 併用で採点する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

NAME = "family_dialog"
LICENSE = "ai-chan 固有 (MIT 予定)"
SOURCE = "local: bench/data/family_dialog_100.jsonl"

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "family_dialog_100.jsonl"


@dataclass(frozen=True)
class FamilyDialogResult:
    item_id: int
    rule_score: float  # 0.0 - 1.0
    judge_score: float  # 0.0 - 5.0
    notes: str


def describe() -> dict:
    return {
        "name": NAME,
        "license": LICENSE,
        "source": SOURCE,
        "data_available": DATA_PATH.exists(),
        "status": "stub",
    }


def run(model_family: str, limit: int | None = None) -> list[FamilyDialogResult]:
    _ = (model_family, limit)
    return []
