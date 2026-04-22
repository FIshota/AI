# M8: LLM 別プロセス化 (IPC) 設計レポート

**作成日**: 2026-04-21
**ステータス**: Go / No-Go 判定レポート（実装未着手）
**判定**: **🟡 Conditional Go（M9 と並走可、ただし家族 AI 単機利用の範囲内なら優先度低）**

---

## 1. 目的 (Why)

現状 `core/llm.py`（1,263 行）は ai-chan プロセスに **in-process** で同居している。リスク:

1. **LLM クラッシュ = ai-chan 全体クラッシュ**: llama.cpp / MLX 内部の segfault（GGUF quantization 組合せでごく稀に発生）がデスクトップペット全体を落とす。会話・感情履歴・日記などの未保存 state が失われる。
2. **メモリ解放不能**: `Llama(...)` インスタンスは RAM 2–8 GB を保持し、`del` では解放されないことが多い（llama.cpp の mmap 仕様）。再ロード要件（モデル切替、設定変更時）で OOM リスク。
3. **GIL スループット競合**: LLM 推論スレッドが 100% 占有する間、感情計算・TTS・UI 応答など他のワーカーの応答性が劣化する場面がある（特に Intel Mac 低速機）。
4. **クラッシュレポート分離不能**: 現状 LLM 由来の stderr が ai-chan 本体ログに混ざり、家族利用時のトリアージが困難。

**対策**: LLM を別プロセス（`ai_chan_llm_worker`）に隔離し、**Unix Domain Socket + JSON lines プロトコル**で IPC する。

## 2. 現状調査

### 2.1 `core/llm.py` のサイズと API 表面積

- **ファイル**: 1,263 行, 43 メソッド/関数
- **公開 API**（`self.llm.*` で呼ばれているもの）:

| メソッド | 呼び出し箇所 | IPC 境界化の難度 |
|---|---|---|
| `generate(prompt, stream)` | core/ai_chan.py | ★☆☆ 低（純粋入出力） |
| `generate_chat(messages, stream, stream_cb)` | core/ai_chan.py（メインパス）, core/multimodal_chat.py | ★★☆ 中（stream_cb callback） |
| `build_prompt(system_prompt, conversation_history, memory_context, emotion_hint)` | core/ai_chan.py | ★☆☆ 低（純粋関数） |
| `is_loaded()` | 複数 | ★☆☆ 低 |
| `override_params(params)` / `restore_params(saved)` | core/ai_chan._apply_moe_routing | ★★☆ 中（状態付き） |
| `get_backend()`, `get_context_stats()` | settings UI | ★☆☆ 低 |

**合計 6 個の公開メソッド** が IPC 境界を通過する必要あり（想定以上に小さい）。

### 2.2 既存の import 依存

- `core/ai_chan.py`: `self.llm = LLMEngine(model_path, config)`（1 箇所）
- `core/multimodal_chat.py`: `self.llm.generate_chat(...)`（1 箇所）
- `ui/`: なし（settings_window は `ai_chan.llm.get_backend()` 経由）

→ **LLMEngine を Proxy に差し替えるだけで済む**構造は既に整っている。

### 2.3 現在の並行性

- chat() は同期呼び出し（blocking）
- stream_cb はトークン単位コールバック（E-05）
- `_batch_executor` は別スレッドで副作用処理

## 3. 設計案

### 3.1 プロセス構成

```
┌─────────────────────┐      UDS: ~/.ai-chan/run/llm.sock      ┌────────────────────────┐
│  ai-chan (main)     │  ◀────────── JSON-lines ──────────▶   │  ai-chan-llm-worker    │
│  - UI (PyQt6)       │                                         │  - core/llm.py         │
│  - core/ai_chan.py  │                                         │  - llama.cpp / MLX     │
│  - LLMProxy         │                                         │  - stdin/stdout ready  │
└─────────────────────┘                                         └────────────────────────┘
```

- **Worker エントリポイント**: `scripts/ai_chan_llm_worker.py`
- **起動**: ai-chan 起動時に `subprocess.Popen([sys.executable, "-m", "scripts.ai_chan_llm_worker"])`
- **永続化**: なし（worker は stateless、モデル設定は最初のハンドシェイクで渡す）
- **再起動**: ai-chan 側のヘルスチェック（30s ping）で失敗 → kill → 再起動。最大 3 回、それ以降は TF-IDF モードに縮退。

### 3.2 プロトコル（JSON-lines / UDS）

**Request**:
```json
{"id": "uuid-v4", "op": "generate_chat", "args": {"messages": [...], "stream": true}}
```

**Streaming chunk**:
```json
{"id": "uuid-v4", "kind": "chunk", "token": "こん"}
{"id": "uuid-v4", "kind": "chunk", "token": "にちは"}
{"id": "uuid-v4", "kind": "end", "full_text": "こんにちは、...", "usage": {"tokens": 42}}
```

**Error**:
```json
{"id": "uuid-v4", "kind": "error", "code": "model_crashed", "message": "..."}
```

- `id` は correlation ID（request ごとに UUID4）
- `stream_cb` は client 側で chunk 受信時にコールバック発火
- `restore_params` 等の state-mutation は先出し request → ack 待ち

### 3.3 新規ファイル構成

| パス | 行数見積 | 役割 |
|---|---|---|
| `core/llm_proxy.py` | ~250 | `LLMEngine` と同じ公開 API を持つ IPC クライアント |
| `core/llm_ipc_protocol.py` | ~120 | JSON-lines エンコード/デコード・バージョン協商 |
| `scripts/ai_chan_llm_worker.py` | ~180 | UDS サーバー、`LLMEngine` を in-process で保持 |
| `core/llm.py` | 1263 → 変更なし | worker 内で使われる本体（無改修） |
| `tests/test_llm_ipc.py` | ~200 | 契約テスト + worker-crash シナリオ |

### 3.4 フォールバック戦略

| 状況 | 挙動 |
|---|---|
| worker 起動失敗 | 3 秒後再試行 × 2 → in-process fallback（現状と同じ） |
| worker クラッシュ（RC != 0） | 自動再起動, 失敗 3 回で TF-IDF モード縮退 + UI 通知 |
| UDS timeout (30s) | request キャンセル + ヘルスチェック → worker 再起動判定 |
| protocol version mismatch | 起動時に検知 → FATAL（ユーザーに update 指示） |

## 4. リスクと懸念

### 🔴 ブロッキングリスク
- **MLX backend の fork 安全性未検証**: Metal は macOS 上で fork 後の state が壊れることで有名。`spawn` 固定必須。`multiprocessing.set_start_method("spawn", force=True)` を main 最上段で宣言する必要あり。
- **起動時間の悪化**: モデルロード 8–15 秒が worker 側で発生。UI は "loading" を表示する必要があり、現在の起動シーケンスを組み直す必要あり。

### 🟡 中リスク
- **ストリーミング latency**: UDS 経由で stream_cb 1 token あたり ~100μs のオーバーヘッド。Intel Mac で 10 tok/s 級の低速モデルなら問題なしだが、MLX 30 tok/s では体感できる可能性。
- **config 変更時のライフサイクル**: モデルパス変更 → worker 再起動が必要。settings UI に再起動ボタンが要る。
- **デバッグ難度**: traceback が 2 プロセスに分断される。統合ログ集約（`logs/llm_worker.jsonl`）が必要。
- **Windows 対応**: Unix Domain Socket は Windows 10 1803+ で限定サポート。TCP localhost フォールバック（ポート衝突回避が必要）か、named pipe 実装切替。

### 🟢 低リスク
- API 表面積が 6 個と非常に小さく、Proxy パターンで差し替え可能
- `LLMEngine` 本体は無改修で worker に移植できる（依存注入済み）
- 既存テストは `LLMEngine` を直接使っているのでほぼ影響なし（IPC テストは追加）

## 5. 移行工数見積

| Phase | 内容 | 見積 |
|---|---|---|
| 1. プロトコル設計・確定 | `core/llm_ipc_protocol.py`, contract test | 4h |
| 2. Worker 実装 | `scripts/ai_chan_llm_worker.py` + 起動スクリプト | 6h |
| 3. Proxy 実装 | `core/llm_proxy.py`, stream_cb ブリッジ | 8h |
| 4. ヘルスチェック & 再起動 | watchdog thread, circuit breaker | 4h |
| 5. Windows TCP fallback | 条件分岐 | 3h |
| 6. 統合テスト | crash injection, protocol version, reconnect | 6h |
| 7. UI 統合 | settings の "再起動" ボタン, 起動時 loading 画面 | 4h |
| 8. ドキュメント | architecture.md, trouble-shooting.md | 2h |
| 9. 段階ロールアウト | opt-in flag → 2 週観察 → default | （期間） 2 週 |

**合計工数**: 約 **37 時間**（action-matrix の「M8: 40h / 2w」とほぼ整合）

## 6. 判定: 🟡 Conditional Go

### Go とする根拠
1. API 表面積（6 メソッド）が小さく、Proxy 差し替えで既存コードへの影響を最小化できる
2. LLM クラッシュ → 会話 state 喪失の家族 AI としての信頼性インパクトが大きい
3. OOM / メモリリーク耐性が明確に向上（worker 再起動で RAM 完全解放）
4. MoE 実験やモデル差し替え時の安全性が上がる（crash 耐性）

### Conditional（条件付き）の理由
1. **家族 AI 単機運用ではクラッシュ頻度が低い**: 実測 945 セッションで LLM 由来クラッシュ 0 件。実害が顕在化していない。現状の優先度は **Nice-to-have**。
2. **Intel Mac 低速環境での UDS オーバーヘッド未測定**: 実測ベンチ必須（Phase 1 で tok/s 比較）。10% 以上劣化なら No-Go。
3. **Windows 対応方針先決必須**: UDS vs TCP localhost vs named pipe の判断が UI ライフサイクルに影響する。
4. **Phase 1 リリース後着手**: M12 完了直後の 944 テスト green ベースラインを 2 週安定運用してから。

### No-Go ではない理由
- MLX spawn 問題は既知の対策あり（`set_start_method("spawn")`）
- stream_cb の IPC 化は前例多数（vscode language server, copilot agent）
- 既存 `LLMEngine` はそのまま移植可能（再実装不要）

## 7. 次のアクション

1. ✅ **本レポートを docs/GUIDE/M8-llm-process-isolation.md に保存**（完了）
2. ⏸ **Phase 1（本ハードニングラウンド）終了を待機**
3. ⏸ **実装着手時の先行タスク**（リスクゼロで今すぐ可能）:
   - sub-task A: `core/llm.py` の副作用を `__init__` 以外に隔離（state-mutation メソッドの identify）
   - sub-task B: ストリーミング overhead のマイクロベンチ（`asyncio.StreamReader` vs synchronous `recv`）
   - sub-task C: Windows named pipe の PoC
4. ⏸ **実測トリガ**: LLM 由来クラッシュが 1 件でも観測されたら即 Go に昇格

**先行着手可能**: sub-task A（state-mutation 識別）は無害で工数 1h 程度。M9 と並走可。

## 参考資料

- [llama.cpp GitHub – server subproject](https://github.com/ggerganov/llama.cpp/tree/master/examples/server)
- [Python multiprocessing – spawn context on macOS](https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods)
- [Unix Domain Sockets on Windows 10 1803+](https://devblogs.microsoft.com/commandline/af_unix-comes-to-windows/)
- `docs/GUIDE/02-expert-reviews.md` §ST3 – LLM isolation 方針
- `docs/GUIDE/03-action-matrix.md` M8 行
- `core/llm.py` L273-1263 – 現行実装
