"""scripts/audit_journal_dates.py の単体テスト."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import List

import pytest

# scripts ディレクトリを import path に追加
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_journal_dates as aud  # noqa: E402


def _write_journal(tmp_path: Path, content: str) -> Path:
    """tmp_path に docs/JOURNAL.md を作成してリポジトリルートを返す."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "JOURNAL.md").write_text(content, encoding="utf-8")
    return tmp_path


def test_parse_entries_extracts_date_headings(tmp_path: Path) -> None:
    root = _write_journal(
        tmp_path,
        "# Top\n\n## 2026-04-23\n\ncontent\n\n## 2026-04-20\nmore\n\n### not-a-date 2026-01-01\n",
    )
    entries = aud.parse_entries(root / "docs" / "JOURNAL.md")
    dates = [e.date for e in entries]
    assert dates == [date(2026, 4, 23), date(2026, 4, 20)]


def test_audit_flags_future_date_as_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_journal(tmp_path, "## 2030-01-01\nfuture\n")
    # git を呼ばせない
    monkeypatch.setattr(aud, "count_commits_on", lambda repo, d: 1)
    entries = aud.parse_entries(root / "docs" / "JOURNAL.md")
    findings, _ = aud.audit(entries, root, today=date(2026, 4, 23))
    assert any(
        f.severity == "ERROR" and "未来日" in f.message for f in findings
    )


def test_audit_warns_on_descending_order_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_journal(
        tmp_path,
        "## 2026-04-20\nold\n\n## 2026-04-23\nnewer below (bad order)\n",
    )
    monkeypatch.setattr(aud, "count_commits_on", lambda repo, d: 1)
    entries = aud.parse_entries(root / "docs" / "JOURNAL.md")
    findings, _ = aud.audit(entries, root, today=date(2026, 4, 23))
    assert any(
        f.severity == "WARN" and "降順違反" in f.message for f in findings
    )


def test_audit_warns_when_commits_are_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_journal(tmp_path, "## 2026-04-22\nno commits that day\n")
    monkeypatch.setattr(aud, "count_commits_on", lambda repo, d: 0)
    entries = aud.parse_entries(root / "docs" / "JOURNAL.md")
    findings, _ = aud.audit(entries, root, today=date(2026, 4, 23))
    assert any(
        f.severity == "WARN" and "コミットが 0 件" in f.message for f in findings
    )


def test_audit_skips_when_git_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_journal(tmp_path, "## 2026-04-22\nentry\n")
    monkeypatch.setattr(aud, "count_commits_on", lambda repo, d: None)
    entries = aud.parse_entries(root / "docs" / "JOURNAL.md")
    findings, skipped = aud.audit(entries, root, today=date(2026, 4, 23))
    # コミット不在 WARN は出ないこと / SKIP フラグが立つこと
    assert skipped is True
    assert not any("コミットが 0 件" in f.message for f in findings)


def test_run_returns_zero_when_no_journal(tmp_path: Path) -> None:
    # docs も JOURNAL も無い
    rc = aud.run(tmp_path, today=date(2026, 4, 23))
    assert rc == 0


def test_run_returns_two_on_future_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_journal(tmp_path, "## 2099-01-01\nfuture\n")
    monkeypatch.setattr(aud, "count_commits_on", lambda repo, d: 1)
    rc = aud.run(tmp_path, today=date(2026, 4, 23))
    assert rc == 2
