"""Benchmark harness for ai-chan LLM backends.

Runs a fixed set of prompts through one or more backends and records
throughput, latency percentiles, and peak memory usage. Results are
written to ``artifacts/bench/llm_backends_<date>.json`` for
comparison across machines (e.g. current Intel dev box vs the
upcoming Apple Silicon production host).

Usage
-----
    python scripts/bench_llm_backends.py                  # auto-detect
    python scripts/bench_llm_backends.py --backends stub cpu
    python scripts/bench_llm_backends.py --backends mlx

If MLX is not available the ``mlx`` target is silently skipped —
the script is designed to work unchanged on any host.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.llm_backend import (  # noqa: E402
    BackendSpec,
    BackendUnavailable,
    select_backend,
)

log = logging.getLogger("bench_llm_backends")

_PROMPTS: List[str] = [
    "今日の天気はどうですか？",
    "桜の季節が近づいてきました。",
    "日本の首都は",
    "Explain quantum entanglement in one sentence.",
    "おはよう、今日の予定は？",
]

_DEFAULT_MAX_TOKENS = 32


# ---------------------------------------------------------------------------
# Memory measurement helpers
# ---------------------------------------------------------------------------


def _peak_memory_mb() -> Optional[float]:
    """Best-effort peak RSS in MB. Returns None if unavailable."""
    try:
        import psutil  # type: ignore

        rss = psutil.Process().memory_info().rss
        return rss / (1024.0 * 1024.0)
    except ImportError:
        pass
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is KB on Linux, bytes on macOS. Normalize to MB.
        maxrss = ru.ru_maxrss
        if sys.platform == "darwin":
            return maxrss / (1024.0 * 1024.0)
        return maxrss / 1024.0
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Backend construction
# ---------------------------------------------------------------------------


def _build_spec(name: str) -> BackendSpec:
    if name == "mlx":
        return BackendSpec(
            name="mlx",
            device_hint="metal",
            precision="fp16",
            notes="bench",
        )
    if name == "cpu":
        return BackendSpec(
            name="cpu", device_hint="cpu", precision="fp32", notes="bench"
        )
    if name == "stub":
        return BackendSpec(
            name="stub", device_hint="stub", precision="fp32", notes="bench"
        )
    raise ValueError(f"unknown backend name: {name}")


# ---------------------------------------------------------------------------
# Bench loop
# ---------------------------------------------------------------------------


def run_backend(name: str, max_tokens: int) -> Dict[str, object]:
    spec = _build_spec(name)
    try:
        backend = select_backend(spec)
    except BackendUnavailable as exc:
        log.warning("backend %s unavailable: %s", name, exc)
        return {
            "backend": name,
            "available": False,
            "reason": str(exc),
        }

    latencies_s: List[float] = []
    total_chars = 0
    outputs: List[str] = []

    mem_before = _peak_memory_mb()
    wall_start = time.perf_counter()
    for prompt in _PROMPTS:
        t0 = time.perf_counter()
        out = backend.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=0.0,
            top_p=1.0,
            seed=42,
        )
        dt = time.perf_counter() - t0
        latencies_s.append(dt)
        outputs.append(out)
        total_chars += len(out)
    wall_total = time.perf_counter() - wall_start
    mem_after = _peak_memory_mb()

    # Rough tokens/sec estimate: ~1 token per ~3 chars is a coarse
    # proxy that lets us compare backends on the same host even
    # without a shared tokenizer.
    est_tokens = max(1, total_chars // 3)
    tps = est_tokens / wall_total if wall_total > 0 else 0.0

    def _pct(p: float) -> float:
        if not latencies_s:
            return 0.0
        sorted_l = sorted(latencies_s)
        idx = min(len(sorted_l) - 1, int(round(p * (len(sorted_l) - 1))))
        return sorted_l[idx]

    return {
        "backend": name,
        "available": True,
        "device_hint": spec.device_hint,
        "prompts": len(_PROMPTS),
        "max_tokens": max_tokens,
        "wall_seconds": round(wall_total, 6),
        "est_tokens_per_sec": round(tps, 3),
        "latency_p50_ms": round(statistics.median(latencies_s) * 1000.0, 3),
        "latency_p95_ms": round(_pct(0.95) * 1000.0, 3),
        "latency_mean_ms": round(
            (sum(latencies_s) / len(latencies_s)) * 1000.0, 3
        ),
        "mem_before_mb": mem_before,
        "mem_after_mb": mem_after,
        "sample_outputs": outputs[:2],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backends",
        nargs="+",
        default=["stub", "cpu", "mlx"],
        help="Backends to benchmark (default: stub cpu mlx)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=_DEFAULT_MAX_TOKENS
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_REPO_ROOT / "artifacts" / "bench",
        help="Output directory for the JSON results file.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s"
    )

    results: List[Dict[str, object]] = []
    for name in args.backends:
        log.info("benchmarking backend=%s", name)
        try:
            results.append(run_backend(name, args.max_tokens))
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("backend %s crashed", name)
            results.append(
                {"backend": name, "available": False, "reason": f"crash: {exc}"}
            )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.date.today().isoformat()
    out_path = args.out_dir / f"llm_backends_{stamp}.json"
    payload = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "host_platform": sys.platform,
        "python": sys.version.split()[0],
        "mlx_model_path_env": os.environ.get("AICHAN_MLX_MODEL_PATH"),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    log.info("wrote %s", out_path)

    # Print a compact summary to stdout for CI scraping.
    for r in results:
        if r.get("available"):
            log.info(
                "  %-5s  tps=%s  p50=%sms  p95=%sms",
                r["backend"],
                r.get("est_tokens_per_sec"),
                r.get("latency_p50_ms"),
                r.get("latency_p95_ms"),
            )
        else:
            log.info("  %-5s  unavailable: %s", r["backend"], r.get("reason"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
