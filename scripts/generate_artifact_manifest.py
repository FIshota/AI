#!/usr/bin/env python3
"""Generate an artifact manifest for offline verification.

Walks a directory recursively and emits a JSON list of:
    {"path": <relative-to-root>, "sha256": <hex>, "size_bytes": <int>}

Only stdlib. Python 3.9 compatible.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# Reuse sha256 streaming from verify script
try:
    from verify_offline_artifacts import sha256_file, CHUNK_SIZE  # type: ignore
except ImportError:  # allow running from repo root
    import hashlib

    CHUNK_SIZE = 64 * 1024

    def sha256_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:  # type: ignore
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                buf = f.read(chunk_size)
                if not buf:
                    break
                h.update(buf)
        return h.hexdigest()


@dataclass(frozen=True)
class GenOptions:
    root: Path
    include_globs: Tuple[str, ...]
    exclude_globs: Tuple[str, ...]
    follow_symlinks: bool = False


def _match_any(rel: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def iter_files(opts: GenOptions):
    root = opts.root.resolve()
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        if not opts.follow_symlinks and p.is_symlink():
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if opts.include_globs and not _match_any(rel, opts.include_globs):
            continue
        if opts.exclude_globs and _match_any(rel, opts.exclude_globs):
            continue
        yield p, rel


def generate(opts: GenOptions) -> list:
    entries = []
    for abs_path, rel in iter_files(opts):
        entries.append({
            "path": rel,
            "sha256": sha256_file(abs_path),
            "size_bytes": abs_path.stat().st_size,
        })
    return entries


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate artifact manifest (stdlib only)")
    p.add_argument("--root", required=True, type=Path, help="Directory to walk")
    p.add_argument("--output", type=Path, default=None,
                   help="Output JSON path (default: stdout)")
    p.add_argument("--include-glob", action="append", default=[],
                   help="Only include files matching this glob (may repeat)")
    p.add_argument("--exclude-glob", action="append", default=[],
                   help="Exclude files matching this glob (may repeat)")
    p.add_argument("--follow-symlinks", action="store_true",
                   help="Follow symlinks during walk")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root
    if not root.is_dir():
        print(f"root is not a directory: {root}", file=sys.stderr)
        return 1
    opts = GenOptions(
        root=root,
        include_globs=tuple(args.include_glob),
        exclude_globs=tuple(args.exclude_glob),
        follow_symlinks=args.follow_symlinks,
    )
    entries = generate(opts)
    payload = json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
