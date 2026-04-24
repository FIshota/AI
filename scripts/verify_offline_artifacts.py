#!/usr/bin/env python3
"""Offline artifact integrity verifier.

Verifies files against a JSON manifest of the form:
    [{"path": "relative/or/abs", "sha256": "...", "size_bytes": 123}, ...]

No network access. stdlib only. Python 3.9 compatible.

Exit codes:
    0 - all entries verified
    2 - one or more entries missing / tampered / size mismatch
    1 - usage / manifest parsing error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

CHUNK_SIZE = 64 * 1024  # 64 KB

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_SIZE_MISMATCH = "size_mismatch"
STATUS_HASH_MISMATCH = "hash_mismatch"
STATUS_UNREADABLE = "unreadable"


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class EntryResult:
    entry: ManifestEntry
    status: str
    actual_sha256: Optional[str] = None
    actual_size: Optional[int] = None
    detail: str = ""


@dataclass(frozen=True)
class VerifyReport:
    results: Tuple[EntryResult, ...]

    @property
    def ok(self) -> bool:
        return all(r.status == STATUS_OK for r in self.results)

    def by_status(self, status: str) -> Tuple[EntryResult, ...]:
        return tuple(r for r in self.results if r.status == status)


def sha256_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk_size)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def load_manifest(manifest_path: Path) -> Tuple[ManifestEntry, ...]:
    with manifest_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError("Manifest root must be a JSON list")
    entries: List[ManifestEntry] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest entry #{i} must be a JSON object")
        try:
            path = str(item["path"])
            sha = str(item["sha256"]).lower()
            size = int(item["size_bytes"])
        except KeyError as e:
            raise ValueError(f"Manifest entry #{i} missing field {e}") from e
        if size < 0:
            raise ValueError(f"Manifest entry #{i} has negative size")
        entries.append(ManifestEntry(path=path, sha256=sha, size_bytes=size))
    return tuple(entries)


def resolve_entry_path(entry: ManifestEntry, base_dir: Path) -> Path:
    p = Path(entry.path)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def verify_entry(entry: ManifestEntry, base_dir: Path) -> EntryResult:
    target = resolve_entry_path(entry, base_dir)
    if not target.exists() or not target.is_file():
        return EntryResult(entry=entry, status=STATUS_MISSING,
                           detail=f"not found: {target}")
    try:
        actual_size = target.stat().st_size
    except OSError as e:
        return EntryResult(entry=entry, status=STATUS_UNREADABLE,
                           detail=f"stat failed: {e}")
    if actual_size != entry.size_bytes:
        return EntryResult(entry=entry, status=STATUS_SIZE_MISMATCH,
                           actual_size=actual_size,
                           detail=f"expected {entry.size_bytes}, got {actual_size}")
    try:
        actual_sha = sha256_file(target)
    except OSError as e:
        return EntryResult(entry=entry, status=STATUS_UNREADABLE,
                           actual_size=actual_size,
                           detail=f"read failed: {e}")
    if actual_sha.lower() != entry.sha256.lower():
        return EntryResult(entry=entry, status=STATUS_HASH_MISMATCH,
                           actual_sha256=actual_sha, actual_size=actual_size,
                           detail="sha256 differs")
    return EntryResult(entry=entry, status=STATUS_OK,
                       actual_sha256=actual_sha, actual_size=actual_size)


def verify_manifest(entries: Iterable[ManifestEntry], base_dir: Path) -> VerifyReport:
    results = tuple(verify_entry(e, base_dir) for e in entries)
    return VerifyReport(results=results)


def format_report(report: VerifyReport) -> str:
    lines: List[str] = []
    total = len(report.results)
    ok = len(report.by_status(STATUS_OK))
    lines.append(f"verified {ok}/{total} entries")
    for status in (STATUS_MISSING, STATUS_SIZE_MISMATCH, STATUS_HASH_MISMATCH, STATUS_UNREADABLE):
        bucket = report.by_status(status)
        if not bucket:
            continue
        lines.append(f"[{status}] ({len(bucket)}):")
        for r in bucket:
            lines.append(f"  - {r.entry.path}: {r.detail}")
    if report.ok:
        lines.append("RESULT: OK")
    else:
        lines.append("RESULT: FAIL")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline artifact verifier (stdlib only)")
    p.add_argument("--manifest", required=True, type=Path,
                   help="Path to manifest JSON")
    p.add_argument("--base-dir", type=Path, default=None,
                   help="Base directory for resolving relative paths (default: manifest's parent)")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON report instead of human-readable text")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    manifest_path: Path = args.manifest
    if not manifest_path.is_file():
        print(f"manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    try:
        entries = load_manifest(manifest_path)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"invalid manifest: {e}", file=sys.stderr)
        return 1
    base_dir: Path = (args.base_dir or manifest_path.parent).resolve()
    report = verify_manifest(entries, base_dir)
    if args.json:
        payload = {
            "ok": report.ok,
            "total": len(report.results),
            "results": [
                {
                    "path": r.entry.path,
                    "status": r.status,
                    "expected_sha256": r.entry.sha256,
                    "expected_size": r.entry.size_bytes,
                    "actual_sha256": r.actual_sha256,
                    "actual_size": r.actual_size,
                    "detail": r.detail,
                }
                for r in report.results
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
    return 0 if report.ok else 2


if __name__ == "__main__":
    sys.exit(main())
