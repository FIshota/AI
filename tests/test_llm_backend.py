"""Tests for :mod:`core.llm_backend` and the MLX backend skeleton.

Covers 10+ scenarios:
    1. BackendSpec frozen
    2. BackendSpec validates the ``name`` field
    3. ``select_backend("stub")`` always works
    4. Stub is deterministic under a fixed seed
    5. ``select_backend("mlx")`` raises ``BackendUnavailable`` without mlx,
       or returns an ``MLXBackend`` when mlx is importable
    6. ``MLXBackend.generate`` returns a str (dummy or real)
    7. ``select_backend("torch")`` raises ``BackendUnavailable`` (placeholder)
    8. HinoMotoBridge accepts ``backend=None`` and keeps legacy behavior
    9. HinoMotoBridge with ``backend=BackendSpec("stub", ...)`` uses new path
   10. Parallel generation across two threads succeeds on the stub backend
   11. CPU backend round-trips through the stub layer and relabels output
"""
from __future__ import annotations

import threading
from typing import List, Optional

import pytest

from core.llm_backend import (
    BackendSpec,
    BackendUnavailable,
    CPUBackend,
    LLMBackend,
    StubBackend,
    select_backend,
)


# ---------------------------------------------------------------------------
# BackendSpec
# ---------------------------------------------------------------------------


def test_backend_spec_is_frozen():
    spec = BackendSpec(name="stub", device_hint="cpu")
    with pytest.raises(Exception):
        spec.name = "mlx"  # type: ignore[misc]


def test_backend_spec_rejects_invalid_name():
    with pytest.raises(ValueError):
        BackendSpec(name="totally-not-a-backend")


def test_backend_spec_extras_dict_is_copy():
    spec = BackendSpec(
        name="stub", extra=(("mlx_model_path", "/tmp/model"),)
    )
    assert spec.extras_dict() == {"mlx_model_path": "/tmp/model"}


# ---------------------------------------------------------------------------
# Stub + CPU backends
# ---------------------------------------------------------------------------


def test_select_stub_backend_always_works():
    b = select_backend(BackendSpec(name="stub"))
    assert isinstance(b, StubBackend)
    out = b.generate("hello", max_tokens=16, seed=1)
    assert isinstance(out, str)
    assert "[stub:" in out


def test_stub_backend_is_deterministic_with_seed():
    b = select_backend(BackendSpec(name="stub"))
    a1 = b.generate("same prompt", seed=123)
    a2 = b.generate("same prompt", seed=123)
    b2 = b.generate("same prompt", seed=999)
    assert a1 == a2
    assert a1 != b2


def test_stub_backend_logprobs_shape():
    b = StubBackend(BackendSpec(name="stub"))
    lp = b.logprobs("hello")
    assert isinstance(lp, list)
    assert len(lp) == 8
    assert all(-1.0 <= x <= 0.0 for x in lp)


def test_cpu_backend_relabels_output():
    b = select_backend(BackendSpec(name="cpu", device_hint="cpu"))
    assert isinstance(b, CPUBackend)
    out = b.generate("hi", seed=0)
    assert out.startswith("[cpu:")


# ---------------------------------------------------------------------------
# MLX backend
# ---------------------------------------------------------------------------


def _mlx_importable() -> bool:
    try:
        import mlx.core  # noqa: F401
        return True
    except ImportError:
        return False


def test_select_mlx_backend_behavior():
    spec = BackendSpec(name="mlx", device_hint="metal")
    if _mlx_importable():
        backend = select_backend(spec)
        # Must look like an LLMBackend
        assert isinstance(backend, LLMBackend)
        out = backend.generate("こんにちは", max_tokens=16, seed=7)
        assert isinstance(out, str)
        assert len(out) > 0
    else:
        with pytest.raises(BackendUnavailable):
            select_backend(spec)


def test_torch_backend_placeholder_unavailable():
    with pytest.raises(BackendUnavailable):
        select_backend(BackendSpec(name="torch"))


# ---------------------------------------------------------------------------
# HinoMotoBridge integration (additive)
# ---------------------------------------------------------------------------


def test_hinomoto_bridge_default_backend_is_none(tmp_path):
    from core.hinomoto_bridge import HinoMotoBridge

    bridge = HinoMotoBridge(
        checkpoint=tmp_path / "ckpt.pt",
        tokenizer=tmp_path / "tok.json",
    )
    # With backend=None the bridge keeps its legacy configuration.
    assert getattr(bridge, "_backend_spec") is None
    assert getattr(bridge, "_backend") is None


def test_hinomoto_bridge_with_stub_backend_generates(tmp_path):
    from core.hinomoto_bridge import HinoMotoBridge

    bridge = HinoMotoBridge(
        checkpoint=tmp_path / "ckpt.pt",
        tokenizer=tmp_path / "tok.json",
        backend=BackendSpec(name="stub", device_hint="test"),
    )
    out = bridge.reply("こんにちは", max_new_tokens=16, seed=42)
    assert isinstance(out, str)
    assert "[stub:" in out
    # Re-entrancy: same seed -> same output.
    out2 = bridge.reply("こんにちは", max_new_tokens=16, seed=42)
    assert out == out2


# ---------------------------------------------------------------------------
# Threading
# ---------------------------------------------------------------------------


def test_parallel_generation_on_stub_backend():
    backend = select_backend(BackendSpec(name="stub"))
    outputs: List[Optional[str]] = [None, None]
    errors: List[Optional[Exception]] = [None, None]

    def worker(idx: int, prompt: str) -> None:
        try:
            outputs[idx] = backend.generate(prompt, seed=idx)
        except Exception as exc:  # pragma: no cover — defensive
            errors[idx] = exc

    t1 = threading.Thread(target=worker, args=(0, "prompt-a"))
    t2 = threading.Thread(target=worker, args=(1, "prompt-b"))
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)

    assert all(e is None for e in errors)
    assert all(isinstance(o, str) and o for o in outputs)
    assert outputs[0] != outputs[1]
