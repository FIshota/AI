# M8 Phase 1 実装レポート

**作成日**: 2026-04-21
**ステータス**: ✅ Phase 1 完了（opt-in、未配線）
**テスト**: 967 passed / 2 skipped（既存 944 + 新規 23）

---

## 1. 完了スコープ

新規モジュール 3 本 + テスト 1 本 + 先行ドキュメント 3 本。**既存 `core/llm.py` には無改修**。

| ファイル | 行 | 役割 |
|---|---:|---|
| `core/llm_ipc_protocol.py` | 173 | JSON-lines frame codec, op/kind 定数, `LineReader`, `WorkerError` |
| `scripts/ai_chan_llm_worker.py` | 254 | UDS server, `LLMEngine` を in-process で保持、request dispatch |
| `core/llm_proxy.py` | 331 | client proxy, `LLMEngine` 互換 public API, subprocess 管理, stream 対応 |
| `tests/test_llm_ipc.py` | 264 | 23 tests: codec unit, LineReader, 実 subprocess を起動した end-to-end |

**補助成果物**:
- `docs/GUIDE/M8-subtaskA-llm-state-inventory.md` — state-mutation 棚卸し
- `docs/GUIDE/M8-subtaskB-ipc-bench-brief.md` — ベンチ判定
- `scripts/bench/m8_ipc_streaming_bench.py` — 回帰用 microbench
- `logs/benchmarks/m8_ipc_*.md` — 実測ログ

## 2. アーキテクチャ

```
┌─────────────────────┐         UDS: $XDG_RUNTIME_DIR/ai-chan/llm-XXXX.sock
│  ai-chan (client)   │  ◀──────────── JSON-lines ────────────▶
│  core.llm_proxy     │                                          ai_chan_llm_worker
│  LLMProxy           │  (8 ops, correlation id, stream chunks)  │
└─────────────────────┘                                          │
                                                                 ▼
                                                         ┌──────────────┐
                                                         │ core.llm.    │
                                                         │ LLMEngine    │
                                                         │ (llama.cpp/  │
                                                         │  MLX)        │
                                                         └──────────────┘
```

### 2.1 プロトコル

- **Transport**: Unix Domain Socket (SOCK_STREAM, 0o600 permissions)
- **Encoding**: UTF-8 JSON-lines, 1 frame = 1 行
- **Correlation**: UUID4 hex per request, response frames carry matching `id`
- **Version**: `PROTOCOL_VERSION = 1`, handshake で version check
- **Max frame**: 8 MB (大きな memory_context でも余裕)

### 2.2 Operations (8)

| op | mode | 戻り |
|---|---|---|
| `init` | handshake | `ready {backend, model_name}` or `error` |
| `is_loaded` | sync | `result: bool` |
| `get_backend` | sync | `result: str` |
| `get_stats` | sync | `result: dict` |
| `generate` | sync or stream | `result: str` or `chunk...end` |
| `generate_chat` | sync or stream | `result: str` or `chunk...end`（`params_override` 引数に `override_params` 吸収） |
| `generate_with_confidence` | sync | `result: {text, confidence}` |
| `shutdown` | sync | `result: true` |

### 2.3 M8-A の設計判断が反映されている箇所

1. **`params_override` の合成オペ化** (`llm_proxy.py:302`)
   - `override_params` / `restore_params` は client-side でスタッシュのみ
   - 実際の適用は `generate_chat` の `params_override` 引数として 1 往復で atomic に
   - worker 側は `try/finally` で確実に restore される

2. **`build_prompt` の client-side 実行** (`llm_proxy.py:335`)
   - IPC 跨ぎなし。system_prompt + memory_context の重複送信を回避

3. **Single-lock 直列化** (`llm_proxy.py:86`)
   - `self._lock = threading.Lock()` で 1 リクエスト同時実行に制限
   - `LLMEngine._inference_lock` と同じセマンティクス

## 3. 未配線（Phase 1 では意図的に未実施）

### 3.1 `core.ai_chan` への統合
- `AiChan.__init__` 内で `settings.get("llm_ipc_enabled", False)` を見て `LLMEngine` vs `LLMProxy` を切り替えるコードは**未追加**
- 理由: 944 件既存テストへの影響をゼロに保ち、Phase 1 の粒度を「IPC スタック完成」に限定するため
- 次フェーズ（Phase 1.5 相当）で配線 + opt-in リリース

### 3.2 Watchdog / Auto-restart
- worker クラッシュ時の自動再起動ロジックは未実装
- Phase 2 で `LLMProxy` 内部に circuit breaker と 3-回再起動ポリシーを追加予定

### 3.3 Windows TCP fallback
- 現状 `AF_UNIX` のみ対応。Windows で動作しない
- Phase 2 で `socket_type` を設定から選べるようにし、TCP localhost + token 認証を追加

### 3.4 UI 統合
- 「LLM worker を再起動」ボタン等の UI は未整備
- Phase 2 で settings_window に追加

## 4. 使い方（現時点での動作確認方法）

```python
from pathlib import Path
from core.llm_proxy import LLMProxy

with LLMProxy(
    model_path=Path("/path/to/model.gguf"),
    config={"n_ctx": 4096, "n_threads": 4},
) as llm:
    # LLMEngine と同じ API
    print(llm.get_backend())          # "llama" or "mlx"
    print(llm.is_loaded())            # True
    # 非ストリーム
    text = llm.generate_chat([
        {"role": "user", "content": "こんにちは"},
    ])
    # ストリーム（callback）
    llm.generate_chat(
        [{"role": "user", "content": "長めに返して"}],
        stream_cb=lambda tok: print(tok, end="", flush=True),
    )
```

## 5. テスト設計

`tests/test_llm_ipc.py`:
- **Unit (14 tests)**: frame codec / request constructors / `LineReader`
- **End-to-end (9 tests)**: 実 subprocess (`python3 -m scripts.ai_chan_llm_worker`) を起動し、fake `core.llm` を inject して全 op を roundtrip

**フェイク注入の仕組み**:
- `tests/support/fake_core_llm.py` — 軽量 stub LLMEngine
- `tests/support/run_fake_worker.py` — `sys.modules["core.llm"] = fake_core_llm` してから worker を起動
- これにより実モデルをロードせずに worker の全経路をカバー

## 6. 残作業（Phase 2）

| # | 項目 | 見積 |
|---|---|---:|
| 1 | `AiChan.__init__` で `settings["llm_ipc_enabled"]` に応じて切替 | 2h |
| 2 | Watchdog thread + circuit breaker（3 回失敗で TF-IDF 縮退） | 4h |
| 3 | Windows TCP fallback + auth token | 4h |
| 4 | UI: settings_window に worker status / restart ボタン | 3h |
| 5 | logs/llm_worker.jsonl 統合ロガー | 1h |
| 6 | crash injection 統合テスト（Phase 1 未カバー） | 3h |
| **計** |  | **17h** |

→ Phase 1 で先行実装した 3 モジュールの**上に積むだけ**なので、残 17h で M8 完全完了できる見込み。

---

## 判定: 🟢 Phase 1 Done — Ready for opt-in Phase 2

- 967 tests green / 既存挙動変化ゼロ
- IPC スタックは単独で動作検証済（実 subprocess + roundtrip）
- `LLMEngine` 互換 API なので ai-chan 側の変更は 1 箇所（engine 生成部）で済む見込み
