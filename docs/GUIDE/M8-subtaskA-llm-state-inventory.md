# M8 Sub-task A: `core/llm.py` State-Mutation 棚卸し

**作成日**: 2026-04-21
**ステータス**: M8 先行タスク（リスクゼロ、実装未変更）
**目的**: IPC 化する際に **client / worker** のどちらに状態を置くか、**同期化が必要なメソッドペア** がどれか、**キャッシュ整合性** の設計要件を明確化する。

---

## 1. サマリ

| 分類 | メソッド数 | IPC 境界化 |
|---|---|---|
| 公開 API（`self.llm.*`） | **11** | ✅ 全て |
| worker 内部のみ（ロード系 `_load_*`） | 3 | ❌ 不要（起動時 1 回のみ） |
| state-mutating メソッド | 8（ほぼ `__init__` と load） | ✅ ※後述 |

**結論**: IPC 境界を横断する "state-mutation" は実質 `override_params` / `restore_params` のペアのみ。その他のキャッシュ書き込みは worker 内部で完結し、IPC プロトコルには露出しない。

## 2. 公開 API の分類（IPC 必須面）

| メソッド | 行 | 引数 | 戻り値 | 副作用 | IPC モード |
|---|---|---|---|---|---|
| `is_loaded()` | 640 | – | `bool` | 純粋 | sync, cacheable on client |
| `is_loading()` | 643 | – | `bool` | 純粋 | sync |
| `get_backend()` | 646 | – | `str` | 純粋 | sync, cacheable after ready |
| `backend` (property) | 651 | – | `str` | 純粋 | sync, cacheable |
| `override_params(params)` | 655 | dict | dict (saved) | **backend mutation** | **sync + stateful** |
| `restore_params(saved)` | 669 | dict | None | **backend mutation** | **sync + stateful** |
| `get_context_stats()` | 743 | – | dict | 純粋 read | sync |
| `generate_with_confidence(prompt)` | 765 | str | (str, float) | generation | sync (long) |
| `generate(prompt, stream)` | 919 | str, bool | str \| Generator | generation + cache W | **sync or stream** |
| `generate_chat(messages, stream, stream_cb)` | 992 | list, bool, cb | str | generation + cb | **sync or stream-cb** |
| `build_prompt(...)` | 1202 | 4 args | list[dict] | cache W (ローカル) | **client-side 可** |

### 2.1 `build_prompt` は client-side 実行で良い

`build_prompt` は純粋なプロンプト組み立て関数で、内部キャッシュ `_cached_prompt` / `_last_prompt_hash` も同一プロセスなら十分。
→ **client (ai-chan 本体) で実行**、worker に送る payload は既に組み立て済みの `messages` にする。
→ IPC データ量削減効果: system_prompt + memory_context の重複送信を回避（1 ターン数 KB × ターン数分）。

### 2.2 Stateful ペア: `override_params` ↔ `restore_params`

```python
saved = llm.override_params({"temperature": 1.2})   # MoE 実験で温度上げ
response = llm.generate_chat(messages)              # override 反映下で生成
llm.restore_params(saved)                           # 元に戻す
```

- 呼び出し順序が保証される必要あり（割込み不可）
- `saved` は worker 内部の llm ハンドル状態 snapshot
- IPC 設計: **sticky session**（同一 request id family 内で同じ worker ハンドル）か、または **call fence**（restore 完了まで次の generate を受け付けない）

**推奨**: client 側で `with llm.params_override({...}):` コンテキストマネージャを新設し、IPC では atomic な `generate_with_params_override(messages, params)` 合成オペに変換する。これで 3 回の round-trip → 1 回に削減 & ordering 問題を排除。

### 2.3 ストリーミング系 2 つ

| メソッド | 現在のシグネチャ | IPC 適用 |
|---|---|---|
| `generate(prompt, stream=True)` | Generator 返却 | chunk frame を JSON-lines で送信、client は generator 化 |
| `generate_chat(messages, stream_cb=cb)` | callback 呼出し | chunk frame 受信時に client 側で cb 呼出し |

両者とも以下の frame で統一可能:

```json
{"id":"uuid","kind":"chunk","token":"こん"}
{"id":"uuid","kind":"end","full_text":"...","usage":{"prompt_tokens":42,"completion_tokens":18}}
```

## 3. state-mutating メソッドの分類（worker 内部限定）

| 種別 | メソッド | 書き込む self.* 属性 | IPC 影響 |
|---|---|---|---|
| 起動 1 回 | `__init__` | model_path, config, _backend, _llm, _mlx_*, _loaded, _template_id, **_response_cache**, _context_stats, _inference_lock | worker 起動時に実行。client は handshake request (`{"op":"init","config":{...}}`) で指示 |
| 起動 1 回 | `_load_model` / `_try_load_mlx_engine` / `_try_load_mlx` / `_try_load_llama` | _backend, _llm, _loaded, _mlx_*, _model_family, _model_family_info, _model_name, _template_id | worker 内部で完結 |
| 呼出し毎 | `_record_context_stats` | _context_stats | worker 内部、client に漏れるのは `get_context_stats()` の結果 dict のみ |
| 呼出し毎 | `generate` | _response_cache_hits, _response_cache_misses | worker 内部キャッシュ統計 |
| 呼出し毎 | `build_prompt` | _cached_prompt, _last_prompt_hash | **client-side 実行なら client 側に存在** |

**重要**: `_response_cache` は worker 側でのみヒット可能。client 側に 2 次キャッシュを置くと整合性問題が起きるので **client cache は持たない**。

## 4. IPC プロトコル設計への含意

### 4.1 request types（8 op）

```
{"op":"init",         "config": {...}}              → worker handshake
{"op":"is_loaded"}                                   → {"loaded": bool}
{"op":"get_backend"}                                 → {"backend": "mlx" | "llama"}
{"op":"get_stats"}                                   → {"stats": {...}}
{"op":"generate",     "prompt": str, "stream": bool} → text or chunk stream
{"op":"generate_chat","messages": [...], "stream": bool, "params_override": {...}} → text or chunk stream
{"op":"generate_with_confidence","prompt": str}      → (text, confidence)
{"op":"shutdown"}                                    → graceful stop
```

**merge**: `override_params` / `restore_params` を直接 expose せず、`params_override` を `generate_chat` 引数に吸収。worker 側で `try/finally` で保証する。

### 4.2 client (ai-chan 本体) 側のやるべきこと

1. `build_prompt` は client-side（`core/llm_proxy.py` 内部で既存 `LLMEngine.build_prompt` を呼ぶ）
2. `params_override` の context manager API を新設（既存の `override_params`/`restore_params` は deprecated 扱い）
3. `_response_cache` / `_context_stats` の読み取りは worker 経由のみ（client に duplicate しない）

### 4.3 worker 側のやるべきこと

1. handshake で `config` を受け取り `LLMEngine(model_path, config)` を生成
2. request ループで op をディスパッチ
3. ストリーミングは **同期ジェネレータ** → bytes encode → stdout / UDS
4. stateful pair は受信レイヤーで atomically 処理

## 5. 既存実装の制約

### 5.1 `_inference_lock` の意味

`__init__` で `self._inference_lock = threading.Lock()` が作られ、`generate_chat` 内で `with self._inference_lock:` している。
→ llama.cpp / MLX の内部状態（KV cache など）は **thread-safe ではない**。
→ worker は **single-threaded event loop** で十分（並列 generation は backend 側で壊れる）。
→ 同時 chat はキュー化。

### 5.2 MoE `apply_routing` は `LLMEngine` 外

`core/ai_chan.py._apply_moe_routing` が `self.moe_router.apply_routing(task_type, self.llm)` を呼ぶ。
`self.llm` を直接渡している → IPC 化時は **`MoERouter` が LLMProxy の override_params 等を経由する前提**に書き換える必要あり。
→ `moe_router` は client 側に残り、`LLMProxy` の public API 経由で通信する。

## 6. 次のサブタスク（B）への申し送り

- ストリーミング frame サイズ: 平均 1 token = UTF-8 3 bytes, JSON overhead 込みで **~40 bytes/frame**
- 日本語チャット平均 200 tokens = 8KB/応答
- チャット頻度: 家族 AI で **~1 応答/10 秒**（ピーク時）
- ベンチターゲット: **per-chunk latency < 500μs**, throughput > 500 chunks/s
- 計測方式: UDS loopback で 10000 チャンク送受信 × 3 パターン:
  1. blocking `socket.recv` + `json.loads`
  2. `asyncio.StreamReader.readline()`
  3. length-prefixed binary frame

---

## 判定: Clean, ready for Phase 1

- IPC 境界 = **8 op** に集約（当初懸念の「30 メソッド」ではない）
- state-mutation ペアは `params_override` context manager 設計で解消
- cache は worker 側一本化で整合性問題なし
- `_inference_lock` 要件で worker は single-thread で OK（設計単純化）

M8 本実装時の **risk reduction**: 当初の「stream_cb を 2 プロセスに分断する複雑さ」 → `params_override` を合成オペ化することで大幅軽減。

---

## 参考

- `docs/GUIDE/M8-llm-process-isolation.md` - 本 M8 の Go/No-Go 判定
- `core/llm.py` L273-1263
- `core/ai_chan.py._apply_moe_routing`
