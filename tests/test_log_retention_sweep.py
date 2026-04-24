"""Tests for scripts.log_retention_sweep.

Covers:
- load_policies: valid YAML, missing file, invalid shape
- scan_candidates: expired vs fresh files
- apply_deletions: actual removal
- dry-run: does not delete
- undeclared directories: skipped entirely
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest
import yaml

# ─────────────────────────────────────────────────────────────
# Load the sweep module by path (scripts/ is not a package).
# ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SWEEP_PATH = _PROJECT_ROOT / "scripts" / "log_retention_sweep.py"

_spec = importlib.util.spec_from_file_location("log_retention_sweep", _SWEEP_PATH)
assert _spec and _spec.loader
sweep = importlib.util.module_from_spec(_spec)
sys.modules["log_retention_sweep"] = sweep
_spec.loader.exec_module(sweep)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _make_file(path: Path, age_days: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    old = time.time() - age_days * 86400.0
    os.utime(path, (old, old))
    return path


def _write_config(tmp: Path, policies: dict) -> Path:
    cfg = tmp / "config" / "log_retention.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(yaml.safe_dump({"policies": policies}), encoding="utf-8")
    return cfg


# ─────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────
def test_load_policies_valid(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, {"logs/a": {"max_age_days": 30}})
    pols = sweep.load_policies(cfg)
    assert len(pols) == 1
    assert pols[0].rel_dir == "logs/a"
    assert pols[0].max_age_days == 30


def test_load_policies_missing_returns_empty(tmp_path: Path) -> None:
    assert sweep.load_policies(tmp_path / "nope.yaml") == []


def test_load_policies_invalid_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(yaml.safe_dump({"policies": {"logs/a": {"foo": 1}}}), encoding="utf-8")
    with pytest.raises(ValueError):
        sweep.load_policies(cfg)


def test_scan_finds_expired_and_skips_fresh(tmp_path: Path) -> None:
    _write_config(tmp_path, {"logs/a": {"max_age_days": 10}})
    old_f = _make_file(tmp_path / "logs" / "a" / "old.txt", age_days=30)
    fresh_f = _make_file(tmp_path / "logs" / "a" / "fresh.txt", age_days=1)

    pols = sweep.load_policies(tmp_path / "config" / "log_retention.yaml")
    cands = sweep.scan_candidates(tmp_path, pols)
    paths = {c.path for c in cands}

    assert old_f in paths
    assert fresh_f not in paths


def test_scan_skips_undeclared_directory(tmp_path: Path) -> None:
    # Policy only covers logs/a, not logs/b.
    _write_config(tmp_path, {"logs/a": {"max_age_days": 10}})
    _make_file(tmp_path / "logs" / "b" / "stale.txt", age_days=9999)

    pols = sweep.load_policies(tmp_path / "config" / "log_retention.yaml")
    cands = sweep.scan_candidates(tmp_path, pols)
    assert cands == []


def test_dry_run_does_not_delete(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _write_config(tmp_path, {"logs/a": {"max_age_days": 5}})
    victim = _make_file(tmp_path / "logs" / "a" / "old.txt", age_days=100)

    rc = sweep.main(["--root", str(tmp_path)])
    assert rc == 0
    assert victim.exists(), "dry-run must not delete"
    out = capsys.readouterr().out
    assert "would be deleted" in out


def test_apply_deletes_expired_only(tmp_path: Path) -> None:
    _write_config(tmp_path, {"logs/a": {"max_age_days": 5}})
    old_f = _make_file(tmp_path / "logs" / "a" / "old.txt", age_days=100)
    fresh_f = _make_file(tmp_path / "logs" / "a" / "fresh.txt", age_days=1)

    rc = sweep.main(["--root", str(tmp_path), "--apply"])
    assert rc == 0
    assert not old_f.exists(), "expired file must be deleted"
    assert fresh_f.exists(), "fresh file must remain"


def test_apply_preserves_directories(tmp_path: Path) -> None:
    _write_config(tmp_path, {"logs/a": {"max_age_days": 5}})
    subdir = tmp_path / "logs" / "a" / "sub"
    victim = _make_file(subdir / "old.txt", age_days=100)

    sweep.main(["--root", str(tmp_path), "--apply"])
    assert not victim.exists()
    assert subdir.exists(), "directory must be preserved"
