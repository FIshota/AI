"""
感情状態長期ドリフト可視化「心の健康診断」の集計ロジック。

既存の ``core.emotion_history.EmotionHistory`` が保存している連続値の
感情スナップショット (happiness / curiosity / affection / energy / anxiety) や、
``label`` キーを持つ離散ラベル付きレコード双方をサポートする。

このモジュールは UI から独立しており、tkinter / matplotlib 非依存。
ASCII sparkline 生成も提供する。
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Literal, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


# valence mapping (外部 config から上書き可能)
# 正 = ポジティブ / 負 = ネガティブ。大きさは強度。
DEFAULT_VALENCE_MAP: Dict[str, float] = {
    "happy": 1.0,
    "happiness": 1.0,
    "joy": 1.0,
    "affection": 0.8,
    "love": 0.8,
    "curiosity": 0.5,
    "energy": 0.4,
    "calm": 0.3,
    "neutral": 0.0,
    "surprise": 0.0,
    "anxiety": -0.6,
    "anxious": -0.6,
    "sad": -1.0,
    "sadness": -1.0,
    "angry": -0.5,
    "anger": -0.5,
    "fear": -0.7,
}

# 連続値キー (EmotionHistory の EMOTION_KEYS とそろえる)
CONTINUOUS_EMOTION_KEYS: Sequence[str] = (
    "happiness",
    "curiosity",
    "affection",
    "energy",
    "anxiety",
)

Window = Literal["week", "month", "year"]

# ▁▂▃▄▅▆▇█ の 8 段スパークライン
_SPARK_CHARS: str = "▁▂▃▄▅▆▇█"


@dataclass(frozen=True)
class EmotionAggregate:
    """単一期間の感情集計結果 (不可変)."""

    period_label: str
    counts: Mapping[str, int] = field(default_factory=dict)
    mean_valence: float = 0.0
    dominant: str = "neutral"
    sample_size: int = 0


def _period_label(dt: datetime, window: Window) -> str:
    if window == "week":
        iso_year, iso_week, _ = dt.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if window == "month":
        return f"{dt.year:04d}-{dt.month:02d}"
    if window == "year":
        return f"{dt.year:04d}"
    raise ValueError(f"unsupported window: {window}")


def _parse_ts(ts: str) -> Optional[datetime]:
    """``emotion_history`` の ts フォーマット (``YYYY-MM-DDTHH:MM`` 等) を寛容に解釈。"""
    if not ts or not isinstance(ts, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _record_label(
    record: Mapping[str, object],
    valence_map: Mapping[str, float],
) -> str:
    """1 レコードから代表感情ラベルを決定する。

    1. ``label`` または ``emotion`` キーがあればそれを採用
    2. 連続値キーの中で、valence の絶対値 * 値 が最大のものを採用
    3. それも取れなければ ``neutral``
    """
    for key in ("label", "emotion", "dominant"):
        val = record.get(key)
        if isinstance(val, str) and val:
            return val

    best_key: Optional[str] = None
    best_score: float = -1.0
    for key in CONTINUOUS_EMOTION_KEYS:
        raw = record.get(key)
        if not isinstance(raw, (int, float)):
            continue
        weight = abs(valence_map.get(key, 0.0))
        score = float(raw) * (weight if weight > 0 else 1.0)
        if score > best_score:
            best_score = score
            best_key = key
    return best_key or "neutral"


def _record_valence(
    record: Mapping[str, object],
    valence_map: Mapping[str, float],
) -> Optional[float]:
    """レコード 1 件の valence スコアを返す。判定不能なら None."""
    # 離散ラベルが入っているケース
    for key in ("label", "emotion", "dominant"):
        val = record.get(key)
        if isinstance(val, str) and val in valence_map:
            return float(valence_map[val])

    # 連続値キー: 各値 * valence で加重平均
    total = 0.0
    weight_total = 0.0
    for key in CONTINUOUS_EMOTION_KEYS:
        raw = record.get(key)
        if not isinstance(raw, (int, float)):
            continue
        v = valence_map.get(key)
        if v is None:
            continue
        total += float(raw) * float(v)
        weight_total += abs(float(raw))
    if weight_total == 0.0:
        return None
    return total / weight_total


class EmotionDriftAnalyzer:
    """感情履歴レコード群を期間 (週 / 月 / 年) で集計する。

    EmotionHistory インスタンスまたは生のレコード list を受け取る。
    """

    def __init__(
        self,
        records: Iterable[Mapping[str, object]] | None = None,
        *,
        history: object | None = None,
        valence_map: Optional[Mapping[str, float]] = None,
    ) -> None:
        if records is None and history is not None:
            getter = getattr(history, "get_recent", None)
            if callable(getter):
                try:
                    records = getter(10_000)
                except TypeError:
                    records = getter()
            else:
                records = getattr(history, "_records", []) or []
        self._records: List[Mapping[str, object]] = list(records or [])
        self._valence_map: Dict[str, float] = dict(DEFAULT_VALENCE_MAP)
        if valence_map:
            self._valence_map.update(valence_map)

    @property
    def valence_map(self) -> Mapping[str, float]:
        return dict(self._valence_map)

    def aggregate(self, window: Window) -> List[EmotionAggregate]:
        """期間ごとに集計した ``EmotionAggregate`` のリストを返す (時系列順)."""
        if window not in ("week", "month", "year"):
            raise ValueError(f"invalid window: {window}")
        if not self._records:
            return []

        buckets: Dict[str, Dict[str, object]] = {}
        order: List[str] = []
        for rec in self._records:
            ts = rec.get("ts") if isinstance(rec, Mapping) else None
            if not isinstance(ts, str):
                continue
            dt = _parse_ts(ts)
            if dt is None:
                continue
            label = _period_label(dt, window)
            bucket = buckets.get(label)
            if bucket is None:
                bucket = {
                    "counts": Counter(),
                    "valence_sum": 0.0,
                    "valence_n": 0,
                    "n": 0,
                }
                buckets[label] = bucket
                order.append(label)
            bucket["n"] = int(bucket["n"]) + 1
            bucket["counts"][_record_label(rec, self._valence_map)] += 1  # type: ignore[index]
            v = _record_valence(rec, self._valence_map)
            if v is not None:
                bucket["valence_sum"] = float(bucket["valence_sum"]) + v
                bucket["valence_n"] = int(bucket["valence_n"]) + 1

        order.sort()
        results: List[EmotionAggregate] = []
        for label in order:
            b = buckets[label]
            counts: Counter = b["counts"]  # type: ignore[assignment]
            n = int(b["n"])
            vn = int(b["valence_n"])
            mean_v = float(b["valence_sum"]) / vn if vn > 0 else 0.0
            dominant = counts.most_common(1)[0][0] if counts else "neutral"
            results.append(
                EmotionAggregate(
                    period_label=label,
                    counts=dict(counts),
                    mean_valence=round(mean_v, 4),
                    dominant=dominant,
                    sample_size=n,
                )
            )
        return results


def ascii_sparkline(values: Sequence[float]) -> str:
    """値列を 8 段の ASCII sparkline に変換する。

    空入力は空文字列を返す。全値同一でも safe (最低段を出す)。
    """
    if not values:
        return ""
    floats = [float(v) for v in values]
    lo = min(floats)
    hi = max(floats)
    span = hi - lo
    out = []
    levels = len(_SPARK_CHARS) - 1
    for v in floats:
        if span == 0:
            idx = 0
        else:
            idx = int(round((v - lo) / span * levels))
            idx = max(0, min(levels, idx))
        out.append(_SPARK_CHARS[idx])
    return "".join(out)


def sparkline_for_aggregates(
    aggregates: Sequence[EmotionAggregate],
) -> str:
    """``EmotionAggregate`` 列から mean_valence の sparkline を作る。"""
    return ascii_sparkline([a.mean_valence for a in aggregates])


__all__ = [
    "DEFAULT_VALENCE_MAP",
    "CONTINUOUS_EMOTION_KEYS",
    "EmotionAggregate",
    "EmotionDriftAnalyzer",
    "ascii_sparkline",
    "sparkline_for_aggregates",
]
