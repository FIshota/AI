#!/usr/bin/env python3
"""
Memory forgetting sweep.

Walk the memory DB, compute Ebbinghaus retention for every non-protected
entry, and report/act on those below threshold.

Usage:
    python scripts/sweep_memory_forgetting.py              # dry-run (default)
    python scripts/sweep_memory_forgetting.py --apply      # actually compress
    python scripts/sweep_memory_forgetting.py --threshold 0.15

Safety:
    - Pinned (is_protected=1 または is_core=1) な行は常に保持.
    - --apply 時は memory_type を 'long' に降格し tags に 'forgotten_sweep' を追加
      (破壊的削除はせず, 既存 compressor の思想に合わせる).
    - すべての判定結果を audit_chain に追記.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audit_chain import append_entry  # noqa: E402
from core.memory_forgetting import (  # noqa: E402
    ForgettingCurveParams,
    ForgettingPolicy,
    MemoryEntry,
)

logger = logging.getLogger("memory_forgetting_sweep")


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def load_entries(db_path: Path) -> List[MemoryEntry]:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """SELECT id, created_at, accessed_at, access_count,
                      COALESCE(is_protected, 0), COALESCE(is_core, 0), memory_type
               FROM memories"""
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    entries: List[MemoryEntry] = []
    for row in rows:
        rid, created_at, accessed_at, access_count, is_protected, is_core, mtype = row
        created = _parse_dt(created_at) or datetime.now()
        rehearsed = _parse_dt(accessed_at)
        entries.append(
            MemoryEntry(
                id=rid,
                created_at=created,
                last_rehearsed_at=rehearsed,
                rehearsal_count=int(access_count or 0),
                pinned=bool(is_protected) or bool(is_core),
                content={"memory_type": mtype},
            )
        )
    return entries


def demote_entries(db_path: Path, ids: List[int]) -> int:
    if not ids:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" * len(ids))
        # nosec B608: placeholders は純粋なプレースホルダ文字列.
        conn.execute(
            f"UPDATE memories SET memory_type='long' "  # nosec B608
            f"WHERE id IN ({placeholders}) AND is_protected=0 AND COALESCE(is_core,0)=0",
            ids,
        )
        conn.commit()
    finally:
        conn.close()
    return len(ids)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("AI_CHAN_MEMORY_DB", "data/memory.db"),
        help="Path to memory sqlite DB.",
    )
    parser.add_argument("--threshold", type=float, default=0.2)
    parser.add_argument("--half-life-days", type=float, default=7.0)
    parser.add_argument("--initial-strength", type=float, default=1.0)
    parser.add_argument("--rehearsal-boost", type=float, default=0.5)
    parser.add_argument("--apply", action="store_true",
                        help="If set, actually demote forgotten entries.")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Default. No-op if --apply is also set.")
    parser.add_argument(
        "--audit-dir",
        default=os.environ.get("AI_CHAN_AUDIT_DIR", "logs/audit_chain"),
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        logger.error("DB not found: %s", db_path)
        return 2

    params = ForgettingCurveParams(
        initial_strength=args.initial_strength,
        half_life_days=args.half_life_days,
        rehearsal_boost=args.rehearsal_boost,
    )
    policy = ForgettingPolicy(threshold=args.threshold, params=params)

    entries = load_entries(db_path)
    now = datetime.now()
    kept, forgotten = policy.apply(entries, now=now)

    logger.info("total=%d kept=%d forgotten=%d pinned=%d",
                len(entries), len(kept), len(forgotten),
                sum(1 for e in entries if e.pinned))

    applied = False
    if args.apply and forgotten:
        ids = [int(e.id) for e in forgotten]
        demote_entries(db_path, ids)
        applied = True
        logger.info("demoted %d entries to long-term.", len(ids))
    else:
        logger.info("dry-run: no DB changes.")

    audit_dir = Path(args.audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    try:
        append_entry(audit_dir, {
            "event": "memory_forgetting_sweep",
            "db": str(db_path),
            "threshold": args.threshold,
            "total": len(entries),
            "kept": len(kept),
            "forgotten": len(forgotten),
            "applied": applied,
            "forgotten_ids": [int(e.id) for e in forgotten][:200],
            "params": {
                "initial_strength": params.initial_strength,
                "half_life_days": params.half_life_days,
                "rehearsal_boost": params.rehearsal_boost,
            },
        })
    except Exception as exc:
        logger.warning("audit append failed: %s", exc)

    # stdout summary (machine-friendly)
    print(json.dumps({
        "total": len(entries),
        "kept": len(kept),
        "forgotten": len(forgotten),
        "applied": applied,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
