# -*- coding: utf-8 -*-
"""Tests for scripts/check_crypto_surface.py

Python 3.9 stdlib (pytest + tempfile) only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_crypto_surface as ccs  # noqa: E402


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_scan_file_detects_expected_modules(tmp_path: Path) -> None:
    """import hashlib / from hmac import / from cryptography.fernet がすべて検出されること."""
    f = _write(
        tmp_path,
        "sample.py",
        "import hashlib\n"
        "from hmac import compare_digest\n"
        "from cryptography.fernet import Fernet\n"
        "import json\n"  # 非対象
        "import secrets as s\n",
    )
    findings = ccs.scan_file(f)
    mods = sorted({x.module for x in findings})
    assert "hashlib" in mods
    assert "hmac" in mods
    assert "cryptography" in mods
    assert "secrets" in mods
    assert "json" not in mods
    # 少なくとも 4 件
    assert len(findings) >= 4


def test_scan_tree_excludes_common_dirs_and_counts(tmp_path: Path) -> None:
    """__pycache__ / .git 配下はスキャンされないこと、カウントが正しいこと."""
    _write(tmp_path, "pkg/a.py", "import hashlib\n")
    _write(tmp_path, "pkg/b.py", "import hmac\nimport hashlib\n")
    _write(tmp_path, "__pycache__/ignored.py", "import cryptography\n")
    _write(tmp_path, ".git/hooks.py", "import secrets\n")
    _write(tmp_path, "pkg/notpy.txt", "import hashlib\n")  # non-.py

    result = ccs.scan_tree(tmp_path)
    assert result.scanned_files == 2  # a.py, b.py のみ
    counts = result.by_module()
    assert counts.get("hashlib") == 2
    assert counts.get("hmac") == 1
    # excluded dirs 内のものは拾わない
    assert "cryptography" not in counts
    # secrets は .git 配下にあるので拾わない
    assert counts.get("secrets") is None


def test_render_report_contains_disclaimer_and_metadata(tmp_path: Path) -> None:
    """レポートに disclaimer・メタデータ・findings セクションが含まれること."""
    _write(tmp_path, "x.py", "import hashlib\n")
    result = ccs.scan_tree(tmp_path)
    text = ccs.render_report(result)
    assert "Disclaimer" in text
    assert "not a legal" in text
    assert "scan_root" in text
    assert "scanned_files" in text
    assert "hashlib" in text
    # findings セクションに path:line が含まれる
    assert "x.py:1" in text


def test_write_report_creates_output_file(tmp_path: Path) -> None:
    """write_report が親ディレクトリを作成しつつファイルを生成すること."""
    _write(tmp_path, "src/y.py", "from cryptography.hazmat.primitives import hashes\n")
    result = ccs.scan_tree(tmp_path)
    out = tmp_path / "reports" / "nested" / "crypto_surface_report.txt"
    written = ccs.write_report(result, out)
    assert written == out
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "cryptography" in body


def test_main_returns_error_for_missing_root(tmp_path: Path) -> None:
    """存在しない root を渡した場合に 0 以外が返ること."""
    missing = tmp_path / "does_not_exist"
    rc = ccs.main(["--root", str(missing), "--output", str(tmp_path / "r.txt")])
    assert rc != 0


def test_main_happy_path_writes_report(tmp_path: Path) -> None:
    """正常系: main が 0 を返し、レポートが書かれること."""
    _write(tmp_path, "m.py", "import hashlib\nimport hmac\n")
    out = tmp_path / "legal" / "report.txt"
    rc = ccs.main(["--root", str(tmp_path), "--output", str(out)])
    assert rc == 0
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "hashlib" in body
    assert "hmac" in body


def test_iter_python_files_skips_hidden_dirs(tmp_path: Path) -> None:
    """hidden (dot) ディレクトリがスキップされること."""
    _write(tmp_path, ".hidden/x.py", "import hashlib\n")
    _write(tmp_path, "visible/y.py", "import hashlib\n")
    files = list(ccs.iter_python_files(tmp_path))
    paths = [str(p) for p in files]
    assert any("visible" in p for p in paths)
    assert not any(".hidden" in p for p in paths)
