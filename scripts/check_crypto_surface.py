#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_crypto_surface.py

暗号・セキュリティ関連モジュールの import 箇所を棚卸しし、
輸出管理 (export control) レビュー用のサーフェスレポートを生成する。

Disclaimer:
    本スクリプトが生成するレポートは**運用上の棚卸し補助**であり、
    法的な該非判定 (export classification) の根拠にはならない可能性がある。
    判定は必ず法務・輸出管理専門家へ。

Usage:
    python3 scripts/check_crypto_surface.py [--root PATH] [--output PATH]

Python 3.9 stdlib のみを使用。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# 監視対象モジュール (大文字小文字を区別)。
# 日米欧いずれかの輸出管理で議論対象となる「可能性」のあるもの。
CRYPTO_MODULES: Tuple[str, ...] = (
    "cryptography",
    "hashlib",
    "secrets",
    "hmac",
    "ssl",
    "base64",  # 単独では暗号ではないが暗号鍵搬送で頻出
    "Crypto",  # pycryptodome
    "nacl",    # PyNaCl
)

# import 行を捕捉する正規表現。
# 例: `import hashlib`, `from hmac import compare_digest`, `from cryptography.hazmat ...`
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?P<from_mod>[A-Za-z_][\w\.]*)\s+import\s+.+|import\s+(?P<imp_mod>[A-Za-z_][\w\.]*(?:\s*,\s*[A-Za-z_][\w\.]*)*))"
)

DEFAULT_EXCLUDE_DIRS: Tuple[str, ...] = (
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    "backups",
)


@dataclass(frozen=True)
class Finding:
    """一件の import 検出結果 (immutable)."""
    path: str
    line_no: int
    module: str
    raw_line: str


@dataclass
class ScanResult:
    """スキャン結果のコンテナ."""
    root: str
    scanned_files: int = 0
    findings: List[Finding] = field(default_factory=list)

    def by_module(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.module] = counts.get(f.module, 0) + 1
        return counts


def iter_python_files(root: Path, exclude_dirs: Iterable[str] = DEFAULT_EXCLUDE_DIRS) -> Iterable[Path]:
    """root 配下の .py ファイルをイテレートする (excluded を除外)."""
    excluded = set(exclude_dirs)
    for dirpath, dirnames, filenames in os.walk(root):
        # in-place ではなく新しいリストで更新 (os.walk の仕様上 dirnames は in-place が要求される)
        dirnames[:] = [d for d in dirnames if d not in excluded and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def _extract_top_modules(match: re.Match) -> List[str]:
    """正規表現マッチから top-level module 名を抽出する."""
    mods: List[str] = []
    from_mod = match.group("from_mod")
    imp_mod = match.group("imp_mod")
    if from_mod:
        mods.append(from_mod.split(".")[0])
    if imp_mod:
        for part in imp_mod.split(","):
            part = part.strip().split(" as ")[0].strip()
            if part:
                mods.append(part.split(".")[0])
    return mods


def scan_file(path: Path, targets: Iterable[str] = CRYPTO_MODULES) -> List[Finding]:
    """単一ファイルをスキャンして Finding のリストを返す (副作用なし)."""
    target_set = set(targets)
    findings: List[Finding] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, start=1):
                m = _IMPORT_RE.match(line)
                if not m:
                    continue
                for mod in _extract_top_modules(m):
                    if mod in target_set:
                        findings.append(
                            Finding(
                                path=str(path),
                                line_no=line_no,
                                module=mod,
                                raw_line=line.rstrip("\n"),
                            )
                        )
    except OSError:
        # 読み取り不能ファイルは黙って無視せず、stderr に残す
        print(f"[warn] cannot read: {path}", file=sys.stderr)
    return findings


def scan_tree(root: Path, targets: Iterable[str] = CRYPTO_MODULES) -> ScanResult:
    """root 配下を走査して ScanResult を返す."""
    result = ScanResult(root=str(root))
    for py in iter_python_files(root):
        result.scanned_files += 1
        result.findings.extend(scan_file(py, targets))
    return result


def render_report(result: ScanResult) -> str:
    """人間可読な text レポートを生成する (純関数)."""
    lines: List[str] = []
    lines.append("Ai-chan Crypto/Security Surface Report")
    lines.append("=" * 60)
    lines.append(f"generated_at : {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"scan_root    : {result.root}")
    lines.append(f"scanned_files: {result.scanned_files}")
    lines.append(f"findings     : {len(result.findings)}")
    lines.append("")
    lines.append("Disclaimer:")
    lines.append("  This report is an operational inventory aid, not a legal")
    lines.append("  export-classification determination. Consult qualified")
    lines.append("  counsel for any actual export decision.")
    lines.append("")
    lines.append("Counts by module:")
    counts = result.by_module()
    if not counts:
        lines.append("  (none)")
    else:
        for mod in sorted(counts.keys()):
            lines.append(f"  {mod:<16} {counts[mod]}")
    lines.append("")
    lines.append("Findings:")
    if not result.findings:
        lines.append("  (none)")
    else:
        for f in sorted(result.findings, key=lambda x: (x.module, x.path, x.line_no)):
            lines.append(f"  [{f.module}] {f.path}:{f.line_no}: {f.raw_line.strip()}")
    lines.append("")
    return "\n".join(lines)


def write_report(result: ScanResult, output_path: Path) -> Path:
    """レポートを指定パスに書き出す (親ディレクトリは自動作成)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(result), encoding="utf-8")
    return output_path


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto/security import surface scanner")
    default_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help="Scan root directory (default: ai-chan project root)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_root / "docs" / "legal" / "crypto_surface_report.txt",
        help="Output report path",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = _parse_args(argv)
    root: Path = args.root
    if not root.is_dir():
        print(f"[error] root is not a directory: {root}", file=sys.stderr)
        return 2
    result = scan_tree(root)
    out = write_report(result, args.output)
    print(f"[ok] wrote report: {out}")
    print(f"     scanned_files={result.scanned_files}, findings={len(result.findings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
