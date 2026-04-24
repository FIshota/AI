# -*- coding: utf-8 -*-
"""Tests for scripts/scan_brand_misuse.py."""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

# スクリプトを import path に追加
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scan_brand_misuse as sbm  # type: ignore  # noqa: E402


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")


# ------------------------------------------------------------------
# tests
# ------------------------------------------------------------------

def test_scan_text_detects_all_brands() -> None:
    text = "HinoMoto is here\nAi speaks.\nYAMATO boots.\nKAGUYA research.\nai-chan runs.\n"
    hits = sbm.scan_text(text)
    brands = {b for (_, b, _) in hits}
    assert {"HinoMoto", "Ai", "YAMATO", "KAGUYA", "ai-chan"} <= brands


def test_scan_text_does_not_false_match_ai_lowercase() -> None:
    # "AI" (uppercase ALL) and "ai" (lowercase) should NOT match the "Ai" pattern.
    text = "AI is an acronym. ai is lowercase. Airline flies."
    hits = sbm.scan_text(text)
    brands = [b for (_, b, _) in hits]
    assert "Ai" not in brands


def test_is_path_in_allowed() -> None:
    assert sbm.is_path_in_allowed("docs/legal/TRADEMARK.md") is True
    assert sbm.is_path_in_allowed("tests/test_foo.py") is True
    assert sbm.is_path_in_allowed("config/app.yml") is True
    assert sbm.is_path_in_allowed("core/engine.py") is False
    assert sbm.is_path_in_allowed("scripts/foo.py") is False


def test_scan_repository_separates_warnings_and_info(tmp_path: Path) -> None:
    # docs 配下 → informational のみ
    _write(tmp_path / "docs" / "a.md", "This mentions HinoMoto and YAMATO.\n")
    # core 配下 → warning
    _write(tmp_path / "core" / "b.py", "# use ai-chan brand here\nprint('KAGUYA')\n")
    # 商標無しファイル
    _write(tmp_path / "utils" / "c.py", "x = 1\n")

    result = sbm.scan_repository(str(tmp_path))
    assert len(result.hits) >= 3
    assert len(result.warnings) >= 2  # core/b.py の 2 行
    assert len(result.informational) >= 1  # docs/a.md
    warn_paths = {h.path.replace(os.sep, "/") for h in result.warnings}
    assert any("core/b.py" in p for p in warn_paths)


def test_main_always_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path / "core" / "x.py", "HinoMoto\nAi\nYAMATO\n")
    rc = sbm.main(["--root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Brand Misuse Scan" in captured.out


def test_main_quiet_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path / "docs" / "x.md", "HinoMoto\n")
    rc = sbm.main(["--root", str(tmp_path), "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "warnings=" in out
    assert "total=" in out
