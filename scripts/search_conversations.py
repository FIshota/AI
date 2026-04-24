#!/usr/bin/env python3
"""CLI for the conversation history search (Sprint 5.7).

Example:
    python scripts/search_conversations.py \\
        --db memory/search_index.db \\
        --from 2027-03-01 --to 2027-03-31 \\
        --keyword "ペット" --speaker papa --limit 20
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

# Allow running this script directly from the repo root.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.conversation_search import (  # noqa: E402
    ConversationSearchIndex,
    SearchHit,
    SearchQuery,
)


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def _format_hit(hit: SearchHit) -> str:
    lines: List[str] = []
    lines.append(
        f"── {hit.timestamp.isoformat()}  [{hit.speaker}]  "
        f"score={hit.score:.3f}  id={hit.turn_id}"
    )
    for c in hit.context_before:
        lines.append(f"    … {c}")
    lines.append(f"  » {hit.text}")
    for c in hit.context_after:
        lines.append(f"    … {c}")
    return "\n".join(lines)


def _hit_to_dict(hit: SearchHit) -> dict:
    return {
        "turn_id": hit.turn_id,
        "timestamp": hit.timestamp.isoformat(),
        "speaker": hit.speaker,
        "text": hit.text,
        "score": hit.score,
        "context_before": list(hit.context_before),
        "context_after": list(hit.context_after),
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Search ai-chan conversation history")
    p.add_argument("--db", default="memory/search_index.db",
                   help="Path to the search index DB (default: memory/search_index.db)")
    p.add_argument("--keyword", "-k", action="append", default=[],
                   help="Keyword (repeatable)")
    p.add_argument("--from", dest="date_from", default=None, help="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD")
    p.add_argument("--speaker", default=None, help="Filter by speaker")
    p.add_argument("--mode", choices=("AND", "OR"), default="AND")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--reindex-from", default=None,
                   help="Rebuild index from an existing memory DB path")
    args = p.parse_args(argv)

    db_path = Path(args.db)
    idx = ConversationSearchIndex(db_path)

    if args.reindex_from:
        n = idx.reindex_from_memory(Path(args.reindex_from))
        print(f"indexed {n} turns from {args.reindex_from}", file=sys.stderr)

    query = SearchQuery(
        keywords=tuple(args.keyword),
        date_from=_parse_date(args.date_from),
        date_to=_parse_date(args.date_to),
        speaker=args.speaker,
        limit=args.limit,
        mode=args.mode,
    )
    hits = idx.search(query)

    if args.json:
        json.dump([_hit_to_dict(h) for h in hits], sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        if not hits:
            print("(no results)")
        for h in hits:
            print(_format_hit(h))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
