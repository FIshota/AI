"""
ai-chan Observability スケルトン (OpenTelemetry 最小ラッパ)

10 年運用の原則「ローカル優先・無課金・プライバシーファースト」に従い、
既定では全ての trace / span / metric は no-op。

有効化:
    OTEL_ENABLED=1 環境変数を設定すると console exporter にのみ出力する。
    外部クラウドへ送信する経路は本ファイルには実装しない (レビュー必須)。

opentelemetry パッケージがインストールされていなくても import に失敗せず、
no-op ダミー実装にフォールバックする。
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional

__all__ = [
    "SpanContext",
    "MetricSample",
    "get_tracer",
    "start_span",
    "record_metric",
    "is_enabled",
]

_LOG = logging.getLogger(__name__)


def _otel_enabled() -> bool:
    """OTEL_ENABLED env var が "1" / "true" / "yes" のいずれかなら有効。"""
    raw = os.environ.get("OTEL_ENABLED", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# opentelemetry インポート (失敗時は no-op)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - 環境依存
    from opentelemetry import trace as _otel_trace  # type: ignore

    _OTEL_AVAILABLE = True
except Exception:  # noqa: BLE001 - 幅広く握りつぶす (import 時にクラッシュしない為)
    _otel_trace = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False


# ---------------------------------------------------------------------------
# 値オブジェクト (frozen dataclass で不変)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SpanContext:
    """span 1 個の観測結果 (no-op 実装でも戻り値型として利用)。"""

    name: str
    start_ns: int
    end_ns: Optional[int] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    noop: bool = True

    @property
    def duration_ns(self) -> Optional[int]:
        if self.end_ns is None:
            return None
        return self.end_ns - self.start_ns


@dataclass(frozen=True)
class MetricSample:
    """単発のメトリクス記録。"""

    name: str
    value: float
    unit: str = ""
    timestamp_ns: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tracer ダミー実装
# ---------------------------------------------------------------------------
class _NoopTracer:
    """OTEL_ENABLED=0 もしくは opentelemetry 未インストール時のダミー。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - 表示用
        return f"<NoopTracer name={self.name!r}>"


def is_enabled() -> bool:
    """OTEL が実行時に有効かどうか。"""
    return _OTEL_AVAILABLE and _otel_enabled()


def get_tracer(name: str) -> Any:
    """tracer を取得する。

    - OTEL 有効かつ opentelemetry 利用可: 実 tracer
    - それ以外: _NoopTracer
    """
    if is_enabled() and _otel_trace is not None:  # pragma: no cover - 実 OTEL 経路
        try:
            return _otel_trace.get_tracer(name)
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("falling back to NoopTracer: %s", exc)
            return _NoopTracer(name)
    return _NoopTracer(name)


# ---------------------------------------------------------------------------
# start_span (contextmanager)
# ---------------------------------------------------------------------------
@contextmanager
def start_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[SpanContext]:
    """span を開始する context manager。

    使用例:
        with start_span("purge_subject", {"subject": "foo"}) as ctx:
            do_work()

    OTEL 無効時は純粋な no-op (タイムスタンプだけ記録)。
    """
    attrs: Dict[str, Any] = dict(attributes or {})
    start_ns = time.monotonic_ns()

    if is_enabled() and _otel_trace is not None:  # pragma: no cover - 実 OTEL 経路
        tracer = get_tracer("ai-chan")
        try:
            with tracer.start_as_current_span(name, attributes=attrs) as _span:
                ctx = SpanContext(
                    name=name,
                    start_ns=start_ns,
                    attributes=attrs,
                    noop=False,
                )
                yield ctx
                return
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("span fallback to noop: %s", exc)

    # no-op 経路
    ctx = SpanContext(
        name=name,
        start_ns=start_ns,
        attributes=attrs,
        noop=True,
    )
    try:
        yield ctx
    finally:
        # end_ns は返り値型には反映しないが (frozen)、副作用の代用として debug log
        end_ns = time.monotonic_ns()
        _LOG.debug(
            "noop span name=%s duration_ns=%d attrs=%s",
            name,
            end_ns - start_ns,
            attrs,
        )


# ---------------------------------------------------------------------------
# record_metric
# ---------------------------------------------------------------------------
def record_metric(
    name: str,
    value: float,
    unit: str = "",
    attributes: Optional[Dict[str, Any]] = None,
) -> MetricSample:
    """メトリクスを 1 点記録し、MetricSample を返す。

    OTEL 無効時は no-op (sample は返すが外部送信しない)。
    """
    sample = MetricSample(
        name=name,
        value=float(value),
        unit=unit,
        timestamp_ns=time.time_ns(),
        attributes=dict(attributes or {}),
    )

    if is_enabled():  # pragma: no cover - 実 OTEL 経路
        # 現状は console に debug 出力するのみ。
        # 外部 exporter を足す場合は docs/quality/OBSERVABILITY.md のレビュー手順に従うこと。
        _LOG.info(
            "metric name=%s value=%s unit=%s attrs=%s",
            sample.name,
            sample.value,
            sample.unit,
            sample.attributes,
        )
    return sample
