"""
Ebbinghaus 忘却曲線 + pin 永続化ポリシー.

References:
    Ebbinghaus (1885) Über das Gedächtnis.
    Anderson & Schooler (1991) Reflections of the environment in memory
        (rational analysis of memory).

Design notes:
    - retention R(t) = exp(-t / S) where S は記憶強度 (days).
    - rehearsal (想起) で S を増加させる (spacing effect の簡易モデル).
    - pinned=True のエントリは減衰シミュレーションとは独立に常に保持.
    - stdlib のみ, Python 3.9 互換.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple


@dataclass(frozen=True)
class ForgettingCurveParams:
    """Ebbinghaus 忘却曲線パラメータ.

    Attributes:
        initial_strength: 初期の記憶強度 S0 (days). 大きいほど初期保持が長い.
        half_life_days:   半減期に相当する基準 (days). S の単位合わせに使う.
        rehearsal_boost:  想起 1 回あたり S を何日分増やすか.
    """

    initial_strength: float = 1.0
    half_life_days: float = 7.0
    rehearsal_boost: float = 0.5

    def __post_init__(self) -> None:
        if self.initial_strength <= 0:
            raise ValueError("initial_strength must be > 0")
        if self.half_life_days <= 0:
            raise ValueError("half_life_days must be > 0")
        if self.rehearsal_boost < 0:
            raise ValueError("rehearsal_boost must be >= 0")


DEFAULT_PARAMS = ForgettingCurveParams()


def retention_score(
    elapsed_days: float,
    rehearsals: int = 0,
    params: ForgettingCurveParams = DEFAULT_PARAMS,
) -> float:
    """Ebbinghaus 風 retention (0.0-1.0) を返す.

    R(t) = exp(-t / (S0 * half_life * (1 + rehearsals * boost)))

    - elapsed_days <= 0 では 1.0 を返す (まだ忘れ始めていない).
    - rehearsals は非負の整数に丸める.
    """
    if elapsed_days <= 0:
        return 1.0
    r = max(0, int(rehearsals))
    effective = params.initial_strength * params.half_life_days * (
        1.0 + r * params.rehearsal_boost
    )
    # effective > 0 は __post_init__ で保証.
    score = math.exp(-elapsed_days / effective)
    # 数値誤差で僅かに 1 を超える場合を抑える.
    if score > 1.0:
        return 1.0
    if score < 0.0:
        return 0.0
    return score


@dataclass(frozen=True)
class MemoryEntry:
    """永続化/圧縮判定用の軽量エントリ.

    content は任意型 (dict/str 何でも可) にして既存 DB 行を持ち込める.
    """

    id: Any
    created_at: datetime
    last_rehearsed_at: Optional[datetime]
    rehearsal_count: int
    pinned: bool
    content: Any = None


@dataclass(frozen=True)
class ForgettingPolicy:
    """しきい値と params をひとまとめにした忘却ポリシー."""

    threshold: float = 0.2
    params: ForgettingCurveParams = field(default_factory=ForgettingCurveParams)

    def __post_init__(self) -> None:
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError("threshold must be within [0.0, 1.0]")

    def score(self, entry: MemoryEntry, now: datetime) -> float:
        """pinned は常に 1.0, それ以外は retention_score."""
        if entry.pinned:
            return 1.0
        base = entry.last_rehearsed_at or entry.created_at
        elapsed = (now - base).total_seconds() / 86400.0
        return retention_score(elapsed, entry.rehearsal_count, self.params)

    def should_forget(self, entry: MemoryEntry, now: datetime) -> bool:
        """retention が threshold を下回ったら True. pinned は常に False."""
        if entry.pinned:
            return False
        return self.score(entry, now) < self.threshold

    def apply(
        self, entries: List[MemoryEntry], now: Optional[datetime] = None
    ) -> Tuple[List[MemoryEntry], List[MemoryEntry]]:
        """(kept, forgotten) に分割.

        非破壊 — 入力リストは変更しない.
        """
        current = now or datetime.now()
        kept: List[MemoryEntry] = []
        forgotten: List[MemoryEntry] = []
        for e in entries:
            if self.should_forget(e, current):
                forgotten.append(e)
            else:
                kept.append(e)
        return kept, forgotten


__all__ = [
    "ForgettingCurveParams",
    "DEFAULT_PARAMS",
    "retention_score",
    "MemoryEntry",
    "ForgettingPolicy",
]
