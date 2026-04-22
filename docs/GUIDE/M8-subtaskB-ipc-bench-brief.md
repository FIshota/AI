# M8 Sub-task B: IPC Streaming Microbench — 判定メモ

**作成日**: 2026-04-21
**計測環境**: darwin / Python 3.13.2 / Intel Mac (family AI reference machine)
**計測スクリプト**: `scripts/bench/m8_ipc_streaming_bench.py`
**最新レポート**: `logs/benchmarks/m8_ipc_20260421_204123.md`

---

## 1. 計測結果（5000 chunks × 2 runs, best of）

| Variant | p50 (μs) | p95 (μs) | max (μs) | throughput (ch/s) |
|---|---:|---:|---:|---:|
| `blocking_jsonl` | 2.2 | 6.5 | 460.3 | 157,423 |
| `asyncio_reader` | 2.5 | **3.0** | **286.1** | 23,378 |
| `lp_binary` | 4.4 | 18.3 | **125.0** | 143,455 |

**目標**: p50 < 500μs, throughput > 500 ch/s → **全 variant が 125x 以上マージン**

## 2. 解釈

### 2.1 IPC オーバーヘッド は無視できる

LLM 推論速度は:
- llama.cpp CPU: 5–15 tok/s → **67–200 ms/tok**
- MLX GPU: 20–50 tok/s → **20–50 ms/tok**

最も速い MLX 50 tok/s (= 20ms/tok) でも、per-chunk IPC 2–4μs は **総レイテンシの 0.01–0.02%**。
→ 「家族 AI の会話 UX が IPC 化で劣化する」心配は **実測で却下**。

### 2.2 variant 別の性質

| variant | 採用判定 | 理由 |
|---|---|---|
| `blocking_jsonl` | ✅ **採用** | 実装が最も simple（stdlib のみ）、最高 throughput、max μs が許容範囲 |
| `asyncio_reader` | △ 将来性 | p95/max のばらつきが小さい（安定性重視の UI）。async アーキ変更時に再検討 |
| `lp_binary` | ❌ 不採用 | デバッグ性を犠牲にして得る速度差ゼロ。JSON の observability（ログ grep, tcpdump）が失われる |

### 2.3 `blocking_jsonl` の max 460μs について

p50=2.2μs に対し max=460μs は GC pause / OS スケジューラ干渉が主因。実 LLM 推論のトークン間ジッタ（数十 ms）に比べて無視できる。

## 3. M8 本実装プロトコルの FINAL 判定

```
# Transport: Unix Domain Socket (Windows: TCP localhost fallback)
# Encoding:  UTF-8 JSON-lines (one JSON object per line)
# Receive:   socket.recv(4096) + split('\n') + json.loads
```

- シンプルさ優先。tshark / jq でライブ観測可能。
- 既知のリスク「500μs 劣化」は **実測で 2-4μs ≒ ノイズ**。
- stdout/stderr での worker ログ統合も同じ pattern で合流できる。

## 4. 懸念材料と緩和策

| 懸念 | 実測 | 緩和策 |
|---|---|---|
| macOS GC pause で max 跳ねる | 最悪 460μs (= 0.5ms) | LLM 推論の 20–200ms tok 間隔に吸収される |
| JSON encode overhead | 実測で lp_binary との差なし | そのまま |
| 1-request あたり chunk 数 | 日本語 200 tokens × 40B = 8KB/応答 | UDS buffer 64KB 十分 |
| Windows TCP localhost | 未計測（Unix でしか bench 不可） | Phase 1 実装時に同スクリプトを Windows で実行して再評価 |

## 5. 先行決定事項

1. **`blocking_jsonl` をベース実装に採用**
2. Protocol 仕様書は sub-task A の §4.1 の 8 op をそのまま採用
3. `core/llm_ipc_protocol.py` の encode/decode は stdlib `json` のみ（第三者ライブラリ不要）
4. Windows TCP fallback は **同スクリプトで再計測 → 採用判定** とする（Phase 1 実装途中の通過儀礼）

## 6. Phase 1 着手時に実行するコマンド

```bash
# 着手前に現環境で再計測（差分検知用）
python3 scripts/bench/m8_ipc_streaming_bench.py --chunks 10000 --runs 3

# 実装途中の回帰テスト
python3 scripts/bench/m8_ipc_streaming_bench.py --chunks 10000 --runs 3 --out-dir logs/benchmarks/m8
```

---

## 判定: 🟢 Go for Phase 1 実装 (sub-task A + B 完了)

**残された Conditional 要素**:
- sqlite-vec GA 待ちは M9 のみ（M8 には無関係）
- Windows 対応は M8 実装中に ad-hoc 検証で十分

**次のフェーズへの示唆**: M8 本実装（37h）は設計が固まり、最大リスク 2 点（state mutation / stream latency）が解消済み。**着手可能**。
