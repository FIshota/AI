# 02. 専門家 5 名の詳細レビュー（Linus 級辛口）

> 2026-04-20 実施。忖度なし。

---

## 🔒 Security Reviewer — **C (web: D)**

### Top 10 Findings

| # | Severity | 場所 | 問題 | 今日やる |
|---|:-:|---|---|---|
| CRITICAL-1 | 🔴 | `web/app.py` 全エンドポイント | 認証ゼロ、LAN 上の誰でも記憶を読み書き | `Depends(verify_token)` + `AICHAN_API_TOKEN` |
| CRITICAL-2 | 🔴 | `core/ai_chan.py:2749-2769` | `_handle_web_fetch` で url_guard 未配線（他では呼んでる） | `assert_safe_http_url(url)` 冒頭追加 |
| CRITICAL-3 | 🔴 | `core/web_fetcher.py:53-57` | `xml.etree.ElementTree` で外部 XML パース | `defusedxml` 置換 |
| HIGH-4 | 🟠 | `utils/crypto.py:129-133` | 鍵ファイルが DB と同ディレクトリ配置 | `~/.config/ai-chan/keys/` に分離 |
| HIGH-5 | 🟠 | `utils/crypto.py:45-82` | cryptography import 失敗で SHA-256 XOR に silent fallback | 起動時 sys.exit(1) |
| HIGH-6 | 🟠 | `core/memory.py:897-928` | security_level が recall()/search() で enforce されず | `max_security_level` 引数追加 |
| HIGH-7 | 🟠 | `core/audit_log.py:27` | ハッシュチェーン 16 文字(64bit) = 誕生日攻撃 2³² | 32+ 文字に |
| HIGH-8 | 🟠 | `core/web_fetcher.py:154` | cache_key = 無加工クエリ + TTL 後も残留 | sha256 + TTLCache |
| HIGH-9 | 🟠 | `core/clipboard_watcher.py:42-55` | パスワード/2FA を無条件で記憶に投入 | pii_masker.mask() 強制 |
| MEDIUM-10 | 🟡 | `requirements.txt:12` | python-jose メンテ不安 | PyJWT 移行検討 |

### 10 年後に最も痛い負債 3 つ
1. 認証なし Web API → 将来 WAN 公開（Tailscale 等）で即死
2. security_level がラベルシール化 → 機密分離が形骸化
3. Clipboard からパスワードが長期記憶に焼き付く → ユーザが気づいた時は手遅れ

### Subsystem Grades

| | Grade |
|---|:-:|
| crypto | B |
| **web** | **D** |
| watchers | C |
| deps | B+ |
| data-handling | C |

---

## 🏛 Architect — **B-**

### Grade Card

| Subsystem | Grade | 所見 |
|---|:-:|---|
| core/ai_chan.py | **C** | 29 core import + God Object |
| core/memory.py + migration.py | **A-** | 最も堅実、背骨 |
| core/llm.py | **B+** | CVE mitigation 自前実装は良い |
| core/emotion.py | **B** | ~~quantum_superposition 等ポエム API は捨てるべき~~ → M10 (2026-04-21) で `get_quantum_state()` / `quantum_superposition()` 削除済み。`mood_label()` は実使用中のため保持 |
| plugin_loader + 空 plugins/ | **D** | 機能しているフリ |
| Growth Stage | **C** | S0-S3 と INFANT-MATURE の 2 系統併存 |
| bench/ | **B+** | 役割分離が明確、健全 |
| yamato_dna + federated_stub | **D** | スタブ、量産前の害悪 |
| Test Suite (30f/819fn) | **C+** | スプリント名命名で回帰防止できてない |
| Config/Code 境界 | **C** | persona.json に会話例埋込 |

### 10 年後に最も後悔する 5 つ
1. **`core/ai_chan.py` が God Object** → 単一マージ地獄化
2. **Protocol を定義したのに使ってない** → DI 入口なし、差し替え不能
3. **Stage/Mode/Phase 系統が併存** → 10 年後コードが読めなくなる
4. **マルチテナント前提が 0** → YAMATO 量産が物理的に不可能
5. **スタブ3兄弟**（yamato_dna/federated_stub/plugin_loader）→ 骨組み誤認リスク

### 今すぐ捨てるコード

- `core/federated_stub.py`
- `core/yamato_dna.py`
- `core/plugin_loader.py` + 空 `core/plugins/`
- ~~`core/emotion.py` の `quantum_superposition()` / `mood_label()` 固定文字列~~ → M10 で `quantum_superposition()` 系削除、`mood_label()` は実使用のため保持
- `core/ai_chan.py:82-111` の CMD_* 60 個 re-export
- `tests/test_rag_and_life_assistant.py` / `test_multimodal_and_defense.py` / `test_server_ops_and_autonomous.py` / `test_conversation_intelligence.py` (旧 `test_sprint3*.py` / `test_sprint_j.py` / `test_sprint_k.py`, M7 でリネーム)
- `config/persona.json` の system_prompt 埋込会話例

### 絶対守るべき核

- `core/memory.py` — 三層記憶 + 暗号化（背骨）
- `core/migration.py` — 10 年運用で最も効く
- `core/protocols.py` — 使われてないが死守
- `core/llm.py` の CVE mitigation
- `docs/TAXONOMY.md`
- `bench/` (runner + suites + judges)
- `personality/` (YAML)

### Ai → YAMATO 再設計 3 手
1. **Protocol を本当に使う**（2 週間）
2. **TenantId 型導入 + `data/{tenant_id}/` 分割**（3 週間）
3. **Stage/Mode/Phase 用語統合**（1 週間）

---

## 🐍 Python Reviewer — **C+**

### Top 10 Code Smells

| # | Severity | 場所 | 痛み |
|---|:-:|---|---|
| 1 | CRITICAL | `main.py:406` vs `core/ai_chan.py:166` | `settings=` 引数なし → `--voice` 起動が TypeError（silent failure） |
| 2 | CRITICAL | `core/ai_chan.py:1615` | `chat()` が 517 行 God method |
| 3 | HIGH | `core/ai_chan.py:176/1879/1927` | `conversation_history` 無ロック + 背景スレッド mutation |
| 4 | HIGH | `core/growth_report.py:119-510` | `except Exception: pass` 10+ 箇所 |
| 5 | HIGH | `core/memory.py:249` | `_conn()` が毎回新接続、WAL が無駄 |
| 6 | HIGH | `core/memory.py:603-614` | 100 行 fetch → Python filter、暗号化時 fast path bypass |
| 7 | HIGH | `core/ai_chan.py` | `getattr(self, "x", None)` が **137 箇所** = mypy --strict 即死 |
| 8 | HIGH | `core/ai_chan.py:1958-1962` | `_batch_updates` が self を共有、並行 chat() でレース |
| 9 | MEDIUM | project-wide | `except Exception` 568 箇所、うち 30% が silent pass |
| 10 | MEDIUM | `main.py:25` | `logger` を定義前に使用、`except ImportError: pass` が NameError を隠蔽 |

### 即削除/分割すべき 3 ファイル

- `core/ai_chan.py` — 3,681 行（`cmd_handlers.py` / `memory_context.py` / `response_pipeline.py` が既にあるのに duplicate）
- `core/bio_nervous_system.py` — 1,095 行、状態機械と prompt 構築が混在
- `core/cmd_handlers.py` — 1,350 行のディスパッチャ mas querading as module

### 強制ルール 3 つ
1. `ruff` `BLE001` + `S110` を pre-commit（盲目 except ≈ 100 バグ発掘見込み）
2. `mypy --strict` を `memory.py`/`crypto.py` から段階導入
3. `ruff` `C901` max-complexity=12（chat() と _init_heavy_components が即落ちる）

### テストスイート評価: **C**
- 819 関数は量は good
- `test_memory_long_term.py` / `test_regression.py` は真面目
- **AiChan.chat() 並行テスト 0 件**、main.py:406 バグを検出するテスト 0 件
- 最大クラスに単体カバレッジゼロ

### 1 日だけならやること
> logger 定義順を全ファイル先頭に移動、ruff BLE001+S110 を pre-commit に、AiChan を最小 config で起動して chat() を呼ぶ 1 本のテストを書く。これで `--voice` 起動死を発見できる。

---

## 🎯 Performance Optimizer — **C+**

### 実測されるであろう常駐メモリ（Intel Mac 16GB）

| | |
|---|---|
| Python core | 80 MB |
| llama-cpp-python (7B Q4) | 4.5 GB |
| sentence-transformers | 500 MB |
| faiss | 50-500 MB |
| **torch + transformers（import だけ）** | **800MB-2GB** |
| Tkinter + PIL | 100 MB |
| **合計** | **6-8 GB** |

### あるべき姿: **3 GB 以下**（YAMATO 組込 8GB デバイスに載せるため）

### Top 10 ボトルネック

1. **`core/llm.py:345`** — 同期モデルロード → 起動体感 -15 秒（非同期化）
2. **`core/clipboard_watcher.py:18-24`** — pbpaste 1 日 34,560 回 fork → NSPasteboard.changeCount
3. **`core/memory.py:603-614`** — 暗号化時 fast path bypass、記憶 1 万件で破綻
4. **`core/memory.py:249-250`** — `_conn()` 毎回新規（WAL 無効化）
5. **`core/llm.py:1022-1031`** — `EntropyEngine` 毎 response 生成
6. **`core/llm.py:1239-1260`** — `UnifiedField` 毎ターン生成
7. **`ui/desktop_pet.py:134-156`** — fade_in after(20ms) ループ
8. **`core/screenshot_reader.py:36-43`** — 全画面 PNG を `/tmp` に書き出し
9. **`core/scheduler.py:97-99`** — check() 毎回ファイル読み
10. **`requirements.txt`** — torch/scipy/scikit-learn が常駐 → 不要

### クイックウィン 3 つ（各 1 日以内）
- **QW1**: pbpaste → NSPasteboard.changeCount（2h）
- **QW2**: torch 削除 + ONNX 切替（-2GB、4h）
- **QW3**: SQLite を threading.local シングルトン化（1h）

### 構造変更 3 つ（10 年スケール）
- **ST1**: LLM を別プロセス化（IPC）— UI クラッシュ分離、YAMATO 移植容易
- **ST2**: Embedding オンデマンド + 暗号化/FTS5 分離（平文 FTS + 本体暗号）
- **ST3**: 依存根本スリム化（torch/scipy/scikit-learn 削除、faiss→sqlite-vec、7B→3B）

### 正直な評価
> **Intel Mac 16GB では条件付きで動く。8GB Mac では動かない。Intel で 1 応答 40-90 秒。24/7 常用は厳しい。**

### YAMATO 最小仕様
- CPU: ARM Cortex-A76+ (Pi 5 クラス)
- RAM: **8GB 必須**
- Storage: 32GB+
- OS: Linux arm64
- **SW 変更必須**: UI 削除、3B モデル、torch/scipy 削除、faiss→sqlite-vec、systemd timer 移譲

---

## ⚕ Healthcare Reviewer — **C-（子供家庭 F）**

### 5 最重要ギャップ

| # | Severity | 場所 | 問題 |
|---|:-:|---|---|
| 1 | CRITICAL | `utils/crypto.py::load_or_create_key` + `config/settings.json.example` | 鍵ファイル `data/.key` が DB と同ディレクトリ平文、Time Machine 盗難で全滅 |
| 2 | CRITICAL | `core/clipboard_watcher.py` + `settings.json.example` | デフォルト ON、同意なし、マスクなし — パスワード/2FA が記憶 DB に |
| 3 | HIGH | `core/screenshot_reader.py` | `/tmp` に全画面 PNG、OCR クラッシュで残留 |
| 4 | HIGH | `core/memory.py::forget` + 全体 | Right to be forgotten 不在、非ユーザー家族（兄弟・子）は取消手段ゼロ |
| 5 | HIGH | `ui/settings_window.py` + `config/access_control.json` | アプリ内アクセス制御ゼロ、**diary/emotion/anniversary 平文**（encrypt されてるのは memories.db の content 列のみ） |

### コンプライアンス

| 規制 | Grade | 理由 |
|---|:-:|---|
| GDPR | **D** | 法的根拠/同意 UI/DSAR/erasure/portability 全部不在、平文 diary、default-on 受動キャプチャ |
| 個人情報保護法（APPI 2022） | **C-** | 要配慮個人情報が平文で diary に落ちる |
| HIPAA 相当 | **D** | read audit log なし、minimum-necessary 不在 |
| EU AI Act | **C** | Emotion inference の transparency 義務未対応 |
| **COPPA（児童保護）** | **F** | 年齢ゲート/保護者同意フロー/content filter/children's memory 制限 ALL 不在 |

### 最低限これだけは今やれ Top 3
1. **ClipboardWatcher/Screenshot をデフォルト OFF + 初回起動で明示同意**
2. **鍵を passphrase + macOS Keychain 由来に + diary/emotion/anniversary も `_enc()` 経由**
3. **`purge_subject(subject_id)` + `export_subject(subject_id)` 実装**

### 10 年後の規制を見越した設計提案
- **EU AI Act**: `emotion_history.py` に `inference_provenance` 列
- **日本 AI 法制化**: AI 発話に cryptographic signature + timestamp + model fingerprint
- **死後プロトコル**: `config/estate_policy.yaml`（Shamir 2-of-3 / デッドマンスイッチ / legacy）
- **越境配布**: region-aware default（EU clipboard=false 強制、US under-13 拒否）
- **量子耐性**: ML-KEM 想定の鍵ラッピング抽象
- **Right to explanation**: 記憶想起時の confidence/source/tier を常時可視化

### ワンライナー判決
> **clipboard/screenshot opt-in + diary 暗号化 + passphrase 鍵 + subject erasure/export が揃うまで実家族に出荷するな。特に子供のいる家庭には絶対に。**
