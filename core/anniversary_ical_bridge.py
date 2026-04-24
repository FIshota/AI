"""Bridge between `core.anniversary` records and `core.ical_export`.

Takes a plain anniversary dict (as returned by AnniversaryManager) plus an
`ImportanceBucket` and produces an `ICalEvent`.

Privacy: by default the description field is omitted. Callers may opt-in
to including `valence` / `mention_count` metadata via the
``include_private`` flag.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional, Tuple

from core.anniversary_importance import ImportanceBucket
from core.ical_export import ICalEvent, stable_uid


def _resolve_dtstart(record: Mapping[str, Any], reference: Optional[date] = None) -> date:
    """Build a `date` for DTSTART.

    Anniversary entries store (month, day) only and are yearly-recurring.
    We anchor DTSTART to the current year (or the ``reference`` year if
    provided) so that RRULE:FREQ=YEARLY does the right thing.

    Leap-day (2/29) entries fall back to 2/28 when the anchor year is not
    a leap year; the RRULE will still repeat every year and real leap
    years will resolve correctly downstream.
    """
    anchor_year = (reference or date.today()).year
    month = int(record["month"])
    day = int(record["day"])
    try:
        return date(anchor_year, month, day)
    except ValueError:
        if month == 2 and day == 29:
            return date(anchor_year, 2, 28)
        raise


def anniversary_to_ical_event(
    record: Mapping[str, Any],
    importance_bucket: ImportanceBucket,
    include_private: bool = False,
    reference: Optional[date] = None,
) -> ICalEvent:
    """Convert a single anniversary record into an ICalEvent.

    Args:
        record: Dict as stored by AnniversaryManager (must have id/label/
            month/day; is_birthday optional).
        importance_bucket: Drives the CATEGORIES and whether a VALARM is
            attached (critical/high → alarm; medium/low → no alarm).
        include_private: If True, include mean_valence / mention_count
            in the DESCRIPTION field. Default False for privacy.
        reference: Override the anchor year used for DTSTART. Defaults to
            today.
    """
    uid = stable_uid(str(record["id"]))
    summary = str(record["label"])
    dtstart = _resolve_dtstart(record, reference=reference)
    rrule = "FREQ=YEARLY" if record.get("yearly", True) else None

    categories: Tuple[str, ...] = ("ai-chan", importance_bucket.value)
    if record.get("is_birthday"):
        categories = categories + ("birthday",)

    description: Optional[str] = None
    if include_private:
        meta = record.get("auto_importance") or {}
        bits = []
        score = meta.get("score")
        if score is not None:
            bits.append(f"score={float(score):.2f}")
        mc = record.get("mention_count")
        if mc is not None:
            bits.append(f"mentions={int(mc)}")
        val = record.get("mean_valence")
        if val is not None:
            bits.append(f"valence={float(val):+.2f}")
        if bits:
            description = "; ".join(bits)

    alarm = importance_bucket in (ImportanceBucket.CRITICAL, ImportanceBucket.HIGH)

    return ICalEvent(
        uid=uid,
        summary=summary,
        dtstart=dtstart,
        rrule=rrule,
        description=description,
        categories=categories,
        alarm=alarm,
    )
