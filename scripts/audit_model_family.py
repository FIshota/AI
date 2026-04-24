#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data-Truth-Audit (DTA) for MODEL_FAMILY.md.

ai-chan/docs/MODEL_FAMILY.md と hinomoto-model/docs/MODEL_FAMILY.md の
「モデル一覧表」を抽出し、同名モデルの属性が矛盾していないか照合する。

- Python 3.9 互換 / stdlib のみ
- hinomoto-model が存在しない環境でも crash せず warn 扱いで終了
- 矛盾あり → exit 2
- TBD 数をカウントしレポート

Usage:
    python scripts/audit_model_family.py
    python scripts/audit_model_family.py --ai-chan PATH --hinomoto PATH
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

EXPECTED_COLUMNS = [
    "モデル名",
    "公開範囲",
    "vocab",
    "d_model",
    "n_layers",
    "パラメータ数",
    "学習コーパス",
    "ライセンス",
    "想定ユーザ",
]

TBD_MARKER = "[TBD]"


def extract_model_table(md_path: Path) -> List[Dict[str, str]]:
    """Extract the model family data table from a Markdown file.

    検索基準: ヘッダ行に EXPECTED_COLUMNS の最初の 3 つ (モデル名 / 公開範囲 / vocab) が
    全て含まれる markdown table を 1 つ見つけて返す。

    Returns a list of row dicts (column name -> cell value).
    """
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find a header line that contains the required columns.
    header_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        if all(col in line for col in EXPECTED_COLUMNS[:3]):
            # Next line must be a separator row: |---|---|...
            if i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i + 1]):
                header_idx = i
                break

    if header_idx is None:
        return []

    header_cells = _split_md_row(lines[header_idx])
    rows: List[Dict[str, str]] = []
    for line in lines[header_idx + 2 :]:
        if not line.lstrip().startswith("|"):
            break
        if re.match(r"^\s*\|[\s\-:|]+\|\s*$", line):
            break
        cells = _split_md_row(line)
        if len(cells) < len(header_cells):
            # pad with empty
            cells = cells + [""] * (len(header_cells) - len(cells))
        row = {header_cells[j]: cells[j] for j in range(len(header_cells))}
        rows.append(row)
    return rows


def _split_md_row(line: str) -> List[str]:
    # Trim leading/trailing whitespace and pipes
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def compare_tables(
    a_rows: List[Dict[str, str]],
    b_rows: List[Dict[str, str]],
    a_label: str = "ai-chan",
    b_label: str = "hinomoto",
) -> List[str]:
    """Return list of conflict descriptions. Empty list means consistent."""
    conflicts: List[str] = []
    a_by_name = {r.get("モデル名", ""): r for r in a_rows if r.get("モデル名")}
    b_by_name = {r.get("モデル名", ""): r for r in b_rows if r.get("モデル名")}

    common = sorted(set(a_by_name) & set(b_by_name))
    only_a = sorted(set(a_by_name) - set(b_by_name))
    only_b = sorted(set(b_by_name) - set(a_by_name))

    for name in only_a:
        conflicts.append(f"[MISSING-IN-{b_label}] モデル '{name}' は {a_label} にのみ存在")
    for name in only_b:
        conflicts.append(f"[MISSING-IN-{a_label}] モデル '{name}' は {b_label} にのみ存在")

    for name in common:
        a_row = a_by_name[name]
        b_row = b_by_name[name]
        for col in EXPECTED_COLUMNS:
            a_val = a_row.get(col, "").strip()
            b_val = b_row.get(col, "").strip()
            # TBD on either side is considered "not yet determined" -> not a conflict
            if a_val == TBD_MARKER or b_val == TBD_MARKER:
                continue
            if a_val != b_val:
                conflicts.append(
                    f"[CONFLICT] '{name}' 列 '{col}': {a_label}='{a_val}' vs {b_label}='{b_val}'"
                )
    return conflicts


def count_tbd(rows: List[Dict[str, str]]) -> int:
    n = 0
    for r in rows:
        for v in r.values():
            if v.strip() == TBD_MARKER:
                n += 1
    return n


def default_paths() -> Tuple[Path, Path]:
    here = Path(__file__).resolve()
    ai_chan_root = here.parents[1]  # ai-chan/
    parent = ai_chan_root.parent
    a = ai_chan_root / "docs" / "MODEL_FAMILY.md"
    b = parent / "hinomoto-model" / "docs" / "MODEL_FAMILY.md"
    return a, b


def run_audit(a_path: Path, b_path: Path) -> int:
    print("=" * 60)
    print("MODEL_FAMILY DTA (Data-Truth-Audit)")
    print("=" * 60)
    if not a_path.exists():
        print(f"ERROR: ai-chan MODEL_FAMILY.md が見つかりません: {a_path}")
        return 2
    a_rows = extract_model_table(a_path)
    print(f"[ai-chan]   {a_path}  行数={len(a_rows)}  TBD={count_tbd(a_rows)}")

    if not b_path.exists():
        print(f"WARN: hinomoto-model MODEL_FAMILY.md が見つかりません: {b_path}")
        print("      → 単独モードで完了 (照合スキップ)")
        return 0

    b_rows = extract_model_table(b_path)
    print(f"[hinomoto]  {b_path}  行数={len(b_rows)}  TBD={count_tbd(b_rows)}")

    if not a_rows:
        print("ERROR: ai-chan 側に表が見つかりません")
        return 2
    if not b_rows:
        print("ERROR: hinomoto-model 側に表が見つかりません")
        return 2

    conflicts = compare_tables(a_rows, b_rows)
    print("-" * 60)
    if conflicts:
        print(f"矛盾 {len(conflicts)} 件:")
        for c in conflicts:
            print("  " + c)
        print("-" * 60)
        print("RESULT: FAIL")
        return 2

    print(f"矛盾なし (共通モデル {len(set(r.get('モデル名','') for r in a_rows) & set(r.get('モデル名','') for r in b_rows))} 件照合済み)")
    print("RESULT: OK")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    a_default, b_default = default_paths()
    ap = argparse.ArgumentParser(description="MODEL_FAMILY DTA")
    ap.add_argument("--ai-chan", type=Path, default=a_default)
    ap.add_argument("--hinomoto", type=Path, default=b_default)
    args = ap.parse_args(argv)
    return run_audit(args.ai_chan, args.hinomoto)


if __name__ == "__main__":
    sys.exit(main())
