"""
Git ログからカテゴリ分類された CHANGELOG.md を生成する。

コミットメッセージの先頭 prefix (feat/fix/refactor/docs/test/chore) で
自動分類し、Markdown 形式で出力する。
"""
from __future__ import annotations

import logging
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# コミットタイプの表示名マッピング
CATEGORY_LABELS: Dict[str, str] = {
    "feat": "New Features",
    "fix": "Bug Fixes",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "test": "Tests",
    "chore": "Chores",
    "perf": "Performance",
    "ci": "CI/CD",
    "style": "Style",
}

# コミットメッセージのパース用パターン
_COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|refactor|docs|test|chore|perf|ci|style)"
    r"(?:\((?P<scope>[^)]+)\))?:\s*(?P<desc>.+)$",
    re.IGNORECASE,
)


def parse_git_log(repo_dir: Path, since: str = "") -> List[Tuple[str, str, str, str]]:
    """git log を解析して (hash, date, type, description) のリストを返す。

    Parameters
    ----------
    repo_dir:
        Git リポジトリのルートディレクトリ。
    since:
        ``--since`` に渡す日付文字列 (例: ``"2024-01-01"``)。空なら全履歴。

    Returns
    -------
    list of (hash, date, category, description)
    """
    cmd = [
        "git", "-C", str(repo_dir), "log",
        "--pretty=format:%h|%ai|%s",
        "--no-merges",
    ]
    if since:
        cmd.append(f"--since={since}")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.error("git log failed: %s", result.stderr.strip())
            return []
    except FileNotFoundError:
        logger.error("git コマンドが見つかりません")
        return []
    except subprocess.TimeoutExpired:
        logger.error("git log がタイムアウトしました")
        return []

    entries: List[Tuple[str, str, str, str]] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        commit_hash, date_str, subject = parts
        m = _COMMIT_RE.match(subject)
        if m:
            category = m.group("type").lower()
            desc = m.group("desc").strip()
        else:
            category = "other"
            desc = subject.strip()
        entries.append((commit_hash, date_str[:10], category, desc))
    return entries


def generate_changelog(
    repo_dir: Path,
    since: str = "",
    output_path: Path | None = None,
) -> str:
    """CHANGELOG を Markdown 文字列として生成し、ファイルにも書き出す。"""
    entries = parse_git_log(repo_dir, since=since)
    if not entries:
        return "# Changelog\n\nNo commits found.\n"

    categorized: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    for commit_hash, date, category, desc in entries:
        categorized[category].append((commit_hash, date, desc))

    lines: List[str] = [
        "# Changelog",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 表示順: feat → fix → refactor → perf → docs → test → chore → ci → other
    order = ["feat", "fix", "refactor", "perf", "docs", "test", "chore", "ci", "style", "other"]
    for cat in order:
        items = categorized.get(cat)
        if not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat.capitalize())
        lines.append(f"## {label}")
        lines.append("")
        for commit_hash, date, desc in items:
            lines.append(f"- {desc} (`{commit_hash}`, {date})")
        lines.append("")

    md = "\n".join(lines)

    if output_path is None:
        output_path = repo_dir / "docs" / "CHANGELOG.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    logger.info("CHANGELOG を生成しました: %s", output_path)
    return md


def main() -> None:
    repo_dir = Path(__file__).parent.parent
    since = sys.argv[1] if len(sys.argv) > 1 else ""
    md = generate_changelog(repo_dir, since=since)
    print(md)


if __name__ == "__main__":
    main()
