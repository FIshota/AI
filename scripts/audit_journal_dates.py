#!/usr/bin/env python3
"""JOURNAL 日付整合性監査スクリプト.

docs/JOURNAL.md (または docs/journal/*.md) の ``## YYYY-MM-DD`` 見出しと
実際の git コミット履歴 / ファイル修正時刻の整合性を自動チェックする。

判定基準:
  - 見出し日付 > 今日 の場合: ERROR (未来日)
  - 見出し日付のコミットが 0 件の場合: WARN (記録と実態の乖離)
  - 見出し順が降順でない場合: WARN

終了コード:
  0: 違反なし (WARN のみでも clean 扱い)
  2: ERROR 検出 (未来日など)
  0: git コマンド不在 / repo でない場合は SKIP 扱い (exit 0)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# 日付見出しの正規表現 (例: "## 2026-04-23")
HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")


@dataclass(frozen=True)
class JournalEntry:
    """JOURNAL 内の 1 つの日付見出しを表す."""

    source: Path
    date: date
    line_no: int


@dataclass(frozen=True)
class AuditFinding:
    """監査結果の 1 件."""

    severity: str  # "ERROR" | "WARN" | "INFO"
    entry: JournalEntry
    message: str


def discover_journals(docs_dir: Path) -> List[Path]:
    """docs/ 配下から JOURNAL ファイルを列挙する.

    優先順位:
      1. docs/JOURNAL.md (単一ファイル)
      2. docs/journal/*.md (複数ファイル)
    """
    result: List[Path] = []
    single = docs_dir / "JOURNAL.md"
    if single.is_file():
        result.append(single)
    subdir = docs_dir / "journal"
    if subdir.is_dir():
        result.extend(sorted(subdir.glob("*.md")))
    return result


def parse_entries(path: Path) -> List[JournalEntry]:
    """JOURNAL ファイルから日付見出しを抽出する."""
    entries: List[JournalEntry] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return entries
    for i, line in enumerate(text.splitlines(), start=1):
        m = HEADING_RE.match(line)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        entries.append(JournalEntry(source=path, date=d, line_no=i))
    return entries


def count_commits_on(repo_root: Path, day: date) -> Optional[int]:
    """指定日のコミット数を git log で取得する.

    git コマンドが無い / repo でない場合は ``None`` を返して SKIP 扱い.
    """
    since = day.strftime("%Y-%m-%d 00:00:00")
    until = day.strftime("%Y-%m-%d 23:59:59")
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                f"--since={since}",
                f"--until={until}",
                "--format=%H",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return len(lines)


def audit(
    entries: Sequence[JournalEntry],
    repo_root: Path,
    today: date,
) -> Tuple[List[AuditFinding], bool]:
    """監査を実施し findings と git SKIP フラグを返す."""
    findings: List[AuditFinding] = []
    git_skipped = False

    # 未来日チェック
    for e in entries:
        if e.date > today:
            findings.append(
                AuditFinding(
                    severity="ERROR",
                    entry=e,
                    message=f"未来日: {e.date.isoformat()} (今日={today.isoformat()})",
                )
            )

    # 降順チェック (ファイル単位)
    by_source: dict = {}
    for e in entries:
        by_source.setdefault(e.source, []).append(e)
    for src, items in by_source.items():
        for prev, cur in zip(items, items[1:]):
            if cur.date > prev.date:
                findings.append(
                    AuditFinding(
                        severity="WARN",
                        entry=cur,
                        message=(
                            f"降順違反: {prev.date.isoformat()} の後に "
                            f"{cur.date.isoformat()} が出現"
                        ),
                    )
                )

    # コミット不在チェック (未来日はスキップ)
    for e in entries:
        if e.date > today:
            continue
        n = count_commits_on(repo_root, e.date)
        if n is None:
            git_skipped = True
            continue
        if n == 0:
            findings.append(
                AuditFinding(
                    severity="WARN",
                    entry=e,
                    message=f"{e.date.isoformat()} のコミットが 0 件 (記録と実態が乖離)",
                )
            )
    return findings, git_skipped


def format_finding(f: AuditFinding) -> str:
    rel = f.entry.source
    return f"[{f.severity}] {rel}:{f.entry.line_no}: {f.message}"


def run(repo_root: Path, today: Optional[date] = None) -> int:
    """CLI エントリポイント本体. 終了コードを返す."""
    today = today or date.today()
    docs_dir = repo_root / "docs"
    journals = discover_journals(docs_dir)
    if not journals:
        print(f"[INFO] JOURNAL ファイルが見つかりません: {docs_dir}")
        return 0

    all_entries: List[JournalEntry] = []
    for j in journals:
        all_entries.extend(parse_entries(j))

    if not all_entries:
        print("[INFO] 日付見出しが 1 件も見つかりません")
        return 0

    findings, git_skipped = audit(all_entries, repo_root, today)
    errors = [f for f in findings if f.severity == "ERROR"]
    warns = [f for f in findings if f.severity == "WARN"]

    for f in findings:
        print(format_finding(f))

    print(
        f"\n[SUMMARY] entries={len(all_entries)} "
        f"errors={len(errors)} warns={len(warns)}"
        + (" git=SKIPPED" if git_skipped else "")
    )

    if errors:
        return 2
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="JOURNAL 日付整合性監査")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="リポジトリルート (既定: スクリプトの親ディレクトリ)",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="今日の日付 (YYYY-MM-DD, 主にテスト用)",
    )
    args = parser.parse_args(argv)
    today: Optional[date] = None
    if args.today:
        today = datetime.strptime(args.today, "%Y-%m-%d").date()
    return run(args.repo_root, today=today)


if __name__ == "__main__":
    sys.exit(main())
