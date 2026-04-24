#!/usr/bin/env python3
"""Corpus isolation guard (ADR 0002).

P4 / P5 個人コーパス (ai-chan/data/personal/, ai-chan/memory/) が
基盤モデル (hinomoto-model) の事前学習/SFT ビルドスクリプトに
参照されていないことを静的にチェックする。

ADR 0002 の物理的隔離を CI で強制するためのガード。
push / pull_request の両方で実行される。

Exit codes:
    0: clean
    2: corpus isolation violation (P4/P5 path referenced from base builder)

Usage:
    python3 scripts/check_corpus_isolation.py
    python3 scripts/check_corpus_isolation.py --repo-root /path/to/ai-chan \\
        --sibling-root /path/to/hinomoto-model
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("check_corpus_isolation")

# P4 / P5 に該当する「基盤モデルに流してはいけない」パス断片。
# ADR 0002 の隔離境界。
FORBIDDEN_IN_BASE_BUILDERS: tuple[str, ...] = (
    "ai-chan/data/personal",
    "ai-chan/memory",
    "data/personal",
)

# 基盤モデル側 (hinomoto-model) の事前学習/SFT/安定化ビルダ群。
# これらは P1-P3 のみを読むべきで、P4/P5 を参照してはならない。
BASE_BUILDER_GLOBS: tuple[str, ...] = (
    "scripts/build_pretrain_corpus.py",
    "scripts/build_dolly_splits.py",
    "scripts/build_stabilize_*.py",
)

# ai-chan リポ内の、P1-P5 のパスを絶対に横断してはいけないビルダ。
AICHAN_BASE_BUILDER_GLOBS: tuple[str, ...] = (
    "scripts/build_pretrain_corpus.py",
    "scripts/build_dolly_splits.py",
)

# 自分自身や、ガード/テスト/ドキュメントは検査から除外する
# (これらは P4/P5 の path 文字列を正当に含む)。
EXCLUDE_SUFFIXES: tuple[str, ...] = (
    "check_corpus_isolation.py",
    "test_corpus_isolation.py",
)
EXCLUDE_DIR_PARTS: tuple[str, ...] = (
    "docs",
    "tests",
    "__pycache__",
)


@dataclass(frozen=True)
class Violation:
    file: Path
    line_no: int
    line: str
    pattern: str


def _is_excluded(path: Path) -> bool:
    if path.name in EXCLUDE_SUFFIXES:
        return True
    return any(part in EXCLUDE_DIR_PARTS for part in path.parts)


def _scan_file(path: Path, patterns: tuple[str, ...]) -> list[Violation]:
    violations: list[Violation] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("cannot read %s: %s", path, exc)
        return violations
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            if pat in line:
                violations.append(
                    Violation(file=path, line_no=line_no, line=line.strip(), pattern=pat)
                )
                break
    return violations


def _iter_base_builders(root: Path, globs: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        logger.info("builder root does not exist, skipping: %s", root)
        return []
    builders: list[Path] = []
    for pattern in globs:
        for match in root.glob(pattern):
            if match.is_file() and not _is_excluded(match):
                builders.append(match)
    return builders


def check_isolation(repo_root: Path, sibling_root: Path | None) -> list[Violation]:
    """Run corpus isolation check against ai-chan repo and optional sibling hinomoto-model repo."""
    violations: list[Violation] = []

    aichan_builders = _iter_base_builders(repo_root, AICHAN_BASE_BUILDER_GLOBS)
    for builder in aichan_builders:
        violations.extend(_scan_file(builder, FORBIDDEN_IN_BASE_BUILDERS))

    if sibling_root is not None:
        sibling_builders = _iter_base_builders(sibling_root, BASE_BUILDER_GLOBS)
        for builder in sibling_builders:
            violations.extend(_scan_file(builder, FORBIDDEN_IN_BASE_BUILDERS))

    return violations


def check_cross_phase_leak(repo_root: Path) -> list[Violation]:
    """Minimal whitelist: P<N> corpus dirs should not import from other P<M> dirs.

    Scans ai-chan/data/personal/ and ai-chan/memory/ for hard-coded references to
    pretrain / sft / stabilize paths (reverse direction: P4/P5 data leaking
    hinomoto pretrain artifacts is also a smell).
    """
    reverse_patterns = ("data/pretrain", "data/sft", "data/stabilize")
    targets = [repo_root / "data" / "personal", repo_root / "memory"]
    violations: list[Violation] = []
    text_exts = re.compile(r"\.(py|yaml|yml|json|toml|md|txt)$", re.IGNORECASE)
    for target in targets:
        if not target.exists():
            continue
        for path in target.rglob("*"):
            if not path.is_file() or not text_exts.search(path.name):
                continue
            if _is_excluded(path):
                continue
            violations.extend(_scan_file(path, reverse_patterns))
    return violations


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="ai-chan repository root",
    )
    parser.add_argument(
        "--sibling-root",
        type=Path,
        default=None,
        help="hinomoto-model repository root (optional, auto-detected if sibling)",
    )
    return parser.parse_args(argv)


def _autodetect_sibling(repo_root: Path) -> Path | None:
    candidate = repo_root.parent / "hinomoto-model"
    return candidate if candidate.exists() else None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    repo_root: Path = args.repo_root.resolve()
    sibling_root: Path | None = args.sibling_root
    if sibling_root is None:
        sibling_root = _autodetect_sibling(repo_root)
    if sibling_root is not None:
        sibling_root = sibling_root.resolve()

    logger.info("repo_root=%s sibling_root=%s", repo_root, sibling_root)

    violations = check_isolation(repo_root, sibling_root)
    violations.extend(check_cross_phase_leak(repo_root))

    if not violations:
        print("corpus isolation: OK (ADR 0002)")
        return 0

    print("corpus isolation: VIOLATION (ADR 0002)")
    for v in violations:
        print(f"  {v.file}:{v.line_no}: pattern={v.pattern!r} :: {v.line}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
