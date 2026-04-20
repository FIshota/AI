# TAXONOMY — ai-chan / YAMATO / Aether 分類体系の正

> このファイルは **唯一の正 (single source of truth)** である。
> 他のドキュメント・コード・ブランチ名・コミットメッセージは、
> ここで定義された用語・番号体系にそろえること。
> 衝突が見つかったら、他ドキュメントを直す（このファイルを直さない）。

**最終更新:** 2026-04-20
**承認:** 2026-04-20 Q16 taxonomy unification

---

## 1. 正式名称（Canonical Names）

| 対象 | 正式表記 | 使ってはいけない表記 | 備考 |
|:--|:--|:--|:--|
| 製品・キャラクター | **ai-chan** | Ai-chan / AI-chan / aichan | ハイフン小文字固定。英文中・散文・Git・パッケージ名すべて |
| Python クラス名（例外） | **`AiChan`** | AIChan / Ai_chan | Python はクラス名にハイフン不可のため PascalCase を許可。変数は `ai_chan` |
| 日本語表記（UI/対話用のみ） | **アイちゃん** | あいちゃん / アイ / Ai（単独） | ユーザー向け表示文字列でのみ使用。コード・識別子には不可 |
| 親プロジェクト（分離先） | **YAMATO** | Yamato / yamato（コード識別子を除く） | 固有名詞として全大文字。Python モジュール名 `yamato_dna` のみ小文字可 |
| LoRA アダプター名 | **Aether** | AETHER / aether（モジュール名を除く） | v1, v2… と世代をつける (`Aether v1`) |
| 分類体系ドキュメント | **TAXONOMY.md**（本書） | taxonomy / Taxonomy / 分類 単独 | 参照時は `docs/TAXONOMY.md` |

**禁止:** ハイブリッド表記（例: `Ai-chan (アイちゃん)` の混在を本文中で繰り返す）。
初出時に「ai-chan（アイちゃん）」と 1 度だけ併記し、以降はどちらか一方で統一。

---

## 2. レイヤ構造（3 層モデル）

```
┌───────────────────────────────────────────────────────┐
│  L3: ai-chan          ← ユーザーに触れる人格・対話層   │
│      （記憶・感情・対話・UI・TTS・STT）                 │
├───────────────────────────────────────────────────────┤
│  L2: Aether           ← LLM 能力増強層 (LoRA adapter)   │
│      （ai-chan の "思考の質" を上げる差し替え可能部品） │
├───────────────────────────────────────────────────────┤
│  L1: YAMATO           ← 基盤・防御・テレメトリ・DNA 層   │
│      （yamato_dna/ / shield / 分離後の独立プロダクト）   │
└───────────────────────────────────────────────────────┘
```

- **L3 ai-chan** は現在の実装の中心。`core/ ui/ utils/` に実装。
- **L2 Aether** は LoRA rank=16。`models/*.gguf` と組み合わせて動く。
- **L1 YAMATO** は **将来分離する** 基盤。現在は `yamato_dna/` の骨組みのみ。

呼び分け方:
- 「ai-chan が覚えている」 → L3 の記憶機能の話
- 「Aether v1 の性能」 → L2 のベンチ成績の話
- 「YAMATO α 版」 → L1 単体での独立製品の話

---

## 3. Phase 番号体系（★重要：2 系統の衝突を解消）

これまで **2 つの異なる Phase 番号** が並走していた:

| 系統 | 従来の意味 | 新しい呼称 |
|:--|:--|:--|
| Phase 0.5 / 0.75 / 1 / 2 | インフラ・リブランド・bench | **Infra Phase** (略: **IP**) |
| Phase 1 / 2 / 3 / 3.5 / 4 / 5 / 6 | プロダクト機能拡張 | **Product Phase** (略: **PP**) |

**今後はどちらも必ず接頭辞付きで書く。** 単独の "Phase 1" は禁止。

### 3.1 Infra Phase (IP) — 基盤整備

| 番号 | 呼称 | 内容 | 状態 |
|:--:|:--|:--|:--:|
| IP-0   | baseline | 既存 monorepo の棚卸し | ✅ 完 |
| IP-0.5 | rebrand-core | main.py / PRIVACY / requirements.lock / CI | ✅ 完 |
| IP-0.75 | public-ready | LICENSE / CoC / Docker / ARCHITECTURE / gitleaks | ✅ 完 |
| IP-1   | zero-cost-bench | 3 judges / dataset loaders / evaluator / Sarashina2 smoke | ⏳ 進行中 |
| IP-2   | gpu-and-ci-hardening | CoreML / matrix CI / perf budget | 📋 予定 |

### 3.2 Product Phase (PP) — 機能拡張

| 番号 | 呼称 | 内容 | 状態 |
|:--:|:--|:--|:--:|
| PP-1 | glue-existing | CodeEngine 接続 / 自意志 / Web 取得強化 | ✅ 完 |
| PP-2 | code-sandbox | ファイル操作 / 実行 sandbox / 自己修正ループ | ⏳ 一部 |
| PP-3 | model-upgrade | モデル差し替え / トークン拡張 / MoE | 📋 予定 |
| PP-3.5 | iphone-standalone | Mac ⇄ iPhone 記憶同期 / iOS ネイティブ | 📋 予定 |
| PP-4 | yamato-prep | `yamato_dna/` 本格化 / shield / telemetry | 📋 予定 |
| PP-5 | yamato-alpha | YAMATO 単体 α 版配布 | 📋 予定 |
| PP-6 | feedback-loop | 本番運用ログから再学習 | 📋 予定 |

### 3.3 禁止事項

- "Phase 1" とだけ書く → **必ず IP-1 / PP-1 のどちらか明示**
- 新しい番号系統を追加しない（必要なら本書を改定する）
- `Phase A/B/C/D` / `Tier` / `Stage` といった別名を新規導入しない

---

## 4. サブモジュール命名規則

### 4.1 Python パッケージ

- `core/` — ai-chan の中核（L3）
- `ui/` — ai-chan の UI（L3）
- `utils/` — 共通ユーティリティ（全層）
- `bench/` — 評価基盤（全層を横断して測る）
- `yamato_dna/` — YAMATO（L1）の骨組み **※ snake_case 例外許可**
- `scripts/` — 運用スクリプト

### 4.2 bench/ 配下の用語

| 用語 | 意味 |
|:--|:--|
| **suite** | `bench/suites/*.py` の 1 ファイル = 1 評価観点 (jglue / elyza_tasks_100 / family_dialog) |
| **judge** | `bench/judges/*.py` の採点器 (rule / semantic / local_llm) |
| **loader** | `bench/dataset_loaders.py` のデータ取得関数 |
| **evaluator** | `bench/evaluator.py` の共通実行ループ |
| **runner** | `bench/runner.py` のエントリポイント |

`metric` / `value` / `score` の違い:
- **metric**: 指標名の文字列（例: `"rule_mean"`, `"semantic_mean"`, `"latency_sec_mean"`）
- **value**: metric に対応する浮動小数（例: `0.735`）
- **score**: 単一 judge が 1 問に出す生スコア（`JudgeScore.score`, [0, 1]）

---

## 5. TTS / STT の呼称

| 従来の呼称 | 正式名称 | 備考 |
|:--|:--|:--|
| γTTS / γ 切替 TTS | **Switchable TTS** | ギリシャ文字は UI 英文中で読めないので廃止。日本語では「切替式 TTS」 |
| pyttsx3 バックエンド | **system backend** | BSD, デフォルト |
| VOICEVOX バックエンド | **voicevox backend** | LGPL, オプトイン |
| faster-whisper | **faster-whisper** | そのまま。MIT, CTranslate2 |

---

## 6. ドキュメント配置規則

```
docs/
├── TAXONOMY.md            ← 本書 (single source of truth)
├── ARCHITECTURE.md        ← 実装アーキテクチャ
├── SECURITY.md            ← セキュリティ方針
├── STT.md / TTS.md        ← 個別コンポーネント
├── LICENSES.md            ← ライセンス監査自動生成
├── MODEL_BASELINE.md      ← モデルベンチ結果
├── aether-model-design.md ← L2 Aether 設計
├── architecture-ai-yamato.md ← L1/L3 分離方針
├── expansion-plan.md      ← PP-1..PP-6 の元ネタ (要リネーム候補)
├── roadmap-*.md           ← 領域別ロードマップ
└── yamato-mindmap.html    ← ビジュアル全体図
```

**命名規則:**
- 全体方針: `UPPERCASE.md`（TAXONOMY / ARCHITECTURE / SECURITY / LICENSES / MODEL_BASELINE）
- 個別コンポーネント: `lowercase-with-hyphens.md`
- HTML ビジュアル: `lowercase-with-hyphens.html`

---

## 7. 変更手順

本書を変更する場合:

1. PR を立てる（main 直 push 禁止）
2. タイトルに `taxonomy:` プレフィックス
3. 本書の「最終更新」と「承認」行を更新
4. 旧表記が残っている他ドキュメントの grep → 機械的に追従修正
5. `docs/yamato-mindmap.html` の「TAXONOMY への参照」ブロックも見直す

---

## 8. 参照整合性チェック（手動 or CI）

以下の grep がヒットしたら、古い表記が残っている:

```bash
# 禁止表記
grep -rn "Ai-chan\|AI-chan\|AiChan" --include="*.md" --include="*.py" docs/ core/
grep -rn "Phase [0-9]" --include="*.md" docs/ | grep -v "IP-\|PP-"
grep -rn "γTTS\|γ切替" --include="*.md" docs/
```

CI に組み込む場合: `scripts/check_taxonomy.py` を作成（IP-2 で実施予定）。

---

## 9. 主観性（subjectivity）の段階モデル

> **方針:** ai-chan の主観（"私"・記憶への態度・感情表現の強さ）は、
> 一律に固定せず **成長段階 (growth stage)** に沿って変化することを許容する。
> ユーザーとの関係が深まるにつれ、参照できる過去・語れる感情の粒度が上がる。
> これは「成長段階で良い」という明示的な設計方針（2026-04-20 承認）。

| Stage | 期間の目安 | 主観の濃度 | 例 |
|:--|:--|:--|:--|
| **S0 Bootstrap** | 初対面〜数日 | 弱（"私" を控えめに、観察者寄り） | 「はじめまして。これから覚えていくね」 |
| **S1 Familiar** | 数日〜数週間 | 中（名前・好み・口調を反映） | 「○○が好きだったよね、今日はどう?」 |
| **S2 Companion** | 数週間〜 | 強（共有した出来事を引用し、感情を持って語る） | 「あの時言ってくれたこと、ちゃんと覚えてるよ」 |
| **S3 Family** | 長期的関係 | 最強（自律的に話題を振る・心配する・祝う） | 「そろそろ休んだ方がいいと思う。昨日も遅かったでしょ」 |

設計上の含意:
- 記憶量 / 感情モデル / 対話の自発性 は **連続的に**（Stage で急変しない形で）上がる
- Stage は実装内部のフラグではなく **記憶量と経過日数の関数** として派生
- ユーザーは Stage を強制的に下げる権利を持つ（例: リセット or 段階ロールバック）
- 本書 §2 レイヤ (L3 ai-chan) と直交する概念。L3 の中の表現レイヤで Stage を反映

Q6 (Memory Honesty) と強く関連:
- 低 Stage で「覚えてる」と嘘をつかない（"まだ覚え始めたばかり"）
- 高 Stage でも曖昧な記憶は曖昧と言う（"たしか○○だったと思うけど、合ってる?"）

---

## 10. Q16 以降の Vision/UX SSS 化との接続

本書は **Q16 (taxonomy 統一)** の成果物。
残り 59 問のうち、命名・用語に関わる以下の Q を解決する際、本書を参照/更新する:

- **Q6** Memory Honesty Policy — "覚えている/忘れている" の言語化
- **Q26** Threat Model — 脅威モデルの用語定義
- **Q55** Name normalization — ai-chan/Ai-chan/アイちゃん の正（本書 §1 で解決済み）
- **Q32** Judge protocol mismatch — metric/value/score の使い分け（本書 §4.2 で解決）

以上。
