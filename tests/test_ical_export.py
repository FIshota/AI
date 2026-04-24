"""Tests for core.ical_export and core.anniversary_ical_bridge."""
from __future__ import annotations

import re
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone

import pytest

from core.anniversary_ical_bridge import anniversary_to_ical_event
from core.anniversary_importance import ImportanceBucket
from core.ical_export import (
    CRLF,
    ICalEvent,
    escape_text,
    fold_line,
    parse_ics_lines,
    serialize_calendar,
    stable_uid,
    validate_roundtrip,
)


FIXED_NOW = datetime(2026, 4, 24, 12, 34, 56, tzinfo=timezone.utc)


def _single_event(**overrides) -> ICalEvent:
    defaults = dict(
        uid="abc123@ai-chan.local",
        summary="結婚記念日",
        dtstart=date(2026, 6, 10),
        rrule="FREQ=YEARLY",
        description=None,
        categories=("ai-chan", "critical"),
        alarm=False,
    )
    defaults.update(overrides)
    return ICalEvent(**defaults)


# ── 1. Single event RFC 5545 format / CRLF ──────────────────────────────
def test_single_event_crlf_and_required_fields():
    ev = _single_event()
    body = serialize_calendar([ev], "家族の記念日", now=FIXED_NOW)

    # CRLF-only line endings.
    assert "\r\n" in body
    assert "\n" not in body.replace("\r\n", "")
    assert body.endswith(CRLF)

    # Required envelope.
    assert body.startswith("BEGIN:VCALENDAR" + CRLF)
    assert "END:VCALENDAR" + CRLF in body
    assert "VERSION:2.0" in body
    assert "PRODID:-//ai-chan//Anniversary//JA" in body
    assert "CALSCALE:GREGORIAN" in body
    assert "UID:abc123@ai-chan.local" in body
    assert "DTSTAMP:20260424T123456Z" in body
    assert "DTSTART;VALUE=DATE:20260610" in body


# ── 2. Multiple events wrapped in one VCALENDAR ─────────────────────────
def test_multiple_events_single_calendar_wrapper():
    a = _single_event(uid="a@x", summary="A")
    b = _single_event(uid="b@x", summary="B")
    body = serialize_calendar([a, b], "cal", now=FIXED_NOW)

    assert body.count("BEGIN:VCALENDAR") == 1
    assert body.count("END:VCALENDAR") == 1
    assert body.count("BEGIN:VEVENT") == 2
    assert body.count("END:VEVENT") == 2


# ── 3. Special-character escaping ───────────────────────────────────────
def test_escape_text_rfc5545_rules():
    raw = "a,b;c\\d\ne"
    esc = escape_text(raw)
    assert esc == "a\\,b\\;c\\\\d\\ne"


def test_summary_special_chars_escaped_in_output():
    ev = _single_event(
        summary="a,b;c\\d\ne",
        categories=("x,y", "z;w"),
    )
    body = serialize_calendar([ev], "cal", now=FIXED_NOW)
    assert "SUMMARY:a\\,b\\;c\\\\d\\ne" in body
    # Categories are joined by unescaped commas, but internal commas are escaped.
    assert "CATEGORIES:x\\,y,z\\;w" in body


# ── 4. Line folding at 75 octets, UTF-8 safe ────────────────────────────
def test_fold_line_japanese_multibyte_boundary():
    # 70 Japanese chars = 210 UTF-8 octets; must fold into >=3 lines and
    # never split a codepoint.
    long_summary = "記念日" * 30  # each char 3 bytes -> 270 bytes
    line = "SUMMARY:" + long_summary
    folded = fold_line(line, limit=75)
    parts = folded.split(CRLF)
    assert len(parts) > 1
    for part in parts:
        assert len(part.encode("utf-8")) <= 75
    # Continuation markers and codepoint integrity.
    for cont in parts[1:]:
        assert cont.startswith(" ")
    # Concatenating (first + continuation-bodies) reconstructs the original.
    rejoined = parts[0] + "".join(p[1:] for p in parts[1:])
    assert rejoined == line


# ── 5. RRULE generation ─────────────────────────────────────────────────
def test_rrule_yearly_emitted():
    body = serialize_calendar([_single_event()], "cal", now=FIXED_NOW)
    assert "RRULE:FREQ=YEARLY" in body


def test_rrule_absent_when_none():
    ev = _single_event(rrule=None)
    body = serialize_calendar([ev], "cal", now=FIXED_NOW)
    assert "RRULE:" not in body


# ── 6. VALARM presence based on bucket ─────────────────────────────────
def test_valarm_attached_for_critical():
    ev = _single_event(alarm=True)
    body = serialize_calendar([ev], "cal", now=FIXED_NOW)
    assert "BEGIN:VALARM" in body
    assert "TRIGGER:-P1D" in body
    assert "END:VALARM" in body


def test_no_valarm_for_medium():
    record = {"id": "x", "label": "普通の日", "month": 7, "day": 7,
              "is_birthday": False, "yearly": True}
    ev = anniversary_to_ical_event(record, ImportanceBucket.MEDIUM)
    body = serialize_calendar([ev], "cal", now=FIXED_NOW)
    assert "VALARM" not in body


# ── 7. UID stability ────────────────────────────────────────────────────
def test_stable_uid_deterministic():
    u1 = stable_uid("anniv-0001")
    u2 = stable_uid("anniv-0001")
    u3 = stable_uid("anniv-0002")
    assert u1 == u2
    assert u1 != u3
    assert u1.endswith("@ai-chan.local")


def test_bridge_uses_stable_uid():
    rec = {"id": "anniv-42", "label": "誕生日", "month": 12, "day": 25,
           "is_birthday": True, "yearly": True}
    a = anniversary_to_ical_event(rec, ImportanceBucket.HIGH)
    b = anniversary_to_ical_event(rec, ImportanceBucket.HIGH)
    assert a.uid == b.uid == stable_uid("anniv-42")


# ── 8. VTIMEZONE Asia/Tokyo block ──────────────────────────────────────
def test_vtimezone_block_present():
    body = serialize_calendar([_single_event()], "cal", now=FIXED_NOW)
    assert "BEGIN:VTIMEZONE" in body
    assert "TZID:Asia/Tokyo" in body
    assert "TZOFFSETTO:+0900" in body
    assert "END:VTIMEZONE" in body


# ── 9. Loose round-trip parse ──────────────────────────────────────────
def test_roundtrip_parse_preserves_logical_lines():
    body = serialize_calendar([_single_event()], "cal", now=FIXED_NOW)
    lines = list(validate_roundtrip(body))
    assert lines[0] == "BEGIN:VCALENDAR"
    assert lines[-1] == "END:VCALENDAR"
    # UID round-trips through the unfolder.
    assert any(ln == "UID:abc123@ai-chan.local" for ln in lines)


def test_roundtrip_handles_folded_long_summary():
    ev = _single_event(summary="記念日" * 40)
    body = serialize_calendar([ev], "cal", now=FIXED_NOW)
    lines = list(validate_roundtrip(body))
    summary_lines = [ln for ln in lines if ln.startswith("SUMMARY:")]
    assert len(summary_lines) == 1
    assert summary_lines[0] == "SUMMARY:" + "記念日" * 40


# ── 10. DTSTAMP UTC format ─────────────────────────────────────────────
def test_dtstamp_is_utc_basic_format():
    body = serialize_calendar([_single_event()], "cal", now=FIXED_NOW)
    m = re.search(r"DTSTAMP:(\d{8}T\d{6}Z)", body)
    assert m is not None
    assert m.group(1) == "20260424T123456Z"


# ── 11. Empty calendar is valid ────────────────────────────────────────
def test_empty_event_list_produces_valid_calendar():
    body = serialize_calendar([], "empty", now=FIXED_NOW)
    assert "BEGIN:VCALENDAR" in body
    assert "END:VCALENDAR" in body
    assert "BEGIN:VEVENT" not in body
    # Still round-trip parseable.
    list(validate_roundtrip(body))


# ── 12. Frozen dataclass / Py3.9 compat ─────────────────────────────────
def test_ical_event_is_frozen():
    ev = _single_event()
    with pytest.raises(FrozenInstanceError):
        ev.summary = "mutated"  # type: ignore[misc]


# ── Extra: bridge end-to-end with a realistic Japanese record ──────────
def test_bridge_japanese_birthday_end_to_end():
    rec = {
        "id": "b-001",
        "label": "ゆうきの誕生日",
        "month": 3,
        "day": 14,
        "is_birthday": True,
        "yearly": True,
        "auto_importance": {"score": 0.91, "bucket": "critical"},
        "mention_count": 42,
        "mean_valence": 0.73,
    }
    ev = anniversary_to_ical_event(
        rec, ImportanceBucket.CRITICAL, include_private=True
    )
    assert ev.alarm is True
    assert "birthday" in ev.categories
    assert "critical" in ev.categories
    assert ev.description is not None
    assert "mentions=42" in ev.description

    body = serialize_calendar([ev], "家族", now=FIXED_NOW)
    assert "SUMMARY:ゆうきの誕生日" in body
    assert "BEGIN:VALARM" in body


def test_parse_ics_rejects_lf_only():
    with pytest.raises(ValueError):
        parse_ics_lines("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
