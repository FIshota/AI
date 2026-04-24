# ai-chan Public Roadmap

**最終更新**: 2026-04-23

このロードマップは **公開用** です。内部専用の意思決定 (Kill-Switch 設計、悪用防止上の判断、非公開な派生モデルの運用方針など) は別文書 (`VISION_INTERNAL.md`) で管理しています。

---

## 現状フェーズ

| フェーズ | 状況 | 主要マイルストーン |
|---|---|---|
| **Phase 0** — 土台固め | ✅ 完了 | core/memory/emotion/llm/ui の 5 層分離、感情基盤、プライバシー暗号化 |
| **Phase 1** — 家族 AI としての完成度 | ✅ 完了 | Desktop Pet, 記念日, 日記, クリップボード/スクリーンショット観察, 学習ループ |
| **Phase 2** — 自社基盤モデル PoC 統合 | 🔄 **進行中** | HinoMoto LM を `LLMEngine` の 1 バックエンドとして差し込み、fp16 量子化で実用サイズに |
| **Phase 3** — 本番統合 | ⏳ 次 | ai-chan の既定応答を HinoMoto に切替、外部 LLM は緊急フォールバック化 |
| **Phase 4** — スケールアップ | ⏳ Windows 到着後 | 5.3M → 40M+ (scaled_v3) の基盤再訓練、品質レベル底上げ |
| **Phase 5+** — 公式派生モデル群 | 🗓 数年後 | 公的に発表する派生モデル群の段階的リリース (商用は年単位先) |

---

## Phase 2 → Phase 3 遷移条件 (現時点の判定基準)

以下がすべて満たされた時点で Phase 3 昇格:

- [x] HinoMoto モデル実装 (Transformer from scratch)
- [x] 学習パイプライン稼働 (pretrain + SFT)
- [x] `HinoMotoBridge` 経由で ai-chan から推論呼び出し成功
- [x] fp16 量子化が無劣化で動作 (PPL +0.01% 以下)
- [x] Corpus isolation guard 稼働 (個人記憶の学習混入をブロック) + CI
- [x] repetition penalty チューニングで反復ループ回避
- [x] **SFT continue 20k step 完走** (2026-04-23 16:57 JST 完走、best_loss=1.667)
- [ ] **品質指標の到達** (※指標自体を再検討中 — 下記参照)
  - PPL 10- 未満 (jawiki_val 上) ← **現状 13.58 (13050) / 13.71 (20000) で未達**。追加 SFT で PPL 微悪化 (+0.13) → 20k 延長は heldout に対しては改善なし
  - 反復率 5% 以下 ← repetition_penalty=1.3 + min_gen_chars=5 で回避済
  - BLEU 0.45+ ← **要検討**: heldout_eval_200 は base 用の continuation prompts で instruction-tuned SFT には不適切 (SFT 13050/20000 ともに 0.0031 で同値、unigram fallback のノイズ域)。→ instruction 形式の holdout 作成 or 代替指標へ移行 (詳細: `docs/adr/0001-sft-eval-metric.md`)

**2026-04-23 比較 eval 結果** (`artifacts/sft_comparison_13050_vs_20000.json`):

| ckpt | BLEU | PPL |
|---|---|---|
| 13050 (sft_dolly_v1 final) | 0.0031 | **13.58** |
| 20000 (sft_dolly_v1_continue) | 0.0031 | 13.71 |

示唆: 追加 6,950 step は heldout PPL を改善せず、むしろ僅かに劣化。次の SFT v2 は (a) データ split 厳密化 (train/val/test 重複排除) と (b) validation loss の実測ベース (sft_dolly_v2.sh の `--val-every` 経由) で実施する。
- [ ] 既定応答を HinoMoto に切替えた状態で 1 週間連続運用無事故
- [ ] 外部 LLM (MLX / llama.cpp) を緊急フォールバック専用に降格

---

## 近傍のマイルストーン

### 🎯 Phase 2 残タスク (今月中)

1. **SFT continue 完走 + before/after 評価** (`scripts/eval_hinomoto.py`)
2. **HinoMotoBridge** の切替方針を `core/llm.py` でデフォルト化するオプション導入
3. **24 時間連続運用テスト** (1 日の会話ログから reply を HinoMoto にリプレイ)

### 🎯 Phase 3 初期タスク (Windows 機到着前)

1. ai-chan 既定 backend を `hinomoto` に切替 (環境変数でフォールバック可能)
2. 長期会話記憶と HinoMoto の併用テスト (memory は外部 episodic、モデルは stateless 保持)
3. エラー時の退避 (HinoMoto → MLX → llama.cpp → canned) 動作確認

### 🎯 Phase 4 準備 (Windows 機到着後)

`docs/RUNBOOK_WINDOWS_SCALED.md` (hinomoto-model 側) に集約。
主要項目:
- scaled_v3 (d_model=512 / n_layers=12) で再事前学習 30k step (GPU で ~3h)
- 同じアーキで SFT 40k step
- int8 量子化を Windows で初試行 (macOS Intel はエンジン非対応)
- ai-chan 側差し替え + 品質ベンチ再測定

---

## 周辺モデル群の扱い

- **HinoMoto** (基盤) — 学習データ中央管理、派生モデルに分岐
- **公式派生 A** (一般向け) — 将来の家庭用モデル。**リリースは数年単位で先**
- **公式派生 B** (公共向け) — 将来の公的発表用モデル。**リリースは数年単位で先**
- **内部専用の派生モデル** — 非公開。このロードマップでは扱わない

派生モデル間のデータ遮断原則 (個人情報が基盤に還流しない) は `docs/VISION.md` 参照。

---

## 長期方針

**商用展開は数年後**。現時点のゴールは:

1. モデルを十分に大きく育てる (scaled_v3 → さらに上)
2. 日本語特化の評価基盤を整備する
3. プライバシー・中立性・説明可能性を技術的に裏付ける

スピードよりも根拠の積み上げを優先する。

---

## 参照文書

| 文書 | 内容 |
|---|---|
| `VISION.md` | 公開ビジョン (派生モデルの役割と隔離原則) |
| `VISION_INTERNAL.md` | 内部専用 (非公開 / `.gitignore` 済み) |
| `ARCHITECTURE.md` | システム構成 |
| `SECURITY.md` / `THREAT_MODEL.md` | セキュリティ方針 |
| `MEMORY_HONESTY.md` | 記憶の正直性原則 |
| `MODEL_POLICY.md` | 外部モデル利用方針 |
| `docs/security/OUTDATED_AUDIT_YYYYMMDD.md` | 依存監査 (日次) |
