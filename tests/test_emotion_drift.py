"""Tests for core.emotion_drift (心の健康診断 集計ロジック)."""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.emotion_drift import (  # noqa: E402
    DEFAULT_VALENCE_MAP,
    EmotionAggregate,
    EmotionDriftAnalyzer,
    ascii_sparkline,
    sparkline_for_aggregates,
)


@pytest.mark.unit
def test_empty_history_returns_empty_list() -> None:
    analyzer = EmotionDriftAnalyzer([])
    assert analyzer.aggregate("week") == []
    assert analyzer.aggregate("month") == []
    assert analyzer.aggregate("year") == []


@pytest.mark.unit
def test_aggregate_frozen_dataclass() -> None:
    agg = EmotionAggregate(period_label="2026-W01", counts={"happy": 1})
    assert dataclasses.is_dataclass(agg)
    with pytest.raises(dataclasses.FrozenInstanceError):
        agg.period_label = "2026-W02"  # type: ignore[misc]


@pytest.mark.unit
def test_invalid_window_raises() -> None:
    analyzer = EmotionDriftAnalyzer([{"ts": "2026-04-01T10:00", "label": "happy"}])
    with pytest.raises(ValueError):
        analyzer.aggregate("decade")  # type: ignore[arg-type]


@pytest.mark.unit
def test_single_emotion_label_records() -> None:
    recs = [
        {"ts": "2026-04-01T10:00", "label": "happy"},
        {"ts": "2026-04-02T11:30", "label": "happy"},
        {"ts": "2026-04-03T09:00", "label": "happy"},
    ]
    out = EmotionDriftAnalyzer(recs).aggregate("month")
    assert len(out) == 1
    a = out[0]
    assert a.period_label == "2026-04"
    assert a.dominant == "happy"
    assert a.counts == {"happy": 3}
    assert a.sample_size == 3
    assert a.mean_valence == pytest.approx(DEFAULT_VALENCE_MAP["happy"])


@pytest.mark.unit
def test_valence_aggregation_mixed_labels() -> None:
    recs = [
        {"ts": "2026-04-01T10:00", "label": "happy"},
        {"ts": "2026-04-02T10:00", "label": "sad"},
        {"ts": "2026-04-03T10:00", "label": "neutral"},
    ]
    [a] = EmotionDriftAnalyzer(recs).aggregate("month")
    # (1.0 + -1.0 + 0.0) / 3 = 0.0
    assert a.mean_valence == pytest.approx(0.0, abs=1e-6)
    assert a.sample_size == 3
    # 各ラベル 1 件なので dominant は Counter の最初の key ("happy")
    assert a.dominant in {"happy", "sad", "neutral"}


@pytest.mark.unit
def test_week_boundary_isocalendar() -> None:
    # 2026-01-04 は ISO 週 2026-W01 の日曜、2026-01-05 は W02 月曜
    recs = [
        {"ts": "2026-01-04T10:00", "label": "happy"},
        {"ts": "2026-01-05T10:00", "label": "happy"},
    ]
    out = EmotionDriftAnalyzer(recs).aggregate("week")
    labels = [a.period_label for a in out]
    assert labels == sorted(labels)
    assert len(out) == 2
    assert "W01" in labels[0] or "W02" in labels[0]


@pytest.mark.unit
def test_month_and_year_windows() -> None:
    recs = [
        {"ts": "2025-12-31T23:59", "label": "sad"},
        {"ts": "2026-01-01T00:05", "label": "happy"},
        {"ts": "2026-02-15T12:00", "label": "happy"},
    ]
    months = EmotionDriftAnalyzer(recs).aggregate("month")
    assert [a.period_label for a in months] == ["2025-12", "2026-01", "2026-02"]
    years = EmotionDriftAnalyzer(recs).aggregate("year")
    assert [a.period_label for a in years] == ["2025", "2026"]
    assert years[0].dominant == "sad"
    assert years[1].dominant == "happy"


@pytest.mark.unit
def test_continuous_emotion_records() -> None:
    recs = [
        {
            "ts": "2026-04-01T10:00",
            "happiness": 0.8,
            "curiosity": 0.6,
            "affection": 0.5,
            "energy": 0.4,
            "anxiety": 0.1,
        },
        {
            "ts": "2026-04-02T10:00",
            "happiness": 0.2,
            "curiosity": 0.3,
            "affection": 0.3,
            "energy": 0.2,
            "anxiety": 0.9,
        },
    ]
    [a] = EmotionDriftAnalyzer(recs).aggregate("month")
    assert a.sample_size == 2
    # 1 件目は happiness が dominant、2 件目は anxiety が dominant
    assert set(a.counts.keys()) == {"happiness", "anxiety"}
    # valence: 1 件目正 / 2 件目負 → mean に正負が混じる
    assert -1.0 <= a.mean_valence <= 1.0


@pytest.mark.unit
def test_invalid_or_missing_ts_ignored() -> None:
    recs = [
        {"ts": "2026-04-01T10:00", "label": "happy"},
        {"ts": "not-a-date", "label": "sad"},
        {"label": "happy"},  # ts 無し
        {"ts": 12345, "label": "happy"},  # 非 str
    ]
    [a] = EmotionDriftAnalyzer(recs).aggregate("month")
    assert a.sample_size == 1
    assert a.dominant == "happy"


@pytest.mark.unit
def test_custom_valence_map_override() -> None:
    recs = [{"ts": "2026-04-01T10:00", "label": "happy"}]
    a = EmotionDriftAnalyzer(recs, valence_map={"happy": 0.25}).aggregate("month")[0]
    assert a.mean_valence == pytest.approx(0.25)


@pytest.mark.unit
def test_ascii_sparkline_basic() -> None:
    spark = ascii_sparkline([0.0, 0.5, 1.0])
    assert len(spark) == 3
    assert spark[0] == "▁"
    assert spark[-1] == "█"


@pytest.mark.unit
def test_ascii_sparkline_empty_and_constant() -> None:
    assert ascii_sparkline([]) == ""
    assert ascii_sparkline([0.5, 0.5, 0.5]) == "▁▁▁"


@pytest.mark.unit
def test_sparkline_for_aggregates() -> None:
    aggs = [
        EmotionAggregate(period_label="a", mean_valence=-1.0),
        EmotionAggregate(period_label="b", mean_valence=0.0),
        EmotionAggregate(period_label="c", mean_valence=1.0),
    ]
    spark = sparkline_for_aggregates(aggs)
    assert len(spark) == 3
    assert spark[0] == "▁"
    assert spark[-1] == "█"


@pytest.mark.unit
def test_aggregates_sorted_by_period() -> None:
    recs = [
        {"ts": "2026-03-15T10:00", "label": "happy"},
        {"ts": "2025-11-01T10:00", "label": "sad"},
        {"ts": "2026-01-10T10:00", "label": "neutral"},
    ]
    labels = [a.period_label for a in EmotionDriftAnalyzer(recs).aggregate("month")]
    assert labels == sorted(labels) == ["2025-11", "2026-01", "2026-03"]


@pytest.mark.unit
def test_analyzer_accepts_history_object() -> None:
    class FakeHistory:
        def __init__(self, recs):
            self._r = recs

        def get_recent(self, n=50):
            return self._r[-n:]

    recs = [{"ts": "2026-04-01T10:00", "label": "happy"}]
    analyzer = EmotionDriftAnalyzer(history=FakeHistory(recs))
    out = analyzer.aggregate("week")
    assert len(out) == 1 and out[0].dominant == "happy"


@pytest.mark.integration
def test_generate_emotion_report_script_no_plot(tmp_path: Path) -> None:
    history_file = tmp_path / "emotion_history.json"
    history_file.write_text(
        json.dumps(
            [
                {"ts": "2026-04-01T10:00", "label": "happy"},
                {"ts": "2026-04-08T10:00", "label": "sad"},
            ]
        ),
        encoding="utf-8",
    )
    script = ROOT / "scripts" / "generate_emotion_report.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--window",
            "week",
            "--input",
            str(history_file),
            "--no-plot",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "valence sparkline" in result.stdout


@pytest.mark.unit
def test_ui_module_importable_without_display() -> None:
    """tkinter が使えない環境でも import 時エラーにならない。"""
    # import だけで Toplevel 呼び出しはしない
    from ui import emotion_drift_window as mod

    text = mod.render_text_summary([])
    assert "(データがまだ足りません)" in text
