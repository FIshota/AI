"""
テレメトリ基盤 -- 匿名品質フィードバック収集
ユーザーのプライバシーを完全に保護しながら、品質改善に必要なデータを収集。

原則:
- 個人情報は一切収集しない
- 会話内容は収集しない
- 統計データのみ（応答時間、品質スコア、エラー率）
- ローカル保存のみ（外部送信しない）
- いつでもオフにできる
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_EVENTS = 10_000


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# データ構造
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass(frozen=True)
class TelemetryEvent:
    """単一テレメトリイベント。

    Attributes:
        event_type: イベント種別 (response_time, quality_score, error, bypass_type 等)
        timestamp: ISO 8601 形式のUTCタイムスタンプ
        data: イベント固有のデータ辞書
    """
    event_type: str
    timestamp: str
    data: Dict[str, Any]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# テレメトリ収集器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TelemetryCollector:
    """匿名テレメトリの収集・集計・レポート。

    イベントは JSON Lines ファイル（1行1JSON、追記のみ）に保存される。
    最大 10,000 件で自動ローテーション。
    """

    def __init__(
        self,
        storage_path: str | Path,
        enabled: bool = True,
    ) -> None:
        self._path = Path(storage_path)
        self._enabled = enabled
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("テレメトリ %s", "有効" if value else "無効")

    # ── 記録 ────────────────────────────────────────────

    def record(self, event_type: str, **data: Any) -> TelemetryEvent | None:
        """テレメトリイベントを記録する。

        Args:
            event_type: イベント種別 (例: "response_time", "quality_score", "error")
            **data: イベント固有のキーワード引数。

        Returns:
            記録された TelemetryEvent、無効時は None。
        """
        if not self._enabled:
            return None

        event = TelemetryEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data=dict(data),
        )

        self._append(event)
        self._rotate_if_needed()
        return event

    def _append(self, event: TelemetryEvent) -> None:
        """イベントをJSON Linesファイルに追記する。"""
        line: str = json.dumps(asdict(event), ensure_ascii=False)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _rotate_if_needed(self) -> None:
        """イベント数が上限を超えたらローテーションする。"""
        if not self._path.exists():
            return

        count = self._count_lines()
        if count <= _MAX_EVENTS:
            return

        # 古いファイルを .bak に退避し、新しい半分だけ残す
        logger.info("テレメトリローテーション開始 (%d イベント)", count)
        events = self._load_all()
        keep = events[count // 2:]  # 後半を残す

        bak = self._path.with_suffix(".jsonl.bak")
        if self._path.exists():
            shutil.copy2(self._path, bak)

        with open(self._path, "w", encoding="utf-8") as f:
            for ev in keep:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

        logger.info("ローテーション完了: %d -> %d イベント", count, len(keep))

    def _count_lines(self) -> int:
        """ファイルの行数を数える。"""
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for _ in f:
                count += 1
        return count

    def _load_all(self) -> List[Dict[str, Any]]:
        """全イベントをリストとして読み込む。"""
        if not self._path.exists():
            return []
        events: List[Dict[str, Any]] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    try:
                        events.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        logger.warning("不正なJSON行をスキップ: %s", stripped[:80])
        return events

    def _load_since(self, cutoff: datetime) -> List[Dict[str, Any]]:
        """指定日時以降のイベントのみ読み込む。"""
        all_events = self._load_all()
        result: List[Dict[str, Any]] = []
        cutoff_iso = cutoff.isoformat()
        for ev in all_events:
            ts = ev.get("timestamp", "")
            if ts >= cutoff_iso:
                result.append(ev)
        return result

    # ── 集計 ────────────────────────────────────────────

    def get_summary(self, days: int = 7) -> Dict[str, Any]:
        """直近N日間の統計サマリを返す。

        Returns:
            {"period_days": N, "total_events": ..., "by_type": {...}, "avg_response_time": ..., "avg_quality_score": ...}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        events = self._load_since(cutoff)

        by_type: Dict[str, int] = {}
        response_times: List[float] = []
        quality_scores: List[float] = []
        error_count = 0

        for ev in events:
            etype = ev.get("event_type", "unknown")
            by_type[etype] = by_type.get(etype, 0) + 1

            data = ev.get("data", {})
            if etype == "response_time" and "value" in data:
                try:
                    response_times.append(float(data["value"]))
                except (ValueError, TypeError):
                    pass
            elif etype == "quality_score" and "value" in data:
                try:
                    quality_scores.append(float(data["value"]))
                except (ValueError, TypeError):
                    pass
            elif etype == "error":
                error_count += 1

        return {
            "period_days": days,
            "total_events": len(events),
            "by_type": by_type,
            "avg_response_time": (
                round(sum(response_times) / len(response_times), 3)
                if response_times else None
            ),
            "avg_quality_score": (
                round(sum(quality_scores) / len(quality_scores), 3)
                if quality_scores else None
            ),
            "error_count": error_count,
        }

    def get_trends(self) -> Dict[str, Any]:
        """品質が向上しているか劣化しているかの傾向を返す。

        直近7日と前7日を比較して変化率を算出する。

        Returns:
            {"response_time_trend": ..., "quality_score_trend": ..., "error_rate_trend": ..., "direction": "improving" | "declining" | "stable"}
        """
        now = datetime.now(timezone.utc)
        recent_start = now - timedelta(days=7)
        previous_start = now - timedelta(days=14)

        all_events = self._load_all()

        recent_rt: List[float] = []
        previous_rt: List[float] = []
        recent_qs: List[float] = []
        previous_qs: List[float] = []
        recent_errors = 0
        previous_errors = 0
        recent_total = 0
        previous_total = 0

        recent_iso = recent_start.isoformat()
        previous_iso = previous_start.isoformat()

        for ev in all_events:
            ts = ev.get("timestamp", "")
            etype = ev.get("event_type", "")
            data = ev.get("data", {})

            if ts >= recent_iso:
                recent_total += 1
                if etype == "response_time" and "value" in data:
                    try:
                        recent_rt.append(float(data["value"]))
                    except (ValueError, TypeError):
                        pass
                elif etype == "quality_score" and "value" in data:
                    try:
                        recent_qs.append(float(data["value"]))
                    except (ValueError, TypeError):
                        pass
                elif etype == "error":
                    recent_errors += 1
            elif ts >= previous_iso:
                previous_total += 1
                if etype == "response_time" and "value" in data:
                    try:
                        previous_rt.append(float(data["value"]))
                    except (ValueError, TypeError):
                        pass
                elif etype == "quality_score" and "value" in data:
                    try:
                        previous_qs.append(float(data["value"]))
                    except (ValueError, TypeError):
                        pass
                elif etype == "error":
                    previous_errors += 1

        def _avg(values: List[float]) -> float | None:
            return round(sum(values) / len(values), 3) if values else None

        def _pct_change(old: float | None, new: float | None) -> float | None:
            if old is None or new is None or old == 0:
                return None
            return round((new - old) / abs(old) * 100, 1)

        avg_recent_rt = _avg(recent_rt)
        avg_prev_rt = _avg(previous_rt)
        avg_recent_qs = _avg(recent_qs)
        avg_prev_qs = _avg(previous_qs)

        rt_change = _pct_change(avg_prev_rt, avg_recent_rt)
        qs_change = _pct_change(avg_prev_qs, avg_recent_qs)

        # 方向判定: 品質スコア上昇 or 応答時間短縮 -> improving
        improving_signals = 0
        declining_signals = 0
        if qs_change is not None:
            if qs_change > 5:
                improving_signals += 1
            elif qs_change < -5:
                declining_signals += 1
        if rt_change is not None:
            if rt_change < -5:  # 応答時間短縮は改善
                improving_signals += 1
            elif rt_change > 5:
                declining_signals += 1

        if improving_signals > declining_signals:
            direction = "improving"
        elif declining_signals > improving_signals:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "response_time_trend": {
                "recent_avg": avg_recent_rt,
                "previous_avg": avg_prev_rt,
                "change_pct": rt_change,
            },
            "quality_score_trend": {
                "recent_avg": avg_recent_qs,
                "previous_avg": avg_prev_qs,
                "change_pct": qs_change,
            },
            "error_rate_trend": {
                "recent": recent_errors,
                "previous": previous_errors,
            },
            "direction": direction,
        }

    # ── レポート ────────────────────────────────────────

    def export_report(self) -> str:
        """人間が読めるテレメトリレポートを生成する。"""
        summary = self.get_summary(days=7)
        trends = self.get_trends()

        lines: List[str] = []
        lines.append("=" * 50)
        lines.append("  テレメトリレポート")
        lines.append("=" * 50)
        lines.append("")

        # サマリ
        lines.append("■ 直近7日間のサマリ")
        lines.append("-" * 30)
        lines.append(f"  総イベント数: {summary['total_events']}")
        if summary["avg_response_time"] is not None:
            lines.append(f"  平均応答時間: {summary['avg_response_time']}s")
        if summary["avg_quality_score"] is not None:
            lines.append(f"  平均品質スコア: {summary['avg_quality_score']}")
        lines.append(f"  エラー数: {summary['error_count']}")
        lines.append("")

        # イベント種別
        by_type = summary.get("by_type", {})
        if by_type:
            lines.append("  イベント種別:")
            for etype, count in sorted(by_type.items()):
                lines.append(f"    {etype}: {count}")
            lines.append("")

        # トレンド
        direction = trends.get("direction", "unknown")
        direction_jp = {
            "improving": "改善傾向",
            "declining": "劣化傾向",
            "stable": "安定",
        }.get(direction, direction)

        lines.append("■ トレンド（前週比較）")
        lines.append("-" * 30)
        lines.append(f"  全体方向: {direction_jp}")

        rt = trends.get("response_time_trend", {})
        if rt.get("change_pct") is not None:
            lines.append(f"  応答時間変化: {rt['change_pct']:+.1f}%")

        qs = trends.get("quality_score_trend", {})
        if qs.get("change_pct") is not None:
            lines.append(f"  品質スコア変化: {qs['change_pct']:+.1f}%")

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)

    # ── #44: 満足度プロキシ ──────────────────────────────

    def record_conversation_length(self, turns: int) -> Optional[TelemetryEvent]:
        """会話ターン数を記録する。

        Args:
            turns: 1セッション内のやりとり回数。

        Returns:
            記録された TelemetryEvent、無効時は None。
        """
        return self.record("conversation_length", value=turns)

    def record_session_gap(self, hours: float) -> Optional[TelemetryEvent]:
        """セッション間のギャップ時間（時間単位）を記録する。

        Args:
            hours: 前回セッションからの経過時間（時間）。

        Returns:
            記録された TelemetryEvent、無効時は None。
        """
        return self.record("session_gap", value=round(hours, 2))

    def record_correction(self, correction_type: str) -> Optional[TelemetryEvent]:
        """ユーザーによる訂正を記録する。

        Args:
            correction_type: 訂正の種類 (例: "rephrase", "reject", "redirect")。

        Returns:
            記録された TelemetryEvent、無効時は None。
        """
        return self.record("correction", type=correction_type)

    def get_satisfaction_proxies(self, days: int = 7) -> Dict[str, Any]:
        """満足度の間接指標をまとめて返す。

        Returns:
            {
                "avg_conversation_length": float | None,
                "avg_session_gap_hours": float | None,
                "correction_rate": float | None,
                "total_sessions": int,
            }
        """
        cutoff: datetime = datetime.now(timezone.utc) - timedelta(days=days)
        events: List[Dict[str, Any]] = self._load_since(cutoff)

        conv_lengths: List[float] = []
        session_gaps: List[float] = []
        corrections: int = 0
        total_events: int = 0

        for ev in events:
            etype: str = ev.get("event_type", "")
            data: Dict[str, Any] = ev.get("data", {})
            total_events += 1

            if etype == "conversation_length" and "value" in data:
                try:
                    conv_lengths.append(float(data["value"]))
                except (ValueError, TypeError):
                    pass
            elif etype == "session_gap" and "value" in data:
                try:
                    session_gaps.append(float(data["value"]))
                except (ValueError, TypeError):
                    pass
            elif etype == "correction":
                corrections += 1

        total_sessions: int = len(conv_lengths)
        return {
            "avg_conversation_length": (
                round(sum(conv_lengths) / len(conv_lengths), 2)
                if conv_lengths else None
            ),
            "avg_session_gap_hours": (
                round(sum(session_gaps) / len(session_gaps), 2)
                if session_gaps else None
            ),
            "correction_rate": (
                round(corrections / total_sessions, 4)
                if total_sessions > 0 else None
            ),
            "total_sessions": total_sessions,
        }

    # ── #52: 処理レイヤー分布 ──────────────────────────────

    _VALID_LAYERS: tuple[str, ...] = ("reflex", "muscle_memory", "llm")

    def record_processing_layer(self, layer: str) -> Optional[TelemetryEvent]:
        """応答生成に使われた処理レイヤーを記録する。

        Args:
            layer: "reflex" / "muscle_memory" / "llm" のいずれか。

        Returns:
            記録された TelemetryEvent、無効時は None。

        Raises:
            ValueError: 不明なレイヤー名が渡された場合。
        """
        if layer not in self._VALID_LAYERS:
            raise ValueError(
                f"不明なレイヤー: {layer!r}  (有効値: {self._VALID_LAYERS})"
            )
        return self.record("processing_layer", layer=layer)

    def get_layer_distribution(self, days: int = 7) -> Dict[str, Any]:
        """処理レイヤーごとの使用割合を返す。

        Returns:
            {
                "counts": {"reflex": N, "muscle_memory": N, "llm": N},
                "ratios": {"reflex": 0.x, ...},
                "total": N,
            }
        """
        cutoff: datetime = datetime.now(timezone.utc) - timedelta(days=days)
        events: List[Dict[str, Any]] = self._load_since(cutoff)

        counts: Counter[str] = Counter()
        for ev in events:
            if ev.get("event_type") == "processing_layer":
                layer: str = ev.get("data", {}).get("layer", "")
                if layer:
                    counts[layer] += 1

        total: int = sum(counts.values())
        ratios: Dict[str, float] = {}
        if total > 0:
            ratios = {k: round(v / total, 4) for k, v in counts.items()}

        return {
            "counts": dict(counts),
            "ratios": ratios,
            "total": total,
        }

    # ── #53: 推論コスト追跡 ─────────────────────────────────

    def record_inference_cost(
        self,
        tokens_in: int,
        tokens_out: int,
        duration_ms: float,
    ) -> Optional[TelemetryEvent]:
        """1回の推論にかかったトークン数と所要時間を記録する。

        Args:
            tokens_in: 入力トークン数。
            tokens_out: 出力トークン数。
            duration_ms: 推論にかかったミリ秒。

        Returns:
            記録された TelemetryEvent、無効時は None。
        """
        return self.record(
            "inference_cost",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=round(duration_ms, 1),
        )

    def get_cost_metrics(self, days: int = 7) -> Dict[str, Any]:
        """推論コストの集計メトリクスを返す。

        Returns:
            {
                "total_tokens_in": int,
                "total_tokens_out": int,
                "avg_duration_ms": float | None,
                "total_inferences": int,
                "avg_tokens_per_inference": float | None,
            }
        """
        cutoff: datetime = datetime.now(timezone.utc) - timedelta(days=days)
        events: List[Dict[str, Any]] = self._load_since(cutoff)

        total_in: int = 0
        total_out: int = 0
        durations: List[float] = []

        for ev in events:
            if ev.get("event_type") != "inference_cost":
                continue
            data: Dict[str, Any] = ev.get("data", {})
            try:
                total_in += int(data.get("tokens_in", 0))
                total_out += int(data.get("tokens_out", 0))
            except (ValueError, TypeError):
                pass
            try:
                durations.append(float(data["duration_ms"]))
            except (KeyError, ValueError, TypeError):
                pass

        total_inferences: int = len(durations)
        total_tokens: int = total_in + total_out

        return {
            "total_tokens_in": total_in,
            "total_tokens_out": total_out,
            "avg_duration_ms": (
                round(sum(durations) / len(durations), 1)
                if durations else None
            ),
            "total_inferences": total_inferences,
            "avg_tokens_per_inference": (
                round(total_tokens / total_inferences, 1)
                if total_inferences > 0 else None
            ),
        }

    # ── #55: 機能ヒートマップ ──────────────────────────────

    def record_feature_usage(self, feature_name: str) -> Optional[TelemetryEvent]:
        """機能の使用を記録する。

        Args:
            feature_name: 使用された機能名 (例: "code_engine", "emotion", "diary")。

        Returns:
            記録された TelemetryEvent、無効時は None。
        """
        return self.record("feature_usage", feature=feature_name)

    def get_feature_heatmap(self, days: int = 30) -> Dict[str, int]:
        """機能ごとの使用回数マップを返す。

        Returns:
            {"feature_name": 使用回数, ...}  使用回数降順。
        """
        cutoff: datetime = datetime.now(timezone.utc) - timedelta(days=days)
        events: List[Dict[str, Any]] = self._load_since(cutoff)

        counts: Counter[str] = Counter()
        for ev in events:
            if ev.get("event_type") == "feature_usage":
                feature: str = ev.get("data", {}).get("feature", "")
                if feature:
                    counts[feature] += 1

        return dict(counts.most_common())

    def get_unused_features(self, all_features: List[str], days: int = 30) -> List[str]:
        """指定期間中に一度も使われなかった機能の一覧を返す。

        Args:
            all_features: 全機能名のリスト。
            days: 集計対象日数。

        Returns:
            使用されなかった機能名のリスト。
        """
        heatmap: Dict[str, int] = self.get_feature_heatmap(days=days)
        return [f for f in all_features if f not in heatmap]

    # ── クリーンアップ ──────────────────────────────────

    def clear(self, older_than_days: int = 30) -> int:
        """指定日数より古いイベントを削除する。

        Args:
            older_than_days: この日数より古いイベントを削除。

        Returns:
            削除されたイベント数。
        """
        if not self._path.exists():
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        cutoff_iso = cutoff.isoformat()
        all_events = self._load_all()

        kept: List[Dict[str, Any]] = []
        removed = 0
        for ev in all_events:
            if ev.get("timestamp", "") >= cutoff_iso:
                kept.append(ev)
            else:
                removed += 1

        with open(self._path, "w", encoding="utf-8") as f:
            for ev in kept:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

        logger.info("テレメトリ清掃: %d 件削除, %d 件保持", removed, len(kept))
        return removed
