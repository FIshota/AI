#!/usr/bin/env python3
"""TAXONOMY 整合性チェック (docs/TAXONOMY.md §8 準拠).

禁止表記が残っていないか機械的に grep する。
CI / pre-commit から呼び出す想定。

Exit codes:
    0: clean
    1: violations found

Usage:
    python3 scripts/check_taxonomy.py [--paths docs/ core/ ...]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── 禁止表記ルール ──
# (pattern, description, severity)
# severity: "error" は exit 1、"warn" は報告のみ
# RULES 形式: (pattern, description, severity, [allowed_exts])
# allowed_exts を指定するとそれ以外の拡張子でのみチェック（除外）
RULES: list[tuple[re.Pattern[str], str, str, tuple[str, ...]]] = [
    # §1 名称
    (re.compile(r"\bAi-chan\b"), "use 'ai-chan' (lowercase). Ai-chan is forbidden.", "error", ()),
    (re.compile(r"\bAI-chan\b"), "use 'ai-chan' (lowercase). AI-chan is forbidden.", "error", ()),
    # AiChan は Python クラス名として例外許可（TAXONOMY §1）。docs/diagram も
    # クラス参照で使うので error 扱いしない（warn のみで存在を可視化）。
    (re.compile(r"\bAiChan\b"), "code identifier 'AiChan' — keep only for Python class references.",
     "warn", ()),
    (re.compile(r"\bAi_chan\b"), "use 'ai-chan'. Ai_chan is forbidden.", "error", ()),
    # §5 TTS
    (re.compile(r"γTTS|γ切替"), "use 'Switchable TTS' (gamma symbol is forbidden).", "error", ()),
    # §3 Phase 番号体系
    # 単独 "Phase N" は IP-/PP- で修飾すること。許容例外: "Phase 0.5", "Phase 0.75" は IP の短縮、
    # "Phase 1 batch" / "Phase 1 完了" のような過去ログは warn のみ
    (
        re.compile(r"(?<![IP]P-)\bPhase\s+\d"),
        "use IP-N or PP-N prefix instead of bare 'Phase N'. See TAXONOMY.md §3.",
        "warn",
        (),
    ),
]

# 除外 glob パターン
EXCLUDE_PATTERNS = (
    "**/.git/**",
    "**/__pycache__/**",
    "**/node_modules/**",
    "**/venv/**",
    "**/.venv/**",
    "**/bench/data_cache/**",
    "**/bench/results/**",
    "**/logs/**",
    "**/models/**",
    "**/*.lock",
    "**/*.gguf",
    # TAXONOMY 自体 / 本スクリプト / マインドマップは禁止表記を説明・引用するので除外
    "**/docs/TAXONOMY.md",
    "**/scripts/check_taxonomy.py",
    "**/docs/yamato-mindmap.html",
    # 履歴/過渡期ドキュメント: 過去の "Phase N" を言及するため warn を素通し
    "**/docs/expansion-plan.md",
    "**/docs/update-plans-100.md",
    "**/docs/roadmap-*.md",
)

DEFAULT_PATHS = ("docs", "core", "ui", "utils", "bench", "scripts", "README.md")
INCLUDE_EXT = {".md", ".py", ".html", ".txt", ".yml", ".yaml", ".json", ".toml"}


def _is_excluded(path: Path) -> bool:
    s = str(path)
    return any(path.match(pat) or pat.replace("**/", "") in s for pat in EXCLUDE_PATTERNS)


def _iter_files(roots: list[Path]):
    for root in roots:
        if root.is_file():
            if not _is_excluded(root):
                yield root
            continue
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in INCLUDE_EXT:
                continue
            if _is_excluded(p):
                continue
            yield p


def check_file(path: Path) -> list[tuple[int, str, str, str]]:
    """Return list of (lineno, matched_text, description, severity)."""
    findings: list[tuple[int, str, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings
    for i, line in enumerate(text.splitlines(), 1):
        for pattern, desc, severity, exempt_exts in RULES:
            if exempt_exts and path.suffix in exempt_exts:
                continue
            for m in pattern.finditer(line):
                findings.append((i, m.group(0), desc, severity))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Taxonomy integrity check.")
    parser.add_argument(
        "--paths", nargs="*", default=list(DEFAULT_PATHS),
        help="Paths (files or directories) to scan.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat 'warn' severity as error.",
    )
    args = parser.parse_args()

    roots = [Path(p) for p in args.paths]
    errors = 0
    warnings = 0

    for f in _iter_files(roots):
        findings = check_file(f)
        if not findings:
            continue
        for lineno, text, desc, severity in findings:
            if severity == "error" or (args.strict and severity == "warn"):
                errors += 1
                marker = "✖"
            else:
                warnings += 1
                marker = "⚠"
            print(f"{marker} {f}:{lineno}: '{text}' — {desc}")

    print()
    print(f"taxonomy check: {errors} errors, {warnings} warnings")
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
