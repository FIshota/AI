"""Tests for scripts/privacy_lint.py."""

from __future__ import annotations

import os
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import privacy_lint  # noqa: E402


VALID_PRIVACY = textwrap.dedent(
    """
    # PRIVACY

    ## 🔑 3 行まとめ
    ok

    ## 📦 データカテゴリ一覧
    クリップボード / スクリーンショット / 日記 / カレンダー / 声紋 / 感情 / 監査

    ## 🔴 Kill-Switch
    one command

    ## 🌐 外部通信
    opt-in

    ## 🧒 未成年
    care

    ## 📜 更新履歴
    2026-04-23
    """
).strip()


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_valid_privacy_passes(tmp_path):
    privacy = tmp_path / "docs" / "PRIVACY.md"
    core = tmp_path / "core"
    core.mkdir()
    _write(str(privacy), VALID_PRIVACY)
    code, messages = privacy_lint.run_lint(str(privacy), str(core))
    assert code == 0, messages
    assert messages == []


def test_missing_file_returns_2(tmp_path):
    privacy = tmp_path / "docs" / "PRIVACY.md"
    code, messages = privacy_lint.run_lint(str(privacy), str(tmp_path / "core"))
    assert code == 2
    assert any("not found" in m for m in messages)


def test_missing_headings_detected(tmp_path):
    privacy = tmp_path / "PRIVACY.md"
    _write(str(privacy), "# PRIVACY\n\n## 🔑 3 行まとめ\nonly this\n")
    code, messages = privacy_lint.run_lint(str(privacy), str(tmp_path / "core"))
    assert code == 1
    joined = "\n".join(messages)
    assert "Missing headings" in joined
    assert "Kill-Switch" in joined
    assert "更新履歴" in joined


def test_undeclared_module_detected(tmp_path):
    privacy = tmp_path / "PRIVACY.md"
    # Text covers all headings but does NOT mention "クリップボード" / clipboard.
    text = VALID_PRIVACY.replace("クリップボード / ", "")
    _write(str(privacy), text)
    core = tmp_path / "core"
    core.mkdir()
    (core / "clipboard_watcher.py").write_text("# module\n")
    code, messages = privacy_lint.run_lint(str(privacy), str(core))
    assert code == 1
    assert any("Undeclared" in m and "clipboard_watcher" in m for m in messages)


def test_declared_module_passes(tmp_path):
    privacy = tmp_path / "PRIVACY.md"
    _write(str(privacy), VALID_PRIVACY)
    core = tmp_path / "core"
    core.mkdir()
    (core / "clipboard_watcher.py").write_text("# module\n")
    (core / "diary.py").write_text("# module\n")
    code, messages = privacy_lint.run_lint(str(privacy), str(core))
    assert code == 0, messages


def test_check_required_headings_all_present():
    missing = privacy_lint.check_required_headings(VALID_PRIVACY)
    assert missing == []


def test_check_required_headings_missing_one():
    text = VALID_PRIVACY.replace("## 🔴 Kill-Switch", "## ignored")
    missing = privacy_lint.check_required_headings(text)
    assert "Kill-Switch" in missing


def test_real_repo_privacy_passes():
    """Smoke test against the actual repo PRIVACY.md."""
    privacy = os.path.join(ROOT, "docs", "PRIVACY.md")
    core = os.path.join(ROOT, "core")
    if not os.path.isfile(privacy):
        pytest.skip("docs/PRIVACY.md not present")
    code, messages = privacy_lint.run_lint(privacy, core)
    assert code == 0, messages


def test_main_exit_code(tmp_path, capsys):
    privacy = tmp_path / "docs" / "PRIVACY.md"
    _write(str(privacy), VALID_PRIVACY)
    (tmp_path / "core").mkdir()
    rc = privacy_lint.main(
        ["--root", str(tmp_path), "--privacy", str(privacy), "--core", str(tmp_path / "core")]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "privacy_lint: OK" in out
