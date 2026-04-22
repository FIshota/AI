# M8 Phase 2 実装レポート

**作成日**: 2026-04-21
**ステータス**: ✅ Phase 2 完了（opt-in 配線 + watchdog + ロガー + crash テスト）
**テスト**: 972 passed / 2 skipped（Phase 1 の 967 + 新規 5 crash-injection）

---

## 1. 完了スコープ

Phase 1 で先行実装した 3 モジュール（`core/llm_ipc_protocol.py`、`scripts/ai_chan_llm_worker.py`、`core/llm_proxy.py`）の**上に積んだ** 5 項目。

| # | 項目 | ファイル | 役割 |
|---|---|---|---|
| 2.1 | AiChan 統合 | `core/ai_chan.py` | `settings["llm_ipc_enabled"]` に応じて `LLMEngine` vs `LLMProxy` を切替。起動失敗時は in-process にフォールバック。`shutdown()` で worker 終了 |
| 2.2 | Watchdog + circuit breaker | `core/llm_proxy.py` | 3 回連続失敗で circuit OPEN、以降 `LLMProxyError` で fail-fast。`max_restarts=2` で worker 自動再起動。`reset_circuit()` で手動復旧 |
| 2.3 | JSONL 統合ロガー | `core/llm_worker_logger.py` (NEW, 92 行) | `logs/llm_worker.jsonl` へ append-only イベント書き出し。9 種類の evt (start/ready/request/success/failure/restart/circuit_open/circuit_reset/shutdown) |
| 2.4 | Crash injection tests | `tests/test_llm_ipc_crash.py` (NEW, 138 行) + `tests/support/crashing_core_llm.py` + `tests/support/run_crashing_worker.py` | 5 tests: circuit open 閾値、reset_circuit、auto-restart、restart budget、logger 初期化 |
| 2.5 | 設定・ドキュメント | `config/settings.json.example` | `"llm_ipc_enabled": false` デフォルト + コメント |

## 2. 既存ファイル変更

| ファイル | 変更 | 目的 |
|---|---|---|
| `core/ai_chan.py` | +23 行 / -2 行 | `_init_core`: LLMProxy 生成分岐、`shutdown()`: worker close 処理 |
| `core/llm_proxy.py` | +120 行 | watchdog メソッド群、`_call_sync_locked` / `_call_stream_locked` 分離、logger 配線 |

## 3. アーキテクチャ変更点

### 3.1 AiChan.__init__ の LLM 生成フロー
```
                        ┌──────────────────────────┐
                        │ self._deps.llm is not    │
                        │ None?                    │
                        └────────────┬─────────────┘
                            yes ──▶ self.llm = deps.llm
                            no  │
                                ▼
                        ┌──────────────────────────┐
                        │ settings.llm_ipc_enabled │
                        │ == True?                 │
                        └────────────┬─────────────┘
                            no  ──▶ LLMEngine(...) (in-process)
                            yes │
                                ▼
                        ┌──────────────────────────┐
                        │ LLMProxy(...).start()    │
                        │ - spawns worker          │
                        │ - handshake              │
                        └────────────┬─────────────┘
                            ok  ──▶ self.llm = proxy
                            fail ─▶ LLMEngine(...) (fallback + warning)
```

### 3.2 リクエスト実行フロー (watchdog 内蔵)
```
client.generate_chat(msgs)
  │
  ├─ _check_circuit() ──▶ raise LLMProxyError if open
  ├─ with self._lock:
  │     ├─ _call_sync_locked(op, ...)  ◀─── success path
  │     │     └─ _note_success()
  │     └─ on error:
  │           ├─ _note_failure(reason)
  │           ├─ WorkerError → 即座に raise（worker は生存）
  │           └─ LLMProxyError/ProtocolError/OSError:
  │                 ├─ _try_restart() if budget > 0
  │                 ├─ retry _call_sync_locked()
  │                 └─ on 2nd failure: raise
  │
  └─ after _circuit_threshold (=3) consecutive failures:
        └─ _circuit_open = True → fail-fast mode
```

### 3.3 JSONL イベントログ (`logs/llm_worker.jsonl`)
```jsonl
{"ts":"2026-04-21T21:00:30+09:00","evt":"start","pid":28365,"socket":"/tmp/ai-chan/llm-abc.sock","worker":"scripts.ai_chan_llm_worker"}
{"ts":"2026-04-21T21:00:32+09:00","evt":"ready","pid":28365,"backend":"llama","model":"qwen2.5-3b","worker_pid":28366}
{"ts":"2026-04-21T21:00:45+09:00","evt":"success","pid":28365}
{"ts":"2026-04-21T21:03:12+09:00","evt":"failure","pid":28365,"reason":"","consecutive_failures":1}
{"ts":"2026-04-21T21:03:12+09:00","evt":"restart","pid":28365,"attempt":1,"max_restarts":2}
{"ts":"2026-04-21T21:08:00+09:00","evt":"shutdown","pid":28365,"restart_count":1,"circuit_open":false,"consecutive_failures":0}
```

## 4. 有効化手順

**デフォルトは OFF**（既存挙動に影響なし）。有効化するには `config/settings.json` に追加：

```json
{
  "llm_ipc_enabled": true
}
```

次回起動時に worker subprocess が立ち上がり、`logs/llm_worker.jsonl` にイベントが記録されます。

## 5. 残作業（Phase 2 スコープ外）

| # | 項目 | 見積 | 備考 |
|---|---|---:|---|
| A | Windows TCP fallback + auth token | 4h | 現状 `AF_UNIX` のみ。POSIX 環境では不要 |
| B | UI: settings_window に worker status / restart ボタン | 3h | `circuit_status()` / `reset_circuit()` は API 準備済み |

Windows 対応と UI は今回のユーザー環境 (Intel Mac) では不要、または別イテレーションで十分と判断し後回し。

## 6. テスト結果

| Suite | passed | skipped | failed |
|---|---:|---:|---:|
| Phase 1 既存 | 967 | 2 | 0 |
| Phase 2 新規 (crash inject) | 5 | 0 | 0 |
| **合計** | **972** | **2** | **0** |

## 判定: 🟢 Phase 2 Done — M8 本線完了

- IPC 分離が opt-in で配線済み
- クラッシュ耐性（auto-restart + circuit breaker）確認済み
- 監査可能なイベントログ出力
- 既存挙動ゼロ変化
- 972 tests green
