#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_brand_misuse.py — ブランド/商標名の利用箇所をスキャンする情報目的ツール.

対象ブランド: HinoMoto / Ai / YAMATO / KAGUYA / ai-chan

ポリシー:
- `docs/`, `tests/`, `config/`, `configs/` 以下での利用は許容 (文書・設定・テスト)
- それ以外のディレクトリ (core/, scripts/, ui/, utils/ 等) での「商標的」利用を warn

本スクリプトは **情報目的** であり、常に exit 0 で終了します。
CI を落とさないため。

Python 3.9 stdlib のみ使用。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple

# ------------------------------------------------------------------
# 定数
# ------------------------------------------------------------------

# 単語境界 (英字/日本語) を考慮。"Ai" は誤検出しやすいため単語境界厳格に。
BRAND_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("HinoMoto", re.compile(r"\bHinoMoto\b")),
    ("YAMATO", re.compile(r"\bYAMATO\b")),
    ("KAGUYA", re.compile(r"\bKAGUYA\b")),
    ("ai-chan", re.compile(r"\bai-chan\b")),
    # "Ai" は単独語としてのみ (大文字小文字厳密)。"AI", "ai" などは除外。
    ("Ai", re.compile(r"(?<![A-Za-z_])Ai(?![A-Za-z_])")),
)

# 許容ディレクトリ (このディレクトリ配下はスキップ対象外 — ただし warn 抑制)
ALLOWED_DIR_NAMES: Tuple[str, ...] = ("docs", "tests", "config", "configs")

# 走査対象拡張子
SCAN_SUFFIXES: Tuple[str, ...] = (
    ".py", ".md", ".txt", ".rst", ".yml", ".yaml", ".json", ".toml",
    ".cfg", ".ini", ".sh",
)

# 除外ディレクトリ
EXCLUDE_DIR_NAMES: Tuple[str, ...] = (
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", "backups", "artifacts",
    "output", "logs", "reports", "models",
)


@dataclass(frozen=True)
class Hit:
    path: str
    lineno: int
    brand: str
    line: str
    in_allowed: bool


@dataclass
class ScanResult:
    hits: List[Hit] = field(default_factory=list)

    @property
    def warnings(self) -> List[Hit]:
        return [h for h in self.hits if not h.in_allowed]

    @property
    def informational(self) -> List[Hit]:
        return [h for h in self.hits if h.in_allowed]


# ------------------------------------------------------------------
# コアロジック
# ------------------------------------------------------------------

def is_path_in_allowed(rel_path: str) -> bool:
    """rel_path (root からの相対) が許容ディレクトリ配下か."""
    parts = rel_path.replace(os.sep, "/").split("/")
    return any(p in ALLOWED_DIR_NAMES for p in parts[:-1])


def scan_text(text: str) -> List[Tuple[int, str, str]]:
    """テキストからヒットを抽出. 返り値: [(lineno, brand, line), ...]"""
    results: List[Tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for brand, pat in BRAND_PATTERNS:
            if pat.search(line):
                results.append((lineno, brand, line.rstrip()))
    return results


def iter_target_files(root: str) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        # 除外ディレクトリを削る (in-place で os.walk を制御)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(SCAN_SUFFIXES):
                yield os.path.join(dirpath, fn)


def scan_repository(root: str) -> ScanResult:
    result = ScanResult()
    root = os.path.abspath(root)
    for abs_path in iter_target_files(root):
        rel = os.path.relpath(abs_path, root)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        hits = scan_text(text)
        if not hits:
            continue
        in_allowed = is_path_in_allowed(rel)
        for lineno, brand, line in hits:
            result.hits.append(
                Hit(path=rel, lineno=lineno, brand=brand, line=line, in_allowed=in_allowed)
            )
    return result


# ------------------------------------------------------------------
# レポート出力
# ------------------------------------------------------------------

def format_report(result: ScanResult) -> str:
    lines: List[str] = []
    lines.append("=== Brand Misuse Scan (informational) ===")
    lines.append(f"total hits      : {len(result.hits)}")
    lines.append(f"warnings        : {len(result.warnings)} (outside docs/tests/config)")
    lines.append(f"informational   : {len(result.informational)} (inside allowed dirs)")
    lines.append("")
    if result.warnings:
        lines.append("-- WARNINGS --")
        for h in result.warnings:
            lines.append(f"  [WARN] {h.path}:{h.lineno} [{h.brand}] {h.line[:100]}")
    else:
        lines.append("(no warnings)")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan repository for trademark brand name usage.")
    parser.add_argument("--root", default=".", help="repository root to scan")
    parser.add_argument("--quiet", action="store_true", help="print only warnings summary")
    args = parser.parse_args(argv)

    result = scan_repository(args.root)
    if not args.quiet:
        print(format_report(result))
    else:
        print(f"warnings={len(result.warnings)} total={len(result.hits)}")
    # 情報目的のため常に 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
