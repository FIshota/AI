"""scripts/lint_minutes.py のテスト。

Python 3.9 互換、stdlib + pytest のみ。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_PATH = REPO_ROOT / "scripts" / "lint_minutes.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("lint_minutes", LINT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_minutes"] = module
    spec.loader.exec_module(module)
    return module


lint_minutes = _load_module()


TEMPLATE_BODY = """# 議事録: sample

## 日付

2026-04-23

## 参加者

- オーナー

## 議題

- テスト議題

## 決定事項

- 何か決める

## 未決事項

- なし

## 次回アクション

- [ ] フォローアップ — 期限: 2026-04-30
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_valid_minutes_passes(tmp_path, capsys):
    path = _write(tmp_path, "2026-04-23-ok.md", TEMPLATE_BODY)
    rc = lint_minutes.main([str(path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out
    assert str(path) in out


def test_missing_section_returns_exit_2(tmp_path, capsys):
    # 「決定事項」セクションを削除
    broken = TEMPLATE_BODY.replace("## 決定事項\n\n- 何か決める\n\n", "")
    path = _write(tmp_path, "2026-04-23-bad.md", broken)
    rc = lint_minutes.main([str(path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "決定事項" in err
    assert "NG" in err


def test_multiple_missing_sections_listed(tmp_path, capsys):
    body = "# タイトルのみ\n\n本文なし\n"
    path = _write(tmp_path, "2026-04-23-empty.md", body)
    rc = lint_minutes.main([str(path)])
    err = capsys.readouterr().err
    assert rc == 2
    # 必須セクションがすべて欠落している
    for name in (
        "日付",
        "参加者",
        "議題",
        "決定事項",
        "未決事項",
        "次回アクション",
    ):
        assert name in err


def test_directory_scan_skips_template(tmp_path, capsys):
    # TEMPLATE.md は無効な内容でも無視される
    _write(tmp_path, "TEMPLATE.md", "# broken template\n")
    ok_path = _write(tmp_path, "2026-04-23-ok.md", TEMPLATE_BODY)
    rc = lint_minutes.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert str(ok_path) in out
    assert "TEMPLATE.md" not in out


def test_extract_sections_parses_headers():
    text = "## 日付\n\n2026-04-23\n\n## 参加者\n\n- A\n"
    assert lint_minutes.extract_sections(text) == ["日付", "参加者"]
