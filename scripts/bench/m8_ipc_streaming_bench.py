"""M8 Sub-task B: IPC streaming microbench PoC.

3 つのプロトコル実装でトークン相当のチャンクを送受信し、
per-chunk レイテンシと throughput を比較する。

Variants:
  1. blocking_jsonl  — socket.recv + JSON-lines (naive synchronous)
  2. asyncio_reader  — asyncio.StreamReader.readline()
  3. lp_binary       — 4-byte length-prefixed binary frame (raw bytes, no JSON)

Target: per-chunk < 500μs, throughput > 500 chunks/s on Intel Mac.

Usage:
    python3 scripts/bench/m8_ipc_streaming_bench.py [--chunks N] [--chunk-size B]

Output: markdown table printed to stdout, also saved to
logs/benchmarks/m8_ipc_YYYYMMDD_HHMMSS.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import statistics
import struct
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path


# ──────────────────────────────────────────────────────────
# Sample chunks (Japanese tokens, ~3 bytes UTF-8 each)
# ──────────────────────────────────────────────────────────
_SAMPLE_TOKENS = [
    "こん", "にち", "は", "、", "今日", "は", "いい", "お", "天気", "です", "ね",
    "。", "何か", "お", "手伝い", "できる", "こと", "は", "あり", "ます", "か",
    "？", "お", "話し", "聞か", "せて", "くだ", "さい", "ね", "。", "えへへ",
]


def _make_chunks(n: int) -> list[str]:
    """n 個のチャンク（平均 3-4 bytes UTF-8）を生成。"""
    return [_SAMPLE_TOKENS[i % len(_SAMPLE_TOKENS)] for i in range(n)]


# ──────────────────────────────────────────────────────────
# Variant 1: blocking socket + JSON-lines
# ──────────────────────────────────────────────────────────
def bench_blocking_jsonl(chunks: list[str]) -> tuple[float, list[float]]:
    """Variant 1: 同期 socket + JSON-lines."""
    sock_dir = tempfile.mkdtemp(prefix="m8bench_")
    sock_path = os.path.join(sock_dir, "v1.sock")

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)

    per_chunk_us: list[float] = []

    def _producer():
        srv.settimeout(5.0)
        conn, _ = srv.accept()
        for i, tok in enumerate(chunks):
            line = json.dumps({"id": "b1", "kind": "chunk", "token": tok, "idx": i}) + "\n"
            conn.sendall(line.encode("utf-8"))
        conn.sendall(json.dumps({"id": "b1", "kind": "end"}).encode("utf-8") + b"\n")
        conn.close()

    t = threading.Thread(target=_producer, daemon=True)
    t.start()

    cli = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    cli.connect(sock_path)
    buf = b""
    received = 0
    start = time.perf_counter()
    last = start
    while True:
        data = cli.recv(4096)
        if not data:
            break
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line:
                continue
            obj = json.loads(line)
            now = time.perf_counter()
            if obj.get("kind") == "chunk":
                per_chunk_us.append((now - last) * 1_000_000)
                received += 1
                last = now
            elif obj.get("kind") == "end":
                total = now - start
                cli.close()
                srv.close()
                Path(sock_path).unlink(missing_ok=True)
                Path(sock_dir).rmdir()
                return total, per_chunk_us
    raise RuntimeError("stream ended without end frame")


# ──────────────────────────────────────────────────────────
# Variant 2: asyncio.StreamReader
# ──────────────────────────────────────────────────────────
async def _bench_asyncio_reader(chunks: list[str]) -> tuple[float, list[float]]:
    sock_dir = tempfile.mkdtemp(prefix="m8bench_")
    sock_path = os.path.join(sock_dir, "v2.sock")
    per_chunk_us: list[float] = []

    async def _handle(reader, writer):  # producer side
        for i, tok in enumerate(chunks):
            line = json.dumps({"id": "b2", "kind": "chunk", "token": tok, "idx": i}) + "\n"
            writer.write(line.encode("utf-8"))
        writer.write((json.dumps({"id": "b2", "kind": "end"}) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()

    srv = await asyncio.start_unix_server(_handle, path=sock_path)
    try:
        reader, writer = await asyncio.open_unix_connection(sock_path)
        start = time.perf_counter()
        last = start
        received = 0
        while True:
            line = await reader.readline()
            if not line:
                break
            obj = json.loads(line)
            now = time.perf_counter()
            if obj.get("kind") == "chunk":
                per_chunk_us.append((now - last) * 1_000_000)
                received += 1
                last = now
            elif obj.get("kind") == "end":
                total = now - start
                writer.close()
                return total, per_chunk_us
        raise RuntimeError("stream ended without end frame")
    finally:
        srv.close()
        await srv.wait_closed()
        Path(sock_path).unlink(missing_ok=True)
        Path(sock_dir).rmdir()


def bench_asyncio_reader(chunks: list[str]) -> tuple[float, list[float]]:
    return asyncio.run(_bench_asyncio_reader(chunks))


# ──────────────────────────────────────────────────────────
# Variant 3: length-prefixed binary frame (no JSON)
# ──────────────────────────────────────────────────────────
def bench_lp_binary(chunks: list[str]) -> tuple[float, list[float]]:
    """Variant 3: 4-byte length prefix + raw UTF-8 (JSON をバイパス)."""
    sock_dir = tempfile.mkdtemp(prefix="m8bench_")
    sock_path = os.path.join(sock_dir, "v3.sock")

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)

    per_chunk_us: list[float] = []

    def _producer():
        srv.settimeout(5.0)
        conn, _ = srv.accept()
        for tok in chunks:
            payload = tok.encode("utf-8")
            conn.sendall(struct.pack(">I", len(payload)) + payload)
        conn.sendall(struct.pack(">I", 0))  # 0-length = end
        conn.close()

    t = threading.Thread(target=_producer, daemon=True)
    t.start()

    cli = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    cli.connect(sock_path)
    start = time.perf_counter()
    last = start

    def _read_exact(n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            data = cli.recv(n - len(buf))
            if not data:
                raise RuntimeError("socket closed early")
            buf.extend(data)
        return bytes(buf)

    while True:
        length_bytes = _read_exact(4)
        (length,) = struct.unpack(">I", length_bytes)
        if length == 0:
            total = time.perf_counter() - start
            cli.close()
            srv.close()
            Path(sock_path).unlink(missing_ok=True)
            Path(sock_dir).rmdir()
            return total, per_chunk_us
        _ = _read_exact(length)
        now = time.perf_counter()
        per_chunk_us.append((now - last) * 1_000_000)
        last = now


# ──────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────
def _summarize(name: str, total_s: float, per_chunk_us: list[float]) -> dict:
    # skip the first chunk (includes connection accept overhead)
    samples = per_chunk_us[1:] if len(per_chunk_us) > 1 else per_chunk_us
    return {
        "name": name,
        "chunks": len(per_chunk_us),
        "total_ms": total_s * 1000,
        "throughput_per_s": len(per_chunk_us) / total_s if total_s else 0.0,
        "p50_us": statistics.median(samples) if samples else 0.0,
        "p95_us": (statistics.quantiles(samples, n=20)[18] if len(samples) >= 20 else max(samples, default=0.0)),
        "max_us": max(samples) if samples else 0.0,
        "mean_us": statistics.mean(samples) if samples else 0.0,
    }


def _format_markdown(results: list[dict], *, n_chunks: int) -> str:
    header = (
        f"# M8 Sub-task B: IPC Streaming Microbench\n\n"
        f"- Date: {datetime.now().isoformat(timespec='seconds')}\n"
        f"- Platform: {sys.platform}, Python {sys.version.split()[0]}\n"
        f"- Chunks per run: {n_chunks}\n"
        f"- Target: per-chunk p50 < 500μs, throughput > 500 chunks/s\n\n"
        f"## Results\n\n"
        f"| Variant | Chunks | Total (ms) | Throughput (ch/s) | p50 (μs) | p95 (μs) | max (μs) | mean (μs) |\n"
        f"|---|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    rows = []
    for r in results:
        rows.append(
            f"| {r['name']} | {r['chunks']} | {r['total_ms']:.2f} | "
            f"{r['throughput_per_s']:.0f} | {r['p50_us']:.1f} | {r['p95_us']:.1f} | "
            f"{r['max_us']:.1f} | {r['mean_us']:.1f} |"
        )
    verdict_lines = ["\n## Verdict\n"]
    for r in results:
        ok_p50 = r["p50_us"] < 500
        ok_thr = r["throughput_per_s"] > 500
        sym = "✅" if ok_p50 and ok_thr else ("⚠️" if ok_p50 or ok_thr else "❌")
        verdict_lines.append(
            f"- {sym} **{r['name']}**: p50={r['p50_us']:.1f}μs "
            f"(target <500), throughput={r['throughput_per_s']:.0f} ch/s (target >500)"
        )
    return header + "\n".join(rows) + "\n" + "\n".join(verdict_lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=int, default=10000, help="chunks per variant (default 10000)")
    parser.add_argument("--runs", type=int, default=3, help="repeat runs to reduce noise (default 3)")
    parser.add_argument("--out-dir", type=Path, default=Path("logs/benchmarks"))
    args = parser.parse_args()

    chunks = _make_chunks(args.chunks)
    variants = [
        ("blocking_jsonl", bench_blocking_jsonl),
        ("asyncio_reader", bench_asyncio_reader),
        ("lp_binary", bench_lp_binary),
    ]

    # warmup
    for _name, fn in variants:
        fn(_make_chunks(100))

    results = []
    for name, fn in variants:
        best_total: float | None = None
        best_samples: list[float] = []
        for _ in range(args.runs):
            total, samples = fn(chunks)
            if best_total is None or total < best_total:
                best_total = total
                best_samples = samples
        results.append(_summarize(name, best_total or 0.0, best_samples))

    md = _format_markdown(results, n_chunks=args.chunks)
    print(md)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"m8_ipc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\nReport saved: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
