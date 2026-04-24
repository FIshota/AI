"""Local-only monitoring alerts for ai-chan.

Design principles:
- No external SaaS. Alerts go to macOS notification center and a local
  markdown file on the owner's Desktop.
- All sinks must be best-effort: a failure in one sink must not break
  others, and must never raise to the caller.
- Alerts are immutable value objects (frozen dataclass).

Severity model:
- info:     FYI, rarely surfaced as banner, always logged to file
- warn:     something is drifting (e.g. disk low, drill stale)
- critical: immediate owner attention (e.g. drill 90d+, disk <2GB)
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Protocol

_VALID_SEVERITIES = ("info", "warn", "critical")


def _default_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Alert:
    """An immutable alert event."""
    id: str
    severity: str
    title: str
    body: str
    ts: str = field(default_factory=_default_ts)

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"invalid severity {self.severity!r}, "
                f"expected one of {_VALID_SEVERITIES}"
            )
        if not self.title:
            raise ValueError("alert title must not be empty")


def make_alert_id(severity: str, title: str, body: str) -> str:
    """Stable id derived from content (for dedupe / tracing)."""
    h = hashlib.sha256(f"{severity}|{title}|{body}".encode("utf-8")).hexdigest()
    return h[:16]


class AlertSink(Protocol):
    """A place an Alert can be emitted to."""

    def emit(self, alert: Alert) -> None:  # pragma: no cover - protocol
        ...


def _osascript_available() -> bool:
    return shutil.which("osascript") is not None


class MacOsNotificationSink:
    """Posts a banner via macOS notification center.

    Falls back silently to a FileSink if osascript is not available
    (e.g. Linux, CI).
    """

    def __init__(self, fallback: Optional["FileSink"] = None) -> None:
        self._fallback = fallback or FileSink()

    def emit(self, alert: Alert) -> None:
        if not _osascript_available():
            self._fallback.emit(alert)
            return
        # Escape double quotes for AppleScript string literal.
        safe_title = alert.title.replace('"', '\\"')
        safe_body = alert.body.replace('"', '\\"')
        script = (
            f'display notification "{safe_body}" '
            f'with title "ai-chan [{alert.severity}]" '
            f'subtitle "{safe_title}"'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            # Never let a banner failure take down the caller.
            self._fallback.emit(alert)


class FileSink:
    """Appends alerts to ~/Desktop/AI_CHAN_ALERTS/YYYY-MM-DD.md."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        if base_dir is None:
            base_dir = Path.home() / "Desktop" / "AI_CHAN_ALERTS"
        self._base_dir = Path(base_dir)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def path_for(self, when: Optional[datetime] = None) -> Path:
        when = when or datetime.now()
        return self._base_dir / f"{when.strftime('%Y-%m-%d')}.md"

    def emit(self, alert: Alert) -> None:
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            path = self.path_for()
            new_file = not path.exists()
            with path.open("a", encoding="utf-8") as f:
                if new_file:
                    f.write(f"# ai-chan alerts {datetime.now().strftime('%Y-%m-%d')}\n\n")
                f.write(
                    f"## [{alert.severity}] {alert.title}\n"
                    f"- id: `{alert.id}`\n"
                    f"- ts: {alert.ts}\n\n"
                    f"{alert.body}\n\n---\n\n"
                )
        except Exception:
            # FileSink is the last line of defense; swallow errors.
            pass


class MultiSink:
    """Fan-out to multiple sinks. Failures in one sink do not affect others."""

    def __init__(self, sinks: Iterable[AlertSink]) -> None:
        self._sinks: List[AlertSink] = list(sinks)

    def emit(self, alert: Alert) -> None:
        for sink in self._sinks:
            try:
                sink.emit(alert)
            except Exception:
                continue


_default_sink: Optional[AlertSink] = None


def _get_default_sink() -> AlertSink:
    global _default_sink
    if _default_sink is None:
        _default_sink = MultiSink([MacOsNotificationSink(), FileSink()])
    return _default_sink


def set_default_sink(sink: AlertSink) -> None:
    """Override the default sink (primarily for tests)."""
    global _default_sink
    _default_sink = sink


def emit_alert(
    severity: str,
    title: str,
    body: str,
    *,
    sink: Optional[AlertSink] = None,
    alert_id: Optional[str] = None,
) -> Alert:
    """Build an Alert and emit it. Returns the constructed Alert."""
    aid = alert_id or make_alert_id(severity, title, body)
    alert = Alert(id=aid, severity=severity, title=title, body=body)
    target = sink or _get_default_sink()
    try:
        target.emit(alert)
    except Exception:
        pass
    return alert


__all__ = [
    "Alert",
    "AlertSink",
    "FileSink",
    "MacOsNotificationSink",
    "MultiSink",
    "emit_alert",
    "make_alert_id",
    "set_default_sink",
]
