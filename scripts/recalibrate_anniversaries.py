"""全 anniversary の auto_importance を再計算するスクリプト。

既定は dry-run で `artifacts/anniversary_recalibration_<date>.json` に
レポートを書き出すのみ。`--apply` を付けると DB (anniversaries.json) にも
反映する。

使い方:
    python scripts/recalibrate_anniversaries.py [--apply]
    python scripts/recalibrate_anniversaries.py --data-dir ./data --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# プロジェクトルートを sys.path に追加
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.anniversary import AnniversaryManager  # noqa: E402
from core.anniversary_importance import (  # noqa: E402
    AnniversaryFeatures,
    bucket_of,
    estimate_importance,
)

logger = logging.getLogger("recalibrate_anniversaries")


def _extract_features(item: Dict[str, Any]) -> AnniversaryFeatures:
    """anniversary エントリから特徴量を抽出する。

    エントリに stats (mention_count 等) が無ければ保守的なデフォルトを使う。
    """
    stats: Dict[str, Any] = item.get("stats", {}) if isinstance(item, dict) else {}
    today_iso = datetime.now(timezone.utc).isoformat()
    return AnniversaryFeatures(
        keyword=str(item.get("label", item.get("id", ""))),
        mention_count=int(stats.get("mention_count", 0)),
        mean_valence=float(stats.get("mean_valence", 0.0)),
        first_seen_at=str(stats.get("first_seen_at", item.get("created_at", today_iso))),
        last_seen_at=str(stats.get("last_seen_at", item.get("updated_at", today_iso))),
        session_total_minutes=float(stats.get("session_total_minutes", 0.0)),
    )


def recalibrate(
    data_dir: Path, apply: bool = False, output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    mgr = AnniversaryManager(data_dir=data_dir)
    items = mgr.list_all()

    report_rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for item in items:
        features = _extract_features(item)
        score = estimate_importance(features, now=now)
        bucket = bucket_of(score)
        previous = item.get("auto_importance", {}).get("score") if isinstance(
            item.get("auto_importance"), dict
        ) else None
        row: Dict[str, Any] = {
            "id": item.get("id"),
            "label": item.get("label"),
            "previous_score": previous,
            "new_score": round(score, 4),
            "bucket": bucket.value,
            "features": {
                "mention_count": features.mention_count,
                "mean_valence": features.mean_valence,
                "session_total_minutes": features.session_total_minutes,
                "last_seen_at": features.last_seen_at,
            },
        }
        report_rows.append(row)

        if apply:
            mgr.attach_auto_importance(
                label_or_id=item.get("id") or item.get("label", ""),
                score=score,
                bucket=bucket.value,
                persist=False,
            )

    if apply:
        mgr._save()  # 一括保存

    out_dir = output_dir or (_ROOT / "artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"anniversary_recalibration_{date.today().isoformat()}.json"
    report: Dict[str, Any] = {
        "generated_at": now.isoformat(),
        "data_dir": str(data_dir),
        "applied": apply,
        "total": len(report_rows),
        "entries": report_rows,
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    logger.info("Report written: %s (applied=%s)", out_path, apply)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Recalibrate anniversary auto_importance")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_ROOT / "data",
        help="ai-chan data directory (default: ./data)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write recomputed auto_importance back to DB (default: dry-run)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    report = recalibrate(data_dir=args.data_dir, apply=args.apply)
    print(
        f"Processed {report['total']} anniversaries "
        f"(applied={report['applied']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
