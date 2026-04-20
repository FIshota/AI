"""ai-chan benchmark runner (Phase 0 skeleton).

Phase 0 の責務はスイート一覧表示と describe() 呼び出しまで。
実行ロジックは各スイートの `run()` 側に委譲する (現状は空リストを返すスタブ)。

Usage:
    python3 bench/runner.py --list
    python3 bench/runner.py --model sarashina2-7b --suite jglue
    python3 bench/runner.py --model sarashina2-7b --all
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# core/llm.py の MODEL_FAMILIES を参照
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.suites import SUITES  # noqa: E402


def _known_families() -> list[str]:
    try:
        from core.llm import MODEL_FAMILIES  # type: ignore

        return list(MODEL_FAMILIES.keys())
    except Exception:
        return ["sarashina2-7b"]


def cmd_list() -> int:
    print("Available suites:")
    for name, mod in SUITES.items():
        info = mod.describe()
        print(f"  - {name:20s} ({info.get('status','?')})  license={info.get('license','?')}")
    print()
    print(f"Known model families: {', '.join(_known_families())}")
    return 0


def cmd_run(
    model: str,
    suite: str | None,
    run_all: bool,
    limit: int | None,
    qid_prefix: str | None = None,
) -> int:
    if model not in _known_families():
        print(f"[bench] ⚠ 未知の model_family: {model} (続行)")
    targets = list(SUITES.keys()) if run_all else [suite] if suite else []
    if not targets:
        print("[bench] --suite か --all を指定してください", file=sys.stderr)
        return 2

    out_dir = Path("bench/results") / date.today().isoformat() / model
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in targets:
        mod = SUITES.get(name)
        if not mod:
            print(f"[bench] 不明なスイート: {name}", file=sys.stderr)
            continue
        info = mod.describe()
        tag = f" qid_prefix={qid_prefix!r}" if qid_prefix else ""
        print(f"[bench] run {name} on {model} ({info.get('status','?')}){tag}")
        try:
            results = mod.run(model_family=model, limit=limit, qid_prefix=qid_prefix)
        except TypeError:
            # backward compat: suite が qid_prefix をまだ受けない場合
            results = mod.run(model_family=model, limit=limit)
        payload = {
            "suite": name,
            "model_family": model,
            "describe": info,
            "results": [
                r.__dict__ if hasattr(r, "__dict__") else dict(r._asdict())
                for r in results
            ],
        }
        for r in results:
            print(f"  - {getattr(r, 'metric', '?')}: {getattr(r, 'value', '?')}")
        (out_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"[bench] done → {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ai-chan benchmark runner")
    p.add_argument("--list", action="store_true", help="list available suites")
    p.add_argument("--model", default="sarashina2-7b", help="model family name")
    p.add_argument("--suite", default=None, help="single suite to run")
    p.add_argument("--all", action="store_true", help="run all suites")
    p.add_argument("--limit", type=int, default=None, help="per-suite item limit")
    p.add_argument(
        "--qid-prefix",
        default=None,
        help="filter items by qid prefix (e.g. 'honesty_' for Memory Honesty seeds)",
    )
    args = p.parse_args(argv)

    if args.list:
        return cmd_list()
    return cmd_run(
        args.model, args.suite, args.all, args.limit, qid_prefix=args.qid_prefix
    )


if __name__ == "__main__":
    raise SystemExit(main())
