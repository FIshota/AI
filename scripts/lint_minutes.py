#!/usr/bin/env python3
"""lint_minutes.py — docs/minutes/ の議事録ファイルに必須セクションが
含まれているかチェックする。

使い方:
    python scripts/lint_minutes.py [PATH ...]

引数を省略した場合は、リポジトリ直下の docs/minutes/ 配下の *.md を
(TEMPLATE.md を除いて) すべてチェックする。

終了コード:
    0 : 全ファイル OK
    2 : 1 ファイル以上で必須セクション欠落
    1 : 使い方エラーや想定外例外

Python 3.9 互換、stdlib のみ。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

REQUIRED_SECTIONS: Tuple[str, ...] = (
    "日付",
    "参加者",
    "議題",
    "決定事項",
    "未決事項",
    "次回アクション",
)

# "## <section>" にマッチするヘッダ正規表現
_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def extract_sections(text: str) -> List[str]:
    """本文から ## で始まる見出しのタイトル一覧を返す。"""
    return [m.group(1).strip() for m in _HEADER_RE.finditer(text)]


def check_file(path: Path) -> List[str]:
    """必須セクションのうち欠落しているものを返す。空なら OK。"""
    text = path.read_text(encoding="utf-8")
    sections = set(extract_sections(text))
    return [s for s in REQUIRED_SECTIONS if s not in sections]


def iter_default_targets(repo_root: Path) -> Iterable[Path]:
    minutes_dir = repo_root / "docs" / "minutes"
    if not minutes_dir.is_dir():
        return []
    return sorted(
        p for p in minutes_dir.glob("*.md") if p.name != "TEMPLATE.md"
    )


def resolve_targets(args_paths: List[str], repo_root: Path) -> List[Path]:
    if not args_paths:
        return list(iter_default_targets(repo_root))
    resolved: List[Path] = []
    for raw in args_paths:
        p = Path(raw)
        if p.is_dir():
            resolved.extend(
                sorted(q for q in p.glob("*.md") if q.name != "TEMPLATE.md")
            )
        else:
            resolved.append(p)
    return resolved


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="チェック対象のファイル/ディレクトリ")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    targets = resolve_targets(ns.paths, repo_root)

    if not targets:
        print("lint_minutes: チェック対象ファイルがありません", file=sys.stderr)
        return 0

    had_error = False
    for path in targets:
        if not path.exists():
            print(f"NG  {path}: ファイルが存在しません", file=sys.stderr)
            had_error = True
            continue
        missing = check_file(path)
        if missing:
            had_error = True
            print(
                f"NG  {path}: 欠落セクション: {', '.join(missing)}",
                file=sys.stderr,
            )
        else:
            print(f"OK  {path}")

    return 2 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
