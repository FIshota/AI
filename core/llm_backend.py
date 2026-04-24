"""LLM backend abstraction layer.

This module defines a minimal, stable interface for pluggable LLM
backends so that the rest of ai-chan can stay agnostic of whether the
inference runs on CPU, MLX (Apple Silicon), a remote process, or a
deterministic stub used in tests and CI.

Design notes
------------
* Backends are selected via :func:`select_backend` which takes a
  frozen :class:`BackendSpec` — callers pass plain data, not a class.
* Real backend implementations live under ``core.backends.*`` and are
  imported lazily so that importing this module never pulls in heavy
  optional dependencies (e.g. ``mlx``, ``torch``).
* The ``stub`` backend is pure stdlib and always works, which is what
  lets tests and CI run regardless of the host machine.

Compatibility
-------------
* Python 3.9+ compatible — uses ``Optional[X]`` / ``List[X]`` rather
  than ``X | Y`` to match the style of the rest of this codebase.
* All dataclasses are ``frozen=True``.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Protocol, runtime_checkable

try:
    # Python 3.8+ — ``Literal`` from ``typing`` works in 3.9 too.
    from typing import Literal
except ImportError:  # pragma: no cover — 3.7 fallback, unused in prod
    from typing_extensions import Literal  # type: ignore

log = logging.getLogger(__name__)


BackendName = Literal["cpu", "mlx", "torch", "stub"]
_VALID_NAMES = ("cpu", "mlx", "torch", "stub")


class BackendUnavailable(RuntimeError):
    """Raised when a requested backend cannot be constructed.

    Typical reasons:
      * optional runtime dependency (e.g. ``mlx``) is not installed
      * hardware is incompatible (e.g. MLX requested on non-Apple Silicon)
      * model assets required by the backend are missing
    """


# ---------------------------------------------------------------------------
# Specification / protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendSpec:
    """Immutable description of a desired backend.

    Attributes
    ----------
    name:
        One of ``"cpu"``, ``"mlx"``, ``"torch"``, ``"stub"``.
    device_hint:
        Free-form device label, e.g. ``"metal"``, ``"cpu"``, ``"cuda:0"``.
        Backends may treat this as advisory.
    precision:
        e.g. ``"fp16"``, ``"fp32"``, ``"int4"``. Advisory.
    notes:
        Free-form human-readable notes for logs / bench labels.
    extra:
        Backend-specific key/value options (e.g. model path).
        Kept as a tuple of pairs to preserve immutability.
    """

    name: str
    device_hint: str = ""
    precision: str = "fp32"
    notes: str = ""
    extra: tuple = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.name not in _VALID_NAMES:
            raise ValueError(
                f"invalid backend name {self.name!r}; "
                f"expected one of {_VALID_NAMES}"
            )

    def extras_dict(self) -> dict:
        """Return ``extra`` as a plain dict (non-mutating)."""
        return dict(self.extra)


@runtime_checkable
class LLMBackend(Protocol):
    """Minimal backend interface.

    Implementations do not need to subclass this — duck typing works.
    """

    name: str

    def generate(
        self,
        prompt: str,
        max_tokens: int = 64,
        temperature: float = 0.0,
        top_p: float = 1.0,
        seed: Optional[int] = None,
    ) -> str:
        ...

    def logprobs(self, prompt: str) -> List[float]:
        ...


# ---------------------------------------------------------------------------
# Stub backend (always available)
# ---------------------------------------------------------------------------


class StubBackend:
    """Deterministic, dependency-free backend for CI and tests.

    Generation is a seeded hash of the prompt — stable across runs so
    that tests can assert on content without flakiness.
    """

    name = "stub"

    def __init__(self, spec: BackendSpec) -> None:
        self.spec = spec

    def _seed_key(self, prompt: str, seed: Optional[int]) -> str:
        payload = f"{seed if seed is not None else 0}::{prompt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def generate(
        self,
        prompt: str,
        max_tokens: int = 64,
        temperature: float = 0.0,
        top_p: float = 1.0,
        seed: Optional[int] = None,
    ) -> str:
        digest = self._seed_key(prompt, seed)
        # Produce a bounded pseudo-text so downstream callers get a str.
        body = digest[: max(8, min(max_tokens, 64))]
        return f"[stub:{self.spec.device_hint or 'cpu'}] {body}"

    def logprobs(self, prompt: str) -> List[float]:
        digest = self._seed_key(prompt, 0)
        # Map hex pairs to [-1.0, 0.0] pseudo-logprobs.
        return [-(int(digest[i : i + 2], 16) / 255.0) for i in range(0, 16, 2)]


# ---------------------------------------------------------------------------
# CPU backend (pure stdlib placeholder, intentionally trivial)
# ---------------------------------------------------------------------------


class CPUBackend:
    """Pure-Python CPU backend.

    Today this is a thin wrapper around :class:`StubBackend` with a
    different label — the real CPU implementation will slot in once the
    portable tokenizer + model are ported, but the surface stays stable.
    """

    name = "cpu"

    def __init__(self, spec: BackendSpec) -> None:
        self.spec = spec
        self._inner = StubBackend(
            BackendSpec(
                name="stub",
                device_hint=spec.device_hint or "cpu",
                precision=spec.precision,
                notes=f"cpu-fallback({spec.notes})",
                extra=spec.extra,
            )
        )

    def generate(
        self,
        prompt: str,
        max_tokens: int = 64,
        temperature: float = 0.0,
        top_p: float = 1.0,
        seed: Optional[int] = None,
    ) -> str:
        text = self._inner.generate(prompt, max_tokens, temperature, top_p, seed)
        # Re-label so callers can tell they came through the CPU path.
        return text.replace("[stub:", "[cpu:")

    def logprobs(self, prompt: str) -> List[float]:
        return self._inner.logprobs(prompt)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def select_backend(spec: BackendSpec) -> LLMBackend:
    """Instantiate a backend from a spec.

    Raises
    ------
    BackendUnavailable
        If the requested backend cannot be constructed on this host
        (e.g. MLX requested without ``mlx`` installed).
    """
    if spec.name == "stub":
        return StubBackend(spec)
    if spec.name == "cpu":
        return CPUBackend(spec)
    if spec.name == "mlx":
        try:
            from core.backends.mlx_backend import MLXBackend
        except BackendUnavailable:
            raise
        except Exception as exc:  # pragma: no cover — defensive
            raise BackendUnavailable(f"failed to import mlx backend: {exc}") from exc
        return MLXBackend(spec)
    if spec.name == "torch":
        # Placeholder — torch path is a stub until the port lands.
        raise BackendUnavailable(
            "torch backend is a placeholder; not wired yet."
        )
    # Should be unreachable thanks to BackendSpec validation.
    raise BackendUnavailable(f"unknown backend: {spec.name}")


__all__ = [
    "BackendName",
    "BackendSpec",
    "BackendUnavailable",
    "CPUBackend",
    "LLMBackend",
    "StubBackend",
    "select_backend",
]
