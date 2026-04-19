"""Benchmark scoring utilities (Phase 0 skeleton).

Implements minimal metrics that downstream suites can call.
Heavy metrics (BLEU, ROUGE, judge-model scoring) are stubbed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreResult:
    suite: str
    metric: str
    value: float
    n: int
    note: str = ""


def accuracy(preds: Iterable[str], golds: Iterable[str]) -> ScoreResult:
    """正解一致率 (文字列完全一致)。"""
    pairs = list(zip(preds, golds, strict=False))
    if not pairs:
        return ScoreResult(suite="", metric="accuracy", value=0.0, n=0)
    correct = sum(1 for p, g in pairs if str(p).strip() == str(g).strip())
    return ScoreResult(
        suite="", metric="accuracy", value=correct / len(pairs), n=len(pairs)
    )


def macro_f1(preds: Iterable[str], golds: Iterable[str]) -> ScoreResult:
    """Macro F1 — クラスごとの F1 平均。Phase 1 で scikit-learn に差し替え予定。"""
    preds_l = [str(p).strip() for p in preds]
    golds_l = [str(g).strip() for g in golds]
    if not preds_l:
        return ScoreResult(suite="", metric="macro_f1", value=0.0, n=0)

    classes = sorted(set(golds_l))
    f1s: list[float] = []
    for c in classes:
        tp = sum(1 for p, g in zip(preds_l, golds_l, strict=False) if p == c and g == c)
        fp = sum(1 for p, g in zip(preds_l, golds_l, strict=False) if p == c and g != c)
        fn = sum(1 for p, g in zip(preds_l, golds_l, strict=False) if p != c and g == c)
        if tp == 0:
            f1s.append(0.0)
            continue
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        f1s.append(f1)
    value = sum(f1s) / len(f1s) if f1s else 0.0
    return ScoreResult(suite="", metric="macro_f1", value=value, n=len(preds_l))


def judge_score_placeholder(responses: Iterable[str]) -> ScoreResult:
    """Phase 1 で GPT-4 / Claude 3.5 judge を呼び出す予定のプレースホルダ。"""
    resp = list(responses)
    return ScoreResult(
        suite="",
        metric="judge_score",
        value=0.0,
        n=len(resp),
        note="stub — Phase 1 で judge モデル連携",
    )
