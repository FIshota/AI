"""CLI: export ai-chan anniversaries to an RFC 5545 .ics file.

Usage:
    python scripts/export_anniversaries_ical.py \
        [--output anniversaries.ics] \
        [--since YYYY-MM-DD] \
        [--include-all] \
        [--include-private] \
        [--validate]

Default behaviour:
- Output: artifacts/anniversaries_<YYYYMMDD>.ics
- Only `critical` + `high` bucket events are exported.
- Description field omitted (privacy).
- --validate re-parses the generated file for a round-trip check.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional

# Allow running as a plain script from repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.anniversary import AnniversaryManager  # noqa: E402
from core.anniversary_ical_bridge import anniversary_to_ical_event  # noqa: E402
from core.anniversary_importance import ImportanceBucket  # noqa: E402
from core.ical_export import (  # noqa: E402
    ICalEvent,
    serialize_calendar,
    validate_roundtrip,
)

logger = logging.getLogger("export_anniversaries_ical")

EXPORT_BUCKETS_DEFAULT = {ImportanceBucket.CRITICAL, ImportanceBucket.HIGH}
EXPORT_BUCKETS_ALL = set(ImportanceBucket)


def _bucket_of_record(record: dict) -> ImportanceBucket:
    meta = record.get("auto_importance") or {}
    raw = meta.get("bucket")
    if raw:
        try:
            return ImportanceBucket(raw)
        except ValueError:
            logger.debug("Unknown bucket %r; defaulting to MEDIUM", raw)
    return ImportanceBucket.MEDIUM


def _since_filter(record: dict, since: Optional[date]) -> bool:
    if since is None:
        return True
    meta = record.get("auto_importance") or {}
    updated = meta.get("updated_at")
    if not updated:
        return True
    try:
        dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
    except ValueError:
        return True
    return dt.date() >= since


def build_events(
    records: Iterable[dict],
    allowed_buckets: set,
    include_private: bool,
    since: Optional[date],
) -> List[ICalEvent]:
    events: List[ICalEvent] = []
    for r in records:
        if not _since_filter(r, since):
            continue
        bucket = _bucket_of_record(r)
        if bucket not in allowed_buckets:
            continue
        events.append(
            anniversary_to_ical_event(
                r, bucket, include_private=include_private
            )
        )
    return events


def _default_output_path() -> Path:
    stamp = date.today().strftime("%Y%m%d")
    return REPO_ROOT / "artifacts" / f"anniversaries_{stamp}.ics"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export anniversaries to iCal")
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--since", type=str, default=None,
                   help="YYYY-MM-DD lower bound on auto_importance.updated_at")
    p.add_argument("--include-all", action="store_true",
                   help="Export every bucket, not just critical/high")
    p.add_argument("--include-private", action="store_true",
                   help="Include valence / mention_count in DESCRIPTION")
    p.add_argument("--validate", action="store_true",
                   help="Re-parse the generated file to check structure")
    p.add_argument("--data-dir", type=Path,
                   default=REPO_ROOT / "data",
                   help="Anniversary data directory")
    p.add_argument("--calendar-name", type=str,
                   default="ai-chan 記念日")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    since: Optional[date] = None
    if args.since:
        since = date.fromisoformat(args.since)

    mgr = AnniversaryManager(args.data_dir)
    records = mgr.list_all()
    allowed = EXPORT_BUCKETS_ALL if args.include_all else EXPORT_BUCKETS_DEFAULT

    events = build_events(records, allowed, args.include_private, since)
    logger.info("Exporting %d / %d anniversaries", len(events), len(records))

    body = serialize_calendar(events, calendar_name=args.calendar_name)

    output = args.output or _default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8", newline="")
    logger.info("Wrote %s", output)

    if args.validate:
        validate_roundtrip(body)
        logger.info("Round-trip validation OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
