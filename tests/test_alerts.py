"""Tests for core.alerts and monitoring scripts."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core import alerts  # noqa: E402
from core.alerts import (  # noqa: E402
    Alert,
    FileSink,
    MacOsNotificationSink,
    MultiSink,
    emit_alert,
    make_alert_id,
    set_default_sink,
)


def test_alert_rejects_invalid_severity() -> None:
    with pytest.raises(ValueError):
        Alert(id="x", severity="panic", title="t", body="b")


def test_alert_rejects_empty_title() -> None:
    with pytest.raises(ValueError):
        Alert(id="x", severity="info", title="", body="b")


def test_alert_is_frozen() -> None:
    a = Alert(id="x", severity="info", title="t", body="b")
    with pytest.raises(Exception):
        a.title = "nope"  # type: ignore[misc]


def test_make_alert_id_is_stable_and_short() -> None:
    a = make_alert_id("warn", "T", "B")
    b = make_alert_id("warn", "T", "B")
    c = make_alert_id("warn", "T", "B2")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_filesink_writes_markdown(tmp_path: Path) -> None:
    sink = FileSink(base_dir=tmp_path)
    sink.emit(Alert(id="abc", severity="warn", title="low disk", body="2.1 GB"))
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "low disk" in content
    assert "warn" in content
    assert "abc" in content


def test_filesink_appends(tmp_path: Path) -> None:
    sink = FileSink(base_dir=tmp_path)
    sink.emit(Alert(id="a", severity="info", title="one", body="b1"))
    sink.emit(Alert(id="b", severity="info", title="two", body="b2"))
    content = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "one" in content and "two" in content


def test_multisink_fanout_and_isolation(tmp_path: Path) -> None:
    calls = []

    class GoodSink:
        def emit(self, a: Alert) -> None:
            calls.append(("good", a.id))

    class BadSink:
        def emit(self, a: Alert) -> None:
            raise RuntimeError("boom")

    ms = MultiSink([BadSink(), GoodSink(), BadSink()])
    ms.emit(Alert(id="x", severity="info", title="t", body="b"))
    assert calls == [("good", "x")]


def test_macos_sink_falls_back_without_osascript(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(alerts, "_osascript_available", lambda: False)
    fb = FileSink(base_dir=tmp_path)
    sink = MacOsNotificationSink(fallback=fb)
    sink.emit(Alert(id="f", severity="critical", title="fb", body="bb"))
    assert any(tmp_path.glob("*.md"))


def test_emit_alert_uses_default_sink(tmp_path: Path) -> None:
    captured = []

    class Capture:
        def emit(self, a: Alert) -> None:
            captured.append(a)

    set_default_sink(Capture())
    try:
        a = emit_alert("warn", "hello", "world")
        assert captured == [a]
        assert a.severity == "warn"
        assert a.title == "hello"
    finally:
        set_default_sink(MultiSink([FileSink(base_dir=tmp_path)]))


def test_check_backup_freshness_evaluate(tmp_path: Path) -> None:
    from scripts.check_backup_freshness import evaluate

    # empty dir -> critical
    sev, _, _ = evaluate(tmp_path)
    assert sev == "critical"

    # fresh log -> ok
    log = tmp_path / "drill.log"
    log.write_text("ok")
    sev, _, _ = evaluate(tmp_path)
    assert sev == "ok"

    # stale warn
    old = time.time() - 40 * 86400
    import os as _os

    _os.utime(log, (old, old))
    sev, _, _ = evaluate(tmp_path)
    assert sev == "warn"

    # stale critical
    very_old = time.time() - 120 * 86400
    _os.utime(log, (very_old, very_old))
    sev, _, _ = evaluate(tmp_path)
    assert sev == "critical"


def test_check_disk_space_evaluate(tmp_path: Path) -> None:
    from scripts.check_disk_space import evaluate

    sev, _, _, free_gb = evaluate(tmp_path)
    assert sev in ("ok", "warn", "critical")
    assert free_gb >= 0
