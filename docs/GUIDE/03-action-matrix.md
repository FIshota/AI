# 03. アクションマトリクス — 優先度付き実行計画

> **Priority = 影響度 I × 緊急度 U × 10年重要度 T**（各 1-5、最大 125）

## 📊 進捗サマリ（2026-04-21 更新）

| Phase | 完了 | 合計 | 残工数見込み |
|---|:-:|:-:|:-:|
| **BLOCKER** | **10 / 10** 🎉 | 10 | 全完了 |
| HIGH | **10 / 10** 🎉 | 10 | 2026-04-21 全完了 |
| MEDIUM | 0 / 12 | 12 | — |

## 🚨 BLOCKER（出荷前必須、Priority ≥ 60）

出荷 = 実家族ベータ / YAMATO 配布。これらが揃うまで **誰にも使わせない**。

| # | 項目 | 領域 | I | U | T | Pri | 工数 | 状態 | 担当ファイル |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| B1 | Web API 全エンドポイント認証 | Sec | 5 | 5 | 5 | **125** | 1d | ✅ 2026-04-21 | `web/app.py` (require_auth) |
| B2 | diary/emotion/anniversary 暗号化統一 | Health | 5 | 5 | 5 | **125** | 3d | ✅ 2026-04-21 | `core/{diary,emotion_history,anniversary}.py` + `utils/secure_store.py` |
| B3 | 鍵を passphrase + macOS Keychain バインド | Health/Sec | 5 | 4 | 5 | **100** | 2d | ✅ 2026-04-21 | `utils/keychain.py` (新設) |
| B4 | `_handle_web_fetch` に url_guard 配線 | Sec | 5 | 5 | 4 | **100** | 2h | ✅ 2026-04-20 | `core/ai_chan.py:_handle_web_fetch` |
| B5 | ClipboardWatcher/Screenshot デフォルト OFF + 同意 UI | Health | 5 | 5 | 4 | **100** | 1d | ✅ 2026-04-21 | `config/settings.json.example`, `ui/settings_window.py`, `core/cmd_handlers.py` |
| B6 | diskcache CVE-2025-69872 回避 | Sec | 4 | 5 | 4 | **80** | 4h | ✅ 事前対応済み | `core/llm.py:_harden_llm_cache()` (0700 perms / owner check / pickle scrub / XDG_CACHE_HOME) |
| B7 | security_level を recall()/search() で enforce | Sec | 5 | 4 | 4 | **80** | 3d | ✅ 2026-04-21 | `core/memory.py` (search/search_hierarchical/search_by_keywords/search_fts/get_recent に clearance 引数 + SQL 側 WHERE 絞込) |
| B8 | `purge_subject(subject_id)` + `export_subject()` | Health | 5 | 3 | 5 | **75** | 1w | ✅ 2026-04-21 | `core/subject_rights.py` (新設) + `core/ai_chan.py` 配線 |
| B9 | defusedxml 置換 | Sec | 4 | 4 | 4 | **64** | 2h | ✅ 2026-04-20 | `core/web_fetcher.py` |
| B10 | main.py logger 順序 + AiChan settings= | Sec | 4 | 4 | 3 | **48** | 30min | ✅ 2026-04-20 | `main.py`, `core/ai_chan.py.__init__` |
| B10 | main.py logger 定義順 + AiChan `settings=` 引数 | Py | 4 | 5 | 3 | **60** | 1h | `main.py`, `core/ai_chan.py:166` |

**BLOCKER 総工数**: 約 4-5 週間（1 人月）

## 🟠 HIGH（今四半期、Priority 40-74）

| # | 項目 | Pri | 工数 |
|---|---|:-:|:-:|
| H1 | core/ai_chan.py を Protocol 経由 DI に（Arch Step 1） | 100 | 2w | ✅ 2026-04-21 `core/deps.py` (AiChanDeps) + `core/protocols.py` 拡張、`__init__(deps=...)` 受け入れ |
| H2 | TenantId 型導入 + `data/{tenant_id}/` 分割（Arch Step 2） | 75 | 3w | ✅ 2026-04-21 `core/tenant.py` + diary/emotion_history/anniversary が tenant_dir 経由（旧パス fallback 付） |
| H3 | ClipboardWatcher に PII deny-list 強制 | 60 | 4h | ✅ 2026-04-21 `core/clipboard_watcher.py` (13 pattern deny-list + drop) |
| H4 | 監査ログハッシュ 16→32+ 文字 | 48 | 1h | ✅ 2026-04-20 `core/audit_log.py:_hash_line` full SHA-256 |
| H5 | `_batch_updates` 単一ワーカー + `_history_lock` | 48 | 1d | ✅ 2026-04-21 `core/ai_chan.py` (`_history_lock` + `_batch_executor` max_workers=1) |
| H6 | torch 排除 + ONNX 切替（-2GB 常駐） | 60 | 1d | ✅ 2026-04-21 `requirements.txt` torch デフォルト除外 + `core/vision_engine.py` graceful fallback |
| H7 | pbpaste → NSPasteboard.changeCount | 36 | 2h | ✅ 2026-04-21 `core/clipboard_watcher.py:_get_change_count` O(1) 判定 |
| H8 | web_search キャッシュ sha256 + TTLCache | 36 | 2h | ✅ 2026-04-21 `core/web_fetcher.py` sha256 キー + LRU (512 entries) + Lock |
| H9 | cryptography import 失敗時 sys.exit(1) | 40 | 30min | ✅ 2026-04-20 `utils/crypto.py` (AICHAN_ALLOW_CRYPTO_FALLBACK env-flag opt-in) |
| H10 | transformers 5.0.0rc3 / 他 minor 更新 | 30 | 2h | ✅ 2026-04-21 `requirements.txt` cryptography/fastapi/uvicorn/pydantic 他 minor bump |

## 🟡 MEDIUM（今年中、Priority 20-39）

| # | 項目 | Pri | 工数 |
|---|---|:-:|:-:|
| M1 | Stage/Mode/Phase 用語統合（Arch Step 3） | 32 | 1w |
| M2 | God Object 解体（ai_chan / bio_nervous / cmd_handlers） | 40 | 1mo |
| M3 | スタブ3兄弟削除（yamato_dna/federated_stub/plugin_loader） | 27 | 1d |
| M4 | ruff BLE001 + S110 + mypy strict を memory/crypto から段階導入 | 32 | 1w |
| M5 | SQLite threading.local connection | 27 | 1d |
| M6 | scripts/convert_hf_to_gguf.py を upstream 参照に降格 | 18 | 2h |
| M7 | test_sprint*.py を機能別再編 | 24 | 3d |
| M8 | LLM を別プロセス化（IPC） | 40 | 2w |
| M9 | faiss-cpu → sqlite-vec 移行検証 | 30 | 1w |
| M10 | core/emotion.py ポエム API 削除 | 18 | 2h |
| M11 | core/ai_chan.py CMD_* 60 個 re-export 削除 | 18 | 1d |
| M12 | chat() 517 行を pipeline 分解 | 40 | 2w |

## 🟢 LATER（YAMATO 量産前、Priority < 20）

- 🏛 AI 発話 cryptographic signature（訴訟耐性）
- 🏛 `config/estate_policy.yaml` 死後プロトコル
- 🏛 region-aware defaults（EU/US 配布時）
- 🔒 量子耐性鍵ラッピング抽象（ML-KEM 想定）
- ⚕ `inference_provenance` 列（emotion_history）
- ⚕ Right to explanation UI（記憶想起トレース）
- 🏛 federated learning 本実装（PP-1）
- 🏛 世代継承プロトコル（親 Ai → 子 Ai 人格引継ぎ）

## 📐 推奨実行順

### Week 1（最初の 1 週間）
- H9（crypto fallback exit）30min
- B10（logger/settings）1h
- B4（url_guard 配線）2h
- B9（defusedxml）2h
- H7（NSPasteboard）2h
- H8（cache sha256）2h
- H4（audit hash）1h
- M10（ポエム API 削除）2h
- H10（minor updates）2h
- **B1（Web 認証）1d**
- **B5（watchers OFF）1d**
- **B6（diskcache 退避）4h**
- **H6（torch 削除）1d**

→ 1 週間で BLOCKER 5/10 + HIGH 半分を消化

### Week 2-3
- **B2（encryption 統一）3d**
- **B3（passphrase/Keychain）2d**
- **B7（security_level enforce）3d**
- H3（PII deny-list）4h
- H5（history lock）1d

### Week 4-7（1 ヶ月）
- **B8（purge/export subject）1w**
- **H1（Protocol DI）2w**
- **H2（TenantId）3w**

### Month 2-3
- M1（用語統合）1w
- M2（God Object 解体）1mo
- M12（chat() 分解）2w
- M8（LLM プロセス分離）2w

### Month 4-6
- M9（sqlite-vec）
- M4（ruff/mypy 全域）
- LATER 着手開始

## 🎯 完了判定基準

BLOCKER 10 本完了 = **実家族 3 世帯ベータ可能**
HIGH 完了 = **β 公開可能**
MEDIUM 完了 = **YAMATO プロトタイプ（SW 版）公開可能**
LATER 完了 = **YAMATO 量産判断可能**
