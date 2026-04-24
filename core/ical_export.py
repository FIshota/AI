"""iCalendar (RFC 5545) serializer for ai-chan anniversaries.

- Pure stdlib, Python 3.9 compatible
- CRLF line endings
- 75-octet line folding (UTF-8 multi-byte safe)
- Escapes commas, semicolons, backslashes, and newlines per RFC 5545
- Emits a VTIMEZONE Asia/Tokyo block
- All-day events use DTSTART;VALUE=DATE:YYYYMMDD (no TZID needed)
- DTSTAMP is emitted in UTC `YYYYMMDDTHHMMSSZ`

This module deliberately only serializes; UID generation and importance
mapping live in `core.anniversary_ical_bridge`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

# RFC 5545 mandatory line terminator
CRLF = "\r\n"
LINE_OCTET_LIMIT = 75

DEFAULT_PRODID = "-//ai-chan//Anniversary//JA"
DEFAULT_TZID = "Asia/Tokyo"


@dataclass(frozen=True)
class ICalEvent:
    """A single VEVENT payload."""

    uid: str
    summary: str
    dtstart: date
    rrule: Optional[str] = None
    description: Optional[str] = None
    categories: Tuple[str, ...] = field(default_factory=tuple)
    # If True, a VALARM TRIGGER:-P1D block is attached.
    alarm: bool = False


# ── UID helpers ─────────────────────────────────────────────────────────
def stable_uid(anniversary_id: str, domain: str = "ai-chan.local") -> str:
    """Derive a stable, non-reversible UID from an anniversary id.

    Using SHA-256 truncated to 16 hex chars gives us >= 64 bits of identity
    which is far more than enough for calendar-UID uniqueness while hiding
    the source id.
    """
    digest = hashlib.sha256(anniversary_id.encode("utf-8")).hexdigest()[:16]
    return f"{digest}@{domain}"


# ── Escaping & folding ─────────────────────────────────────────────────
def escape_text(value: str) -> str:
    """Escape a TEXT value per RFC 5545 section 3.3.11.

    Order matters: backslash first so we don't double-escape our own
    escapes.
    """
    out = value.replace("\\", "\\\\")
    out = out.replace(";", "\\;")
    out = out.replace(",", "\\,")
    out = out.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return out


def fold_line(line: str, limit: int = LINE_OCTET_LIMIT) -> str:
    """Fold a logical content line to <= `limit` UTF-8 octets per physical
    line, per RFC 5545 section 3.1.

    Continuation lines begin with a single space. We fold on octet
    boundaries but never in the middle of a UTF-8 multi-byte codepoint.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= limit:
        return line

    chunks: List[bytes] = []
    i = 0
    # First physical line is full limit; continuation lines are
    # limit-1 (because of the leading space).
    first = True
    while i < len(encoded):
        remaining = len(encoded) - i
        budget = limit if first else limit - 1
        if remaining <= budget:
            chunks.append(encoded[i:])
            break
        # Step back to a safe UTF-8 boundary.
        end = i + budget
        # A UTF-8 continuation byte has bits 10xxxxxx (0x80..0xBF).
        while end > i and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        if end == i:
            # Degenerate case: a single codepoint exceeds the budget.
            # Push the whole codepoint anyway to guarantee progress.
            end = i + budget
            while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
                end += 1
        chunks.append(encoded[i:end])
        i = end
        first = False

    parts = [chunks[0].decode("utf-8")]
    for c in chunks[1:]:
        parts.append(" " + c.decode("utf-8"))
    return CRLF.join(parts)


# ── Line assembly ──────────────────────────────────────────────────────
def _lines_for_event(ev: ICalEvent, now_utc: datetime) -> List[str]:
    lines: List[str] = ["BEGIN:VEVENT"]
    lines.append(f"UID:{ev.uid}")
    lines.append("DTSTAMP:" + now_utc.strftime("%Y%m%dT%H%M%SZ"))
    lines.append("DTSTART;VALUE=DATE:" + ev.dtstart.strftime("%Y%m%d"))
    lines.append("SUMMARY:" + escape_text(ev.summary))
    if ev.description:
        lines.append("DESCRIPTION:" + escape_text(ev.description))
    if ev.categories:
        cats = ",".join(escape_text(c) for c in ev.categories)
        lines.append("CATEGORIES:" + cats)
    if ev.rrule:
        lines.append("RRULE:" + ev.rrule)
    if ev.alarm:
        lines.extend(
            [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                "DESCRIPTION:" + escape_text(ev.summary),
                "TRIGGER:-P1D",
                "END:VALARM",
            ]
        )
    lines.append("END:VEVENT")
    return lines


def _vtimezone_asia_tokyo() -> List[str]:
    # Asia/Tokyo has no DST and a fixed UTC+9 offset since 1951.
    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{DEFAULT_TZID}",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:JST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]


def serialize_calendar(
    events: Sequence[ICalEvent],
    calendar_name: str,
    prodid: str = DEFAULT_PRODID,
    now: Optional[datetime] = None,
) -> str:
    """Serialize a sequence of events into a VCALENDAR string (RFC 5545).

    Empty event sequences produce a valid empty calendar body.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    else:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

    logical: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:" + escape_text(prodid),
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + escape_text(calendar_name),
    ]
    logical.extend(_vtimezone_asia_tokyo())
    for ev in events:
        logical.extend(_lines_for_event(ev, now))
    logical.append("END:VCALENDAR")

    folded = [fold_line(ln) for ln in logical]
    # Trailing CRLF is required by RFC 5545.
    return CRLF.join(folded) + CRLF


# ── Loose round-trip validator (stdlib only) ───────────────────────────
def parse_ics_lines(text: str) -> List[str]:
    """Unfold CRLF-folded lines back into logical lines.

    This is intentionally minimal: it only performs line unfolding and
    returns the list of logical lines. Callers can assert structural
    invariants on top.
    """
    if "\r\n" not in text:
        raise ValueError("ICS text must use CRLF line endings")
    physical = text.split("\r\n")
    logical: List[str] = []
    for line in physical:
        if line.startswith(" ") or line.startswith("\t"):
            if not logical:
                raise ValueError("Continuation line with no predecessor")
            logical[-1] = logical[-1] + line[1:]
        else:
            if line == "" and logical and logical[-1] == "":
                continue
            logical.append(line)
    # Drop trailing empty string from final CRLF.
    while logical and logical[-1] == "":
        logical.pop()
    return logical


def validate_roundtrip(text: str) -> Iterable[str]:
    """Return an iterable of logical lines after validating basic
    VCALENDAR structure. Raises ValueError on structural problems.
    """
    lines = parse_ics_lines(text)
    if not lines or lines[0] != "BEGIN:VCALENDAR":
        raise ValueError("Missing BEGIN:VCALENDAR")
    if lines[-1] != "END:VCALENDAR":
        raise ValueError("Missing END:VCALENDAR")
    # Balance BEGIN/END pairs.
    stack: List[str] = []
    for ln in lines:
        if ln.startswith("BEGIN:"):
            stack.append(ln[len("BEGIN:") :])
        elif ln.startswith("END:"):
            name = ln[len("END:") :]
            if not stack or stack[-1] != name:
                raise ValueError(f"Unbalanced END:{name}")
            stack.pop()
    if stack:
        raise ValueError(f"Unclosed blocks: {stack}")
    return lines
