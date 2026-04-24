"""
core/observability のユニットテスト。

OTEL パッケージが無い / OTEL_ENABLED=0 の環境でも全て通ること。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# プロジェクトルートを path に追加 (tests/ が conftest を持たない場合の保険)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core import observability as obs  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    """各テストで OTEL_ENABLED を明示的に 0 にする。"""
    monkeypatch.setenv("OTEL_ENABLED", "0")


@pytest.mark.unit
def test_noop_when_otel_disabled() -> None:
    """OTEL_ENABLED=0 なら is_enabled は False。"""
    assert obs.is_enabled() is False


@pytest.mark.unit
def test_get_tracer_returns_noop_when_disabled() -> None:
    """無効時は NoopTracer を返す。"""
    tracer = obs.get_tracer("ai-chan-test")
    # _NoopTracer は private クラスだが、name 属性で識別できる
    assert hasattr(tracer, "name")
    assert tracer.name == "ai-chan-test"


@pytest.mark.unit
def test_start_span_context_manager() -> None:
    """start_span は context manager として機能し SpanContext を yield する。"""
    with obs.start_span("unit-op", {"foo": "bar"}) as ctx:
        assert isinstance(ctx, obs.SpanContext)
        assert ctx.name == "unit-op"
        assert ctx.attributes == {"foo": "bar"}
        assert ctx.noop is True
        assert ctx.start_ns > 0


@pytest.mark.unit
def test_record_metric_returns_sample() -> None:
    """record_metric は MetricSample を返す。"""
    sample = obs.record_metric("ai_chan.test.count", 42.0, unit="1", attributes={"k": "v"})
    assert isinstance(sample, obs.MetricSample)
    assert sample.name == "ai_chan.test.count"
    assert sample.value == 42.0
    assert sample.unit == "1"
    assert sample.attributes == {"k": "v"}
    assert sample.timestamp_ns > 0


@pytest.mark.unit
def test_nested_spans() -> None:
    """span のネストができる (no-op 経路でも壊れない)。"""
    with obs.start_span("outer") as outer:
        with obs.start_span("inner", {"depth": 1}) as inner:
            assert outer.name == "outer"
            assert inner.name == "inner"
            assert inner.attributes == {"depth": 1}
            assert outer.noop is True
            assert inner.noop is True


@pytest.mark.unit
def test_fallback_when_opentelemetry_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """opentelemetry 未インストールを模した状態でも落ちない。"""
    # 強制的に未インストール扱いにする
    monkeypatch.setattr(obs, "_OTEL_AVAILABLE", False)
    monkeypatch.setattr(obs, "_otel_trace", None)
    monkeypatch.setenv("OTEL_ENABLED", "1")  # 有効化しても fallback するべき

    assert obs.is_enabled() is False  # _OTEL_AVAILABLE=False なので False
    tracer = obs.get_tracer("fallback")
    assert tracer.name == "fallback"

    with obs.start_span("fallback-span") as ctx:
        assert ctx.noop is True

    sample = obs.record_metric("fallback.metric", 1.0)
    assert sample.value == 1.0


@pytest.mark.unit
def test_span_context_is_frozen() -> None:
    """SpanContext は frozen dataclass (不変)。"""
    ctx = obs.SpanContext(name="x", start_ns=1)
    with pytest.raises(Exception):
        ctx.name = "y"  # type: ignore[misc]


@pytest.mark.unit
def test_core_init_does_not_export_observability() -> None:
    """core/__init__.py からは observability を export しない (明示 import 必須)。"""
    import core

    assert "observability" not in getattr(core, "__all__", [])
    assert "get_tracer" not in dir(core)


@pytest.mark.unit
def test_otel_enabled_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """OTEL_ENABLED の各種真偽値パース。"""
    for truthy in ("1", "true", "True", "YES", "on"):
        monkeypatch.setenv("OTEL_ENABLED", truthy)
        assert obs._otel_enabled() is True
    for falsy in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("OTEL_ENABLED", falsy)
        assert obs._otel_enabled() is False
