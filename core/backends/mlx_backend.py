"""MLX (Apple Silicon) LLM backend.

This is a *skeleton* implementation:

* When ``mlx`` / ``mlx_lm`` are importable it wires up a generation
  pathway using the real library.
* Without those modules, importing this file raises
  :class:`core.llm_backend.BackendUnavailable` (not ``ImportError``)
  so callers do not have to special-case missing optional deps.
* The model itself is expected to live at a path supplied via the
  spec ``extra`` (key ``mlx_model_path``) or via the
  ``AICHAN_MLX_MODEL_PATH`` environment variable. If neither is set,
  the backend falls back to a deterministic in-memory dummy model so
  that smoke tests and the bench harness still have a generation path.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import List, Optional

from core.llm_backend import BackendSpec, BackendUnavailable

log = logging.getLogger(__name__)

try:
    import mlx.core as _mx  # type: ignore  # noqa: F401
    _MLX_CORE_AVAILABLE = True
except ImportError as _e:  # pragma: no cover — hardware dependent
    _MLX_CORE_AVAILABLE = False
    _MLX_IMPORT_ERROR = _e
else:
    _MLX_IMPORT_ERROR = None

try:
    from mlx_lm import generate as _mlx_generate  # type: ignore
    from mlx_lm import load as _mlx_load  # type: ignore
    _MLX_LM_AVAILABLE = True
except ImportError:  # pragma: no cover — hardware dependent
    _MLX_LM_AVAILABLE = False


if not _MLX_CORE_AVAILABLE:
    # Converting module-import failure into BackendUnavailable lets
    # ``select_backend("mlx")`` surface a uniform error type.
    raise BackendUnavailable(
        f"mlx is not importable on this host: {_MLX_IMPORT_ERROR!r}"
    )


_MODEL_PATH_ENV = "AICHAN_MLX_MODEL_PATH"
_MODEL_PATH_EXTRA_KEY = "mlx_model_path"


class _DummyMLXModel:
    """Deterministic in-memory model used when no real checkpoint is set.

    Keeps the generation path exercised without touching disk.
    """

    def generate(self, prompt: str, max_tokens: int, seed: Optional[int]) -> str:
        # Use MLX device string in the output so bench logs can confirm
        # that the call really went through the MLX path.
        device = str(_mx.default_device())
        # A trivially derived output — stable for identical inputs.
        body_len = max(4, min(max_tokens, 32))
        body = f"dummy-{abs(hash((prompt, seed or 0))) % (10 ** 8):08d}"
        return f"[mlx:{device}] {body[:body_len + 14]}"


class MLXBackend:
    """LLM backend that runs on Apple's MLX framework.

    The backend is thread-safe for the ``generate`` entry point. A
    lock guards the underlying model because ``mlx_lm.generate`` is
    not guaranteed to be safe under concurrent access.
    """

    name = "mlx"

    def __init__(self, spec: BackendSpec) -> None:
        self.spec = spec
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._using_dummy = False
        self._model_path = self._resolve_model_path(spec)
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_model_path(spec: BackendSpec) -> Optional[str]:
        extras = spec.extras_dict()
        if _MODEL_PATH_EXTRA_KEY in extras and extras[_MODEL_PATH_EXTRA_KEY]:
            return str(extras[_MODEL_PATH_EXTRA_KEY])
        env_val = os.environ.get(_MODEL_PATH_ENV)
        if env_val:
            return env_val
        return None

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self._model_path and _MLX_LM_AVAILABLE:
                try:
                    log.info("[MLXBackend] loading model from %s", self._model_path)
                    self._model, self._tokenizer = _mlx_load(self._model_path)
                    self._using_dummy = False
                except Exception as exc:
                    log.warning(
                        "[MLXBackend] real model load failed (%s); "
                        "falling back to dummy model",
                        exc,
                    )
                    self._model = _DummyMLXModel()
                    self._using_dummy = True
            else:
                if not _MLX_LM_AVAILABLE:
                    log.info(
                        "[MLXBackend] mlx_lm not installed — using dummy model"
                    )
                else:
                    log.info(
                        "[MLXBackend] no model path configured "
                        "(extra %s / env %s) — using dummy model",
                        _MODEL_PATH_EXTRA_KEY,
                        _MODEL_PATH_ENV,
                    )
                self._model = _DummyMLXModel()
                self._using_dummy = True
            self._loaded = True

    # ------------------------------------------------------------------
    # Public API (matches LLMBackend protocol)
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        max_tokens: int = 64,
        temperature: float = 0.0,
        top_p: float = 1.0,
        seed: Optional[int] = None,
    ) -> str:
        self._ensure_loaded()
        if self._using_dummy:
            assert isinstance(self._model, _DummyMLXModel)
            # Small sleep ensures bench latency numbers are measurable
            # even on the dummy path (<1ms is noise).
            time.sleep(0.0)
            return self._model.generate(prompt, max_tokens, seed)

        # Real path
        with self._lock:
            text = _mlx_generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                verbose=False,
            )
        return str(text)

    def logprobs(self, prompt: str) -> List[float]:
        # Skeleton: real implementation would call into mlx to score
        # per-token log-probabilities. For now we return a stable,
        # deterministic placeholder derived from the prompt length so
        # the protocol is satisfied.
        self._ensure_loaded()
        n = max(1, min(len(prompt), 16))
        return [-(i + 1) / 16.0 for i in range(n)]

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def device_label(self) -> str:
        return str(_mx.default_device())

    def is_using_dummy(self) -> bool:
        self._ensure_loaded()
        return self._using_dummy


__all__ = ["MLXBackend"]
