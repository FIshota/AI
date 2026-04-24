"""
沈黙トークン (Silence-aware) — HinoMoto 四本柱 #4「沈黙を理解する」の ai-chan 側実装。

家族との暮らしでは、沈黙そのものに意味がある (気まずい沈黙 / 穏やかな沈黙 / 不在の沈黙)。
本モジュールは「沈黙」を時間的にトークン化し、会話履歴と感情モデル更新の対象にする。

Python 3.9 互換, stdlib のみ。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, List, Optional


class SilenceCategory(Enum):
    """沈黙の粒度カテゴリ。閾値は docs/design/SILENCE_AWARE.md を参照。"""

    MICRO = "micro"      # 3〜15s   : turn 内の短い pause
    SHORT = "short"      # 15s〜2min: 考え込み・言葉を選ぶ間
    MEDIUM = "medium"    # 2min〜30min : 作業中同席・同じ空間で別作業
    LONG = "long"        # 30min〜3h  : 離席 or 集中モード
    ABSENT = "absent"    # 3h超    : 不在


# 閾値 (秒) — 下限を含み、上限を含まない (半開区間 [lo, hi))
_MICRO_LO = 3.0
_MICRO_HI = 15.0
_SHORT_HI = 120.0         # 2 min
_MEDIUM_HI = 30 * 60.0    # 30 min
_LONG_HI = 3 * 60 * 60.0  # 3 h


@dataclass(frozen=True)
class SilenceEvent:
    """ある期間の沈黙を表す不変イベント。"""

    started_at: datetime
    ended_at: datetime
    duration_s: float
    category: SilenceCategory
    ambient_context: Optional[str] = None

    def __post_init__(self) -> None:
        # invariant: started_at <= ended_at
        if self.started_at > self.ended_at:
            raise ValueError(
                f"SilenceEvent invariant violated: started_at({self.started_at}) "
                f"> ended_at({self.ended_at})"
            )
        if self.duration_s < 0:
            raise ValueError(f"duration_s must be non-negative, got {self.duration_s}")


class SilenceClassifier:
    """duration と (任意の) ambient_context から category を推定。"""

    @staticmethod
    def classify(duration_s: float, ambient_context: Optional[str] = None) -> Optional[SilenceCategory]:
        """
        duration_s に対応する SilenceCategory を返す。
        MICRO 閾値 (3s) 未満は沈黙として扱わず None を返す。
        ambient_context は将来の拡張点 (現状は category 決定には使用しない)。
        """
        if duration_s < _MICRO_LO:
            return None
        if duration_s < _MICRO_HI:
            return SilenceCategory.MICRO
        if duration_s < _SHORT_HI:
            return SilenceCategory.SHORT
        if duration_s < _MEDIUM_HI:
            return SilenceCategory.MEDIUM
        if duration_s < _LONG_HI:
            return SilenceCategory.LONG
        return SilenceCategory.ABSENT


# Emit コールバック型
SilenceCallback = Callable[[SilenceEvent], None]


class SilenceDetector:
    """
    ユーザーのアクティビティ (発話/入力等) と tick から沈黙を検出する状態機械。

    使い方:
        det = SilenceDetector(on_emit=lambda ev: ...)
        det.on_user_activity(ts)   # アクティビティを観測
        det.on_tick(now)            # 定期的に現在時刻で状態更新

    閾値を跨いだタイミングで 1 度だけ SilenceEvent を emit する。
    長時間不在から復帰した場合も、その不在期間を 1 件の ABSENT event に集約する
    (境界を跨ぐたびに大量発火することはない)。
    """

    def __init__(
        self,
        on_emit: Optional[SilenceCallback] = None,
        ambient_context_provider: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        self._on_emit = on_emit
        self._ambient_context_provider = ambient_context_provider
        self._last_activity: Optional[datetime] = None
        # このサイレンス区間で既に emit 済みの最上位カテゴリ
        self._last_emitted_category: Optional[SilenceCategory] = None
        self._silence_start: Optional[datetime] = None
        self._pending: List[SilenceEvent] = []

    # -------- public API --------

    def on_user_activity(self, ts: datetime) -> Optional[SilenceEvent]:
        """
        ユーザーのアクティビティを通知する。
        直前に沈黙が進行していた場合、その最終カテゴリの SilenceEvent を確定して emit する。
        """
        emitted: Optional[SilenceEvent] = None
        if self._silence_start is not None:
            duration = (ts - self._silence_start).total_seconds()
            category = SilenceClassifier.classify(duration, self._ambient_context())
            if category is not None:
                emitted = self._emit(self._silence_start, ts, duration, category)
        # reset
        self._last_activity = ts
        self._silence_start = ts
        self._last_emitted_category = None
        return emitted

    def on_tick(self, now: datetime) -> List[SilenceEvent]:
        """
        現在時刻で状態機械を進める。
        閾値を初めて跨いだカテゴリに対してのみ emit する (重複発火を避ける)。
        """
        emitted: List[SilenceEvent] = []
        if self._silence_start is None:
            # 初回 tick: 沈黙開始点を now とする
            self._silence_start = now
            return emitted

        duration = (now - self._silence_start).total_seconds()
        category = SilenceClassifier.classify(duration, self._ambient_context())
        if category is None:
            return emitted
        # 既に同じ/上位カテゴリを emit 済みならスキップ
        if self._last_emitted_category is not None and _rank(category) <= _rank(
            self._last_emitted_category
        ):
            return emitted
        event = self._emit(self._silence_start, now, duration, category)
        emitted.append(event)
        return emitted

    def drain(self) -> List[SilenceEvent]:
        """emit 済みで未取得の event を全て返す (test や buffered 利用向け)。"""
        out = list(self._pending)
        self._pending.clear()
        return out

    # -------- internal --------

    def _ambient_context(self) -> Optional[str]:
        if self._ambient_context_provider is None:
            return None
        try:
            return self._ambient_context_provider()
        except Exception:
            return None

    def _emit(
        self,
        started_at: datetime,
        ended_at: datetime,
        duration_s: float,
        category: SilenceCategory,
    ) -> SilenceEvent:
        event = SilenceEvent(
            started_at=started_at,
            ended_at=ended_at,
            duration_s=duration_s,
            category=category,
            ambient_context=self._ambient_context(),
        )
        self._last_emitted_category = category
        self._pending.append(event)
        if self._on_emit is not None:
            try:
                self._on_emit(event)
            except Exception:
                # callback failure は detector の状態を壊さない
                pass
        return event


_CATEGORY_RANK = {
    SilenceCategory.MICRO: 1,
    SilenceCategory.SHORT: 2,
    SilenceCategory.MEDIUM: 3,
    SilenceCategory.LONG: 4,
    SilenceCategory.ABSENT: 5,
}


def _rank(c: SilenceCategory) -> int:
    return _CATEGORY_RANK[c]


__all__ = [
    "SilenceCategory",
    "SilenceEvent",
    "SilenceClassifier",
    "SilenceDetector",
    "SilenceCallback",
]
