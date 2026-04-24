#!/usr/bin/env python3
"""
感情ドリフト「心の健康診断」レポート生成スクリプト。

使用例:
    python scripts/generate_emotion_report.py --window week
    python scripts/generate_emotion_report.py --window month --input path/to/history.json
    python scripts/generate_emotion_report.py --window year --no-plot

matplotlib 未インストール時や ``--no-plot`` 指定時は ASCII sparkline のみ標準出力に出す。
画像は ``artifacts/emotion_reports/<YYYY-MM-DD>_<window>.png`` に保存される。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

# リポジトリルートを import path に追加 (スクリプト単体実行対応)
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.emotion_drift import (  # noqa: E402
    EmotionAggregate,
    EmotionDriftAnalyzer,
    sparkline_for_aggregates,
)

logger = logging.getLogger("emotion_report")


def _load_records(path: Optional[Path]) -> List[dict]:
    if path is None:
        candidates = [
            _ROOT / "data" / "tenants" / "self" / "emotion_history.json",
            _ROOT / "data" / "emotion_history.json",
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
    if path is None or not path.exists():
        logger.warning("emotion_history.json not found; returning empty list")
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("failed to read %s: %s", path, exc)
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def _render_matplotlib(
    aggregates: Sequence[EmotionAggregate],
    out_path: Path,
) -> bool:
    """matplotlib で折れ線 + 積み上げ棒グラフを書き出す。成功したら True."""
    try:
        import matplotlib  # type: ignore

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - matplotlib 未導入環境用
        logger.info("matplotlib unavailable: %s", exc)
        return False

    if not aggregates:
        logger.info("no aggregates to plot")
        return False

    labels = [a.period_label for a in aggregates]
    valences = [a.mean_valence for a in aggregates]

    # 積み上げ棒用にすべての emotion キーを収集
    all_keys: List[str] = []
    for a in aggregates:
        for k in a.counts:
            if k not in all_keys:
                all_keys.append(k)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    ax1.plot(labels, valences, marker="o", color="#6C5CE7", linewidth=2)
    ax1.axhline(0.0, color="#CCCCCC", linewidth=0.8, linestyle="--")
    ax1.set_ylabel("mean valence")
    ax1.set_title("Emotional drift (mean valence)")
    ax1.grid(True, alpha=0.3)

    bottoms = [0.0] * len(aggregates)
    for key in all_keys:
        heights = [float(a.counts.get(key, 0)) for a in aggregates]
        ax2.bar(labels, heights, bottom=bottoms, label=key)
        bottoms = [b + h for b, h in zip(bottoms, heights)]
    ax2.set_ylabel("count")
    ax2.set_title("Emotion composition")
    ax2.legend(fontsize=8, loc="upper right")
    for tick in ax2.get_xticklabels():
        tick.set_rotation(45)
        tick.set_ha("right")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def _print_ascii_summary(aggregates: Sequence[EmotionAggregate]) -> None:
    if not aggregates:
        print("(no data)")
        return
    spark = sparkline_for_aggregates(aggregates)
    print(f"valence sparkline: {spark}")
    for a in aggregates:
        print(
            f"  {a.period_label}  n={a.sample_size:<4d}  "
            f"valence={a.mean_valence:+.3f}  dominant={a.dominant}"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate emotion drift report")
    p.add_argument(
        "--window",
        choices=("week", "month", "year"),
        default="week",
        help="aggregation window",
    )
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="explicit path to emotion_history.json",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "artifacts" / "emotion_reports",
        help="directory to write the PNG report",
    )
    p.add_argument(
        "--no-plot",
        action="store_true",
        help="skip matplotlib rendering even if available",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    records = _load_records(args.input)
    analyzer = EmotionDriftAnalyzer(records)
    aggregates = analyzer.aggregate(args.window)

    _print_ascii_summary(aggregates)

    if args.no_plot:
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    out_path = Path(args.out_dir) / f"{today}_{args.window}.png"
    rendered = _render_matplotlib(aggregates, out_path)
    if rendered:
        print(f"wrote: {out_path}")
    else:
        print("(matplotlib unavailable or no data; ASCII fallback only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
