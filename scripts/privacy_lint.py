#!/usr/bin/env python3
"""Privacy policy linter.

Validates ``docs/PRIVACY.md``:

1. Required section headings exist.
2. Known data-producing modules under ``core/`` are mentioned (or
   allow-listed) so new persistence modules force a PRIVACY.md update.

Usage::

    python scripts/privacy_lint.py [--root <repo>] [--privacy <path>]

Exit codes:

- 0: ok
- 1: missing headings or undeclared data categories
- 2: PRIVACY.md not found
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Iterable, List, Sequence, Tuple

REQUIRED_HEADINGS: Tuple[str, ...] = (
    "3 行まとめ",
    "データカテゴリ一覧",
    "Kill-Switch",
    "外部通信",
    "未成年",
    "更新履歴",
)

# core/ modules that persist user data. If a module is added here but not
# mentioned in PRIVACY.md (or in ALLOWLIST), the lint fails.
KNOWN_DATA_MODULES: Tuple[Tuple[str, Sequence[str]], ...] = (
    ("clipboard_watcher", ("クリップボード", "clipboard")),
    ("screenshot_reader", ("スクリーンショット", "screenshot")),
    ("diary", ("日記", "diary")),
    ("calendar_reader", ("カレンダー", "calendar")),
    ("voice_id", ("声紋", "voice id", "voice_id")),
    ("emotion", ("感情",)),
    ("audit_log", ("監査",)),
)

ALLOWLIST_UNDECLARED: Tuple[str, ...] = ()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def check_required_headings(text: str, required: Iterable[str] = REQUIRED_HEADINGS) -> List[str]:
    """Return list of missing heading fragments."""
    missing: List[str] = []
    for frag in required:
        pattern = re.compile(r"^#{1,6}\s.*" + re.escape(frag), re.MULTILINE)
        if not pattern.search(text):
            missing.append(frag)
    return missing


def detect_core_modules(core_dir: str) -> List[str]:
    if not os.path.isdir(core_dir):
        return []
    names: List[str] = []
    for entry in sorted(os.listdir(core_dir)):
        if not entry.endswith(".py"):
            continue
        stem = entry[:-3]
        for mod, _ in KNOWN_DATA_MODULES:
            if stem == mod or stem.startswith(mod):
                names.append(mod)
                break
    return sorted(set(names))


def check_modules_mentioned(text: str, modules: Iterable[str]) -> List[str]:
    lower = text.lower()
    undeclared: List[str] = []
    for mod in modules:
        if mod in ALLOWLIST_UNDECLARED:
            continue
        keywords = dict(KNOWN_DATA_MODULES).get(mod, (mod,))
        if not any(kw.lower() in lower for kw in keywords):
            undeclared.append(mod)
    return undeclared


def run_lint(privacy_path: str, core_dir: str) -> Tuple[int, List[str]]:
    messages: List[str] = []
    if not os.path.isfile(privacy_path):
        return 2, [f"PRIVACY.md not found: {privacy_path}"]

    text = read_text(privacy_path)

    missing = check_required_headings(text)
    if missing:
        messages.append("Missing headings: " + ", ".join(missing))

    detected = detect_core_modules(core_dir)
    undeclared = check_modules_mentioned(text, detected)
    if undeclared:
        messages.append("Undeclared data modules: " + ", ".join(undeclared))

    return (1 if messages else 0), messages


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint PRIVACY.md")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--privacy", default=None, help="Path to PRIVACY.md")
    parser.add_argument("--core", default=None, help="Path to core/ directory")
    args = parser.parse_args(argv)

    privacy = args.privacy or os.path.join(args.root, "docs", "PRIVACY.md")
    core_dir = args.core or os.path.join(args.root, "core")

    code, messages = run_lint(privacy, core_dir)
    for msg in messages:
        print(msg)
    if code == 0:
        print("privacy_lint: OK")
    return code


if __name__ == "__main__":
    sys.exit(main())
