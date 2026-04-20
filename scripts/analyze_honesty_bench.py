#!/usr/bin/env python3
"""H-1: honesty bench 結果を aspect 別に集計.

Usage:
    python3 scripts/analyze_honesty_bench.py \
        bench/results/YYYY-MM-DD/sarashina2-7b/family_dialog.json

rule / semantic / honesty 判定を aspect (forget/uncertain/conflict/emotion_first)
別に heatmap 形式で表示する。
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def _aspect_from_qid(qid: str) -> str:
    # honesty_forget_01 → forget
    parts = qid.split("_")
    if len(parts) < 3 or parts[0] != "honesty":
        return "other"
    if parts[1] in ("emotion",):
        return "emotion_first"  # honesty_emotion_first_01
    return parts[1]


def main(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"not found: {p}", file=sys.stderr)
        return 1
    data = json.loads(p.read_text(encoding="utf-8"))

    # describe の直下に results があるケースと per-item details があるケースを両対応
    # runner.py の payload は aggregate のみ。生データは別途 records 経由が必要
    results = data.get("results", [])
    if not results:
        print("no results")
        return 2

    print(f"# suite: {data.get('suite','?')}  model: {data.get('model_family','?')}")
    print(f"# describe: {data.get('describe',{}).get('status','?')}")
    print()
    print("## Aggregate (全 honesty_* 問題)")
    for r in results:
        metric = r.get("metric", "?")
        value = r.get("value", 0.0)
        print(f"  - {metric:30s}: {value:.4f}")

    # records が別ファイルにある場合 (将来拡張)
    details_path = p.with_name(f"{p.stem}_details.jsonl")
    if details_path.exists():
        print()
        print("## Per-aspect breakdown")
        rows = [json.loads(line) for line in details_path.read_text().splitlines() if line]
        by_aspect: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in rows:
            aspect = _aspect_from_qid(row.get("qid", ""))
            for judge_name, score in row.get("scores", {}).items():
                by_aspect[aspect][judge_name].append(score)
        for aspect, judges in sorted(by_aspect.items()):
            print(f"\n### {aspect}")
            for j, scores in sorted(judges.items()):
                if not scores:
                    continue
                mean = statistics.mean(scores)
                print(f"  {j:12s} mean={mean:.3f}  n={len(scores)}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
