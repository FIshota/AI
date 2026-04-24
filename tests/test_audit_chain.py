"""Tests for the tamper-evident audit log hash chain."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from core.audit_chain import (
    ENTRY_HASH_FIELD,
    PREV_HASH_FIELD,
    ZERO_HASH,
    append_entry,
    verify_chain,
)


def _append_with_gap(log_dir: Path, entry: dict) -> dict:
    """Append an entry and sleep briefly so filename timestamps differ."""
    written = append_entry(log_dir, entry)
    time.sleep(0.005)
    return written


@pytest.mark.unit
def test_empty_dir_verifies_true(tmp_path: Path) -> None:
    log_dir = tmp_path / "audit"
    log_dir.mkdir()
    is_valid, violations = verify_chain(log_dir)
    assert is_valid is True
    assert violations == []


@pytest.mark.unit
def test_single_entry_chains_correctly(tmp_path: Path) -> None:
    log_dir = tmp_path / "audit"
    written = append_entry(log_dir, {"event": "start", "detail": "first"})

    assert written[PREV_HASH_FIELD] == ZERO_HASH
    assert len(written[ENTRY_HASH_FIELD]) == 64

    is_valid, violations = verify_chain(log_dir)
    assert is_valid is True
    assert violations == []


@pytest.mark.unit
def test_three_entry_chain_valid(tmp_path: Path) -> None:
    log_dir = tmp_path / "audit"
    _append_with_gap(log_dir, {"event": "a"})
    _append_with_gap(log_dir, {"event": "b"})
    _append_with_gap(log_dir, {"event": "c"})

    is_valid, violations = verify_chain(log_dir)
    assert is_valid is True
    assert violations == []
    assert len(list(log_dir.glob("*.json"))) == 3


@pytest.mark.unit
def test_modified_middle_entry_detected(tmp_path: Path) -> None:
    log_dir = tmp_path / "audit"
    _append_with_gap(log_dir, {"event": "a"})
    _append_with_gap(log_dir, {"event": "b"})
    _append_with_gap(log_dir, {"event": "c"})

    files = sorted(log_dir.glob("*.json"))
    middle = files[1]
    data = json.loads(middle.read_text(encoding="utf-8"))
    data["event"] = "tampered"
    # Re-write preserving the original entry_hash so tampering is exposed.
    middle.write_text(json.dumps(data), encoding="utf-8")

    is_valid, violations = verify_chain(log_dir)
    assert is_valid is False
    assert violations
    joined = "\n".join(violations)
    assert "entry_hash mismatch" in joined or "prev_hash mismatch" in joined


@pytest.mark.unit
def test_deleted_middle_entry_detected(tmp_path: Path) -> None:
    log_dir = tmp_path / "audit"
    _append_with_gap(log_dir, {"event": "a"})
    _append_with_gap(log_dir, {"event": "b"})
    _append_with_gap(log_dir, {"event": "c"})

    files = sorted(log_dir.glob("*.json"))
    files[1].unlink()

    is_valid, violations = verify_chain(log_dir)
    assert is_valid is False
    # The third entry's prev_hash now references the deleted entry, not the first.
    assert any("prev_hash mismatch" in v for v in violations)


@pytest.mark.unit
def test_reordered_entries_detected(tmp_path: Path) -> None:
    log_dir = tmp_path / "audit"
    _append_with_gap(log_dir, {"event": "a"})
    _append_with_gap(log_dir, {"event": "b"})
    _append_with_gap(log_dir, {"event": "c"})

    files = sorted(log_dir.glob("*.json"))
    # Swap contents of first and second files — same filenames, wrong order.
    content0 = files[0].read_text(encoding="utf-8")
    content1 = files[1].read_text(encoding="utf-8")
    files[0].write_text(content1, encoding="utf-8")
    files[1].write_text(content0, encoding="utf-8")

    is_valid, violations = verify_chain(log_dir)
    assert is_valid is False
    assert any("prev_hash mismatch" in v for v in violations)
