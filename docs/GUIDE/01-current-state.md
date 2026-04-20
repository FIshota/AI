# 01. 現在地（Current State）— 2026-04-20

> 自動スキャン + 5 専門家レビューで凍結した「今の ai-chan」。
> **全結果は Linus 級辛口モードで取得済み**。忖度なし。

## 🔬 自動スキャン結果

### pip-audit（依存脆弱性）

| CVE | Package | Version | Fix | 備考 |
|---|---|---|---|---|
| CVE-2026-1839 | transformers | 4.57.6 | 5.0.0rc3 | Trainer クラス |
| **CVE-2025-69872** | diskcache | 5.6.3 | **未修正** ⚠️ | pickle 逆シリアル化 |

### bandit（静的解析、351 件 high-confidence）

| Severity | 件数 |
|---|---|
| HIGH | 0 |
| **MEDIUM** | **26** |
| LOW | 340 |

**Medium リスク要対処:**
- `core/server_home.py` L204/228/261/265/269/275 — Paramiko shell injection 6 箇所
- `core/web_fetcher.py` L36/56/57/108/171 — SSRF 候補 + unsafe XML parse
- `core/memory.py` L645/667, `core/memory_compressor.py` L68, `core/data_exporter.py` L160 — SQL injection 候補 4 箇所
- `web_main.py` L22/78 — 0.0.0.0 バインド
- `bench/dataset_loaders.py` L94 — HF Hub download without revision pinning

### gitleaks ✅

33 commits scanned, **0 leaks**. 唯一のクリーン領域。

### outdated packages

transformers / fastapi / cryptography / Flask / lxml / pillow / sentence-transformers ほか 30+ が 1-2 minor 遅れ。

### コード規模

| | |
|---|---|
| `core/ai_chan.py` | **3,681 行** 👹 |
| `scripts/convert_hf_to_gguf.py` | 6,195 行（upstream copy） |
| `core/bio_nervous_system.py` | 1,095 行 |
| `core/cmd_handlers.py` | 1,350 行 |
| `core/llm.py` | 1,263 行 |
| `core/memory.py` | 1,049 行 |
| 800 行超ファイル | **11 個** |
| core/ フラットモジュール | **129 個** |
| tests / sources 比 | 30 / 227 = 13%（量よりカバレッジ） |

## 📊 5 専門家グレードカード

| 専門家 | 総合 | 主要サブシステム | 要点 |
|---|:-:|---|---|
| 🔒 security-reviewer | **C** | crypto:B / **web:D** / watchers:C / deps:B+ / data:C | Web 認証ゼロ、SSRF ガード未配線、security_level 形骸化 |
| 🏛 architect | **B-** | memory:A- / llm:B+ / **ai_chan:C** / **plugin:D** / **yamato_dna:D** | God Object + Protocol は飾り + マルチテナント不可 |
| 🐍 python-reviewer | **C+** | — | main.py 起動時 NameError を silently 飲む / chat() 517行 / 568 件の盲目 except |
| 🎯 performance-optimizer | **C+** | — | 常駐 6-8GB（torch 不要で -2GB）/ pbpaste 1日 34,560 fork / FTS5 × 暗号化矛盾 |
| ⚕ healthcare-reviewer | **C-** | GDPR:D / APPI:C- / HIPAA:D / EU AI Act:C / **COPPA:F** | **diary 平文** / 鍵と DB 同居 / RTBF 不在 / 子供家庭に出荷不可 |

## 🔴 5 名全員が独立に指摘した "単一の根"

| # | 問題 | Sec | Arch | Py | Perf | Health |
|---|---|:-:|:-:|:-:|:-:|:-:|
| 1 | `core/ai_chan.py` God Object | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2 | 家族/テナント境界 不在 | ✅ | ✅ | — | — | ✅ |
| 3 | 暗号化の一貫性破綻 | ✅ | — | — | ✅ | ✅ |
| 4 | Web 認証 / SSRF ガード | ✅ | — | — | — | ✅ |
| 5 | torch 肥大 + watchers default ON | — | — | — | ✅ | ✅ |

**これが BLOCKER の絶対核。**

## 💡 唯一救われているもの

- gitleaks クリーン（秘密情報漏洩なし）
- `core/memory.py` + `core/migration.py` — 三層記憶 + 暗号化 + マイグレーションは A- 級
- `core/protocols.py` — 使われてないが死守すべき抽象
- `bench/` — runner + suites + judges の役割分離は B+
- crypto PBKDF2 480k iter は妥当

## 次の一歩

→ `02-expert-reviews.md`（詳細指摘） → `03-action-matrix.md`（優先度） → `04-decade-roadmap.md`（航路）
