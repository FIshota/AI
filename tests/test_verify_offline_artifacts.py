"""Tests for scripts/verify_offline_artifacts.py."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_offline_artifacts as voa  # noqa: E402
import generate_artifact_manifest as gam  # noqa: E402


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def _make_manifest(tmp_path: Path, files: dict) -> Path:
    entries = []
    for rel, data in files.items():
        _write(tmp_path / rel, data)
        entries.append({
            "path": rel,
            "sha256": _sha256_bytes(data),
            "size_bytes": len(data),
        })
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    return manifest


def test_all_match(tmp_path: Path) -> None:
    manifest = _make_manifest(tmp_path, {
        "a.bin": b"hello",
        "sub/b.txt": b"world!",
    })
    entries = voa.load_manifest(manifest)
    report = voa.verify_manifest(entries, tmp_path)
    assert report.ok
    assert len(report.results) == 2
    assert all(r.status == voa.STATUS_OK for r in report.results)


def test_missing_file(tmp_path: Path) -> None:
    manifest = _make_manifest(tmp_path, {"a.bin": b"hi"})
    (tmp_path / "a.bin").unlink()
    entries = voa.load_manifest(manifest)
    report = voa.verify_manifest(entries, tmp_path)
    assert not report.ok
    assert report.results[0].status == voa.STATUS_MISSING


def test_tampered_content(tmp_path: Path) -> None:
    manifest = _make_manifest(tmp_path, {"a.bin": b"hello"})
    # Rewrite with same length different content
    (tmp_path / "a.bin").write_bytes(b"HELLO")
    entries = voa.load_manifest(manifest)
    report = voa.verify_manifest(entries, tmp_path)
    assert not report.ok
    assert report.results[0].status == voa.STATUS_HASH_MISMATCH


def test_size_mismatch(tmp_path: Path) -> None:
    manifest = _make_manifest(tmp_path, {"a.bin": b"hello"})
    (tmp_path / "a.bin").write_bytes(b"hello_extra")
    entries = voa.load_manifest(manifest)
    report = voa.verify_manifest(entries, tmp_path)
    assert not report.ok
    assert report.results[0].status == voa.STATUS_SIZE_MISMATCH


def test_empty_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text("[]", encoding="utf-8")
    entries = voa.load_manifest(manifest)
    report = voa.verify_manifest(entries, tmp_path)
    assert report.ok
    assert len(report.results) == 0


def test_relative_path_resolution(tmp_path: Path) -> None:
    # Use subdirectory in relative path
    manifest = _make_manifest(tmp_path, {"dir1/dir2/x.dat": b"abc123"})
    entries = voa.load_manifest(manifest)
    assert entries[0].path == "dir1/dir2/x.dat"
    report = voa.verify_manifest(entries, tmp_path)
    assert report.ok


def test_chunked_hashing_large_file(tmp_path: Path) -> None:
    # File larger than single chunk to exercise streaming read
    data = b"x" * (voa.CHUNK_SIZE * 3 + 17)
    p = tmp_path / "big.bin"
    p.write_bytes(data)
    assert voa.sha256_file(p) == _sha256_bytes(data)


def test_invalid_manifest_not_list(tmp_path: Path) -> None:
    m = tmp_path / "m.json"
    m.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        voa.load_manifest(m)


def test_cli_exit_code_ok(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    manifest = _make_manifest(tmp_path, {"a.bin": b"ok"})
    rc = voa.main(["--manifest", str(manifest)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RESULT: OK" in out


def test_cli_exit_code_fail(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    manifest = _make_manifest(tmp_path, {"a.bin": b"ok"})
    (tmp_path / "a.bin").write_bytes(b"tampered!")
    rc = voa.main(["--manifest", str(manifest)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "RESULT: FAIL" in out


def test_generate_and_verify_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _write(root / "a.bin", b"alpha")
    _write(root / "nested/b.txt", b"beta")
    _write(root / "skip.log", b"no")

    opts = gam.GenOptions(
        root=root,
        include_globs=tuple(),
        exclude_globs=("*.log",),
    )
    entries = gam.generate(opts)
    assert {e["path"] for e in entries} == {"a.bin", "nested/b.txt"}

    manifest = tmp_path / "M.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")

    loaded = voa.load_manifest(manifest)
    report = voa.verify_manifest(loaded, root)
    assert report.ok
