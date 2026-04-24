# LLM Backends

## Background

ai-chan's text generation runs on different hardware depending on the
environment:

| Environment            | Preferred backend | Reason                                          |
|------------------------|-------------------|-------------------------------------------------|
| CI / unit tests        | `stub`            | deterministic, no optional deps                 |
| Portable dev box       | `cpu`             | works anywhere, no accelerator required         |
| Apple Silicon (prod)   | `mlx`             | uses Metal / Neural Engine via `mlx` + `mlx_lm` |
| Future CUDA host       | `torch` (planned) | reserved; currently a placeholder               |

The target production machine (M2 Pro) has `mlx 0.31.1`, `mlx-lm`, and
`mlx-metal` installed — MLX is available as a *first-class* backend,
not an optional add-on. The current dev box (Intel Mac) cannot run
MLX, so the abstraction layer must always fall back cleanly.

## Module map

```
core/
  llm_backend.py              # BackendSpec, LLMBackend, select_backend,
                              # StubBackend, CPUBackend
  backends/
    __init__.py
    mlx_backend.py            # MLXBackend; raises BackendUnavailable if mlx missing
  hinomoto_bridge.py          # accepts optional backend=BackendSpec(...)
scripts/
  bench_llm_backends.py       # tokens/sec, P50/P95 latency, peak RSS
tests/
  test_llm_backend.py         # 11 cases, incl. MLX conditional
docs/design/
  LLM_BACKENDS.md             # this file
```

## How to pick a backend

```python
from core.llm_backend import BackendSpec, select_backend

spec = BackendSpec(
    name="mlx",
    device_hint="metal",
    precision="fp16",
    notes="prod",
    extra=(("mlx_model_path", "/path/to/mlx/model"),),
)
backend = select_backend(spec)
reply = backend.generate("こんにちは", max_tokens=64, seed=42)
```

If the requested backend cannot be constructed on this host,
`select_backend` raises `BackendUnavailable`. Callers that want a
graceful fallback should catch it and retry with `name="cpu"` or
`name="stub"`.

## Configuring the MLX model path

The MLX backend looks up its model in this order:

1. `BackendSpec.extra` key `mlx_model_path`
2. Environment variable `AICHAN_MLX_MODEL_PATH`
3. A deterministic in-memory dummy model (smoke-test only)

This means the skeleton works end-to-end on any Apple Silicon box,
even before the real checkpoint has been copied over — useful for
wiring work and for reproducing the bench layout.

## Adding a new backend

1. Add the literal to `BackendSpec._VALID_NAMES` in `core/llm_backend.py`.
2. Create `core/backends/<name>_backend.py` that:
   - raises `BackendUnavailable` at import time if deps are missing
   - exposes a class matching the `LLMBackend` protocol
3. Wire it into `select_backend`.
4. Add cases to `tests/test_llm_backend.py` (at least: available path,
   unavailable path, and a thread-safety smoke test).
5. Add the backend to the default list in `scripts/bench_llm_backends.py`.

## Reading the bench output

`scripts/bench_llm_backends.py` writes JSON to
`artifacts/bench/llm_backends_<date>.json`:

```json
{
  "generated_at": "...",
  "host_platform": "darwin",
  "results": [
    {
      "backend": "cpu",
      "available": true,
      "est_tokens_per_sec": ...,
      "latency_p50_ms": ...,
      "latency_p95_ms": ...,
      "mem_before_mb": ...,
      "mem_after_mb": ...
    },
    { "backend": "mlx", "available": true, ... }
  ]
}
```

Fields to watch during the Intel → Apple Silicon migration:

- `est_tokens_per_sec`: higher is better; expect `mlx` > `cpu` ≥ `stub`
  once a real model is loaded.
- `latency_p95_ms`: tail latency — MLX cold-start includes model load
  on the first request; re-run the bench twice and report the second
  run for steady-state numbers.
- `mem_after_mb`: sanity-check that MLX doesn't duplicate the model
  in both host RAM and VRAM on a unified-memory device.

## Non-goals (this skeleton)

- Real MLX generation with a production checkpoint (deferred until
  the model move lands on the Apple Silicon host).
- Token-level log-probabilities on MLX (`logprobs` returns a
  deterministic placeholder).
- A `torch` implementation — it is intentionally a stub that fails
  loudly so the surface is visible without pulling in a large dep.
