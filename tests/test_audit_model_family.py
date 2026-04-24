# -*- coding: utf-8 -*-
"""Tests for scripts/audit_model_family.py (MODEL_FAMILY DTA)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_model_family as afm  # noqa: E402


HEADER = (
    "| モデル名 | 公開範囲 | vocab | d_model | n_layers | パラメータ数 "
    "| 学習コーパス | ライセンス | 想定ユーザ |"
)
SEP = "|---|---|---|---|---|---|---|---|---|"


def _md(rows_text: str) -> str:
    return "\n".join(["# title", "", HEADER, SEP, rows_text.strip(), ""])


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def test_extract_table_basic(tmp_path: Path) -> None:
    body = _md("| HinoMoto-v1 | 研究内部 | 8000 | 256 | 8 | 5.3M | wiki | Apache-2.0 | 研究者 |")
    p = _write(tmp_path, "A.md", body)
    rows = afm.extract_model_table(p)
    assert len(rows) == 1
    assert rows[0]["モデル名"] == "HinoMoto-v1"
    assert rows[0]["d_model"] == "256"


def test_ok_identical_tables(tmp_path: Path) -> None:
    row = "| HinoMoto-v1 | 研究内部 | 8000 | 256 | 8 | 5.3M | wiki | Apache-2.0 | 研究者 |"
    a = _write(tmp_path, "A.md", _md(row))
    b = _write(tmp_path, "B.md", _md(row))
    assert afm.run_audit(a, b) == 0


def test_tbd_is_not_conflict(tmp_path: Path) -> None:
    row_a = "| Ai | 非公開 | [TBD] | [TBD] | [TBD] | [TBD] | 本人のみ | Private | 開発者 |"
    row_b = "| Ai | 非公開 | 16000 | 384 | 10 | 12M | 本人のみ | Private | 開発者 |"
    a = _write(tmp_path, "A.md", _md(row_a))
    b = _write(tmp_path, "B.md", _md(row_b))
    assert afm.run_audit(a, b) == 0


def test_conflict_detected(tmp_path: Path) -> None:
    row_a = "| HinoMoto-v1 | 研究内部 | 8000 | 256 | 8 | 5.3M | wiki | Apache-2.0 | 研究者 |"
    row_b = "| HinoMoto-v1 | 研究内部 | 8000 | 512 | 8 | 5.3M | wiki | Apache-2.0 | 研究者 |"
    a = _write(tmp_path, "A.md", _md(row_a))
    b = _write(tmp_path, "B.md", _md(row_b))
    assert afm.run_audit(a, b) == 2


def test_missing_hinomoto_dir_is_warn_not_crash(tmp_path: Path) -> None:
    row = "| HinoMoto-v1 | 研究内部 | 8000 | 256 | 8 | 5.3M | wiki | Apache-2.0 | 研究者 |"
    a = _write(tmp_path, "A.md", _md(row))
    missing = tmp_path / "does_not_exist" / "MODEL_FAMILY.md"
    # should warn and return 0, not crash
    assert afm.run_audit(a, missing) == 0


def test_tbd_count(tmp_path: Path) -> None:
    row = "| Ai | 非公開 | [TBD] | [TBD] | [TBD] | [TBD] | 本人 | Private | 開発者 |"
    p = _write(tmp_path, "A.md", _md(row))
    rows = afm.extract_model_table(p)
    assert afm.count_tbd(rows) == 4
