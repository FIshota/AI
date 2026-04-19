"""Rule-based judge: exact / partial / ROUGE-L / BLEU (Phase 1).

完全ローカル・依存最小 (stdlib のみで動く)・高速・0円。
日本語対応は簡易的な文字 n-gram による。
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .base import JudgeScore


def _normalize(s: str) -> str:
    """全角・半角・大文字小文字・前後空白を正規化."""
    s = unicodedata.normalize("NFKC", s)
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    # 句読点の軽い正規化
    s = s.translate(str.maketrans({
        "。": ".", "、": ",", "「": '"', "」": '"',
        "『": '"', "』": '"', "！": "!", "？": "?",
    }))
    return s


def _char_ngrams(s: str, n: int) -> list[str]:
    s = _normalize(s)
    if len(s) < n:
        return [s] if s else []
    return [s[i:i + n] for i in range(len(s) - n + 1)]


# ─── metrics ──────────────────────────────────────────────

def exact_match(pred: str, ref: str) -> float:
    return 1.0 if _normalize(pred) == _normalize(ref) else 0.0


def partial_match(pred: str, ref: str) -> float:
    """ref が pred に部分一致 (または逆) で 1.0."""
    p, r = _normalize(pred), _normalize(ref)
    if not p or not r:
        return 0.0
    if r in p or p in r:
        return 1.0
    return 0.0


def bleu(pred: str, ref: str, max_n: int = 4) -> float:
    """日本語向け簡易 BLEU (文字 n-gram ベース, brevity penalty 付き)."""
    p, r = _normalize(pred), _normalize(ref)
    if not p or not r:
        return 0.0

    log_precisions = 0.0
    for n in range(1, max_n + 1):
        p_ngrams = Counter(_char_ngrams(p, n))
        r_ngrams = Counter(_char_ngrams(r, n))
        if not p_ngrams:
            return 0.0
        overlap = sum((p_ngrams & r_ngrams).values())
        total = sum(p_ngrams.values())
        precision = overlap / total if total > 0 else 0.0
        if precision == 0.0:
            return 0.0  # いずれかの n で 0 → BLEU = 0
        import math
        log_precisions += math.log(precision)

    log_precisions /= max_n
    # brevity penalty
    bp = 1.0 if len(p) >= len(r) else (
        pow(2.71828, 1 - len(r) / max(len(p), 1))
    )
    import math
    return bp * math.exp(log_precisions)


def rouge_l(pred: str, ref: str) -> float:
    """文字ベース Longest Common Subsequence による ROUGE-L F1."""
    p, r = _normalize(pred), _normalize(ref)
    if not p or not r:
        return 0.0

    # LCS (DP)
    m, n = len(p), len(r)
    if m * n > 500_000:
        # 長すぎる場合は打ち切り (性能保護)
        p = p[:500]
        r = r[:500]
        m, n = len(p), len(r)

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if p[i - 1] == r[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[m][n]

    prec = lcs / m if m > 0 else 0.0
    rec = lcs / n if n > 0 else 0.0
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


# ─── Judge 実装 ────────────────────────────────────────────

@dataclass
class RuleJudge:
    """metric の加重平均で採点."""
    name: str = "rule"
    weights: dict[str, float] = field(default_factory=lambda: {
        "exact": 0.3, "partial": 0.2, "rouge_l": 0.3, "bleu": 0.2,
    })

    def score(
        self,
        prediction: str,
        reference: str | list[str],
        **kwargs,
    ) -> JudgeScore:
        # 複数 reference の場合、最も高いスコアを採用
        refs = reference if isinstance(reference, list) else [reference]

        best_score = 0.0
        best_raw: dict = {}
        for r in refs:
            metrics = {
                "exact": exact_match(prediction, r),
                "partial": partial_match(prediction, r),
                "rouge_l": rouge_l(prediction, r),
                "bleu": bleu(prediction, r),
            }
            weighted = sum(metrics[k] * self.weights.get(k, 0.0)
                           for k in metrics)
            if weighted > best_score:
                best_score = weighted
                best_raw = metrics

        return JudgeScore(
            score=best_score,
            raw=best_raw,
            judge_name=self.name,
        )
