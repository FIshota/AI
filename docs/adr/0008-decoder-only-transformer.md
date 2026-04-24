# ADR 0008: HinoMoto はゼロから decoder-only transformer を学習する

- Status: Accepted
- Date: 2026-04-23
- Deciders: honnsipittu

## コンテキスト

自前基盤モデル HinoMoto の実装方式として、以下の選択肢があった。

1. ゼロから decoder-only transformer を設計・事前学習
2. 既存事前学習モデル (Llama, Mistral, Swallow 等) を微調整
3. encoder-decoder (T5 系) を自前訓練
4. state-space model (Mamba 等) を自前訓練

本プロジェクトは単独開発・Intel Mac CPU 学習・データ主権の確保が
強い制約であり、学術的興味と長期保守性が混在する前提。

## 決定

**ゼロから設計した decoder-only transformer** を採用する。
初期サイズ 5.3M params、将来 scaled_v3 でスケール予定。

- 位置エンコーディング: RoPE
- 正規化: RMSNorm
- 活性化: SwiGLU
- Tokenizer: SentencePiece BPE 自前学習

実装は `hinomoto-model/hinomoto/model.py` に配置。

## 理由

- **データ主権**: 事前学習コーパスまで全て自前管理。
  既存モデルを起点にすると、不明なデータで学習された weights に
  依存することになり、P1-P5 の責任の所在が曖昧になる。
- **ライセンス明瞭性**: 既存モデル (Llama 等) は派生ライセンスが複雑で、
  将来 YAMATO の公開条件と衝突しうる。
- **小ささで再訓練可能**: 5.3M params は Intel Mac CPU で現実的に再訓練できる。
  再現性と所有者のコントロールを担保。
- **学習価値**: 単独開発の知的資産として、基盤技術を手の届く範囲に置く。
- **decoder-only の選択**: 対話 / 生成が主用途であり、encoder-decoder の
  複雑性は不要。Mamba は実装・ツール生態系の成熟度でまだ早い。

## 結果 / トレードオフ

- Phase 2 完了時点で PPL ~13.58、反復率 0% を達成 (ADR 0001)。
- 日本語品質は公開モデルに及ばないが、用途 (個人対話 + instruction 応答)
  には足る水準を目指す。
- トレードオフ: 絶対品質は既成モデル微調整より低い。
  この譲歩は主権と透明性のためと明示する。
- scaled_v3 (将来) で params 規模を増やす前提。

## 代替案 (検討して却下)

### 案 A: Llama 3 を LoRA 微調整
却下理由: データ主権・ライセンス不明瞭性。
公開派生 YAMATO を想定すると詰まる。

### 案 B: Swallow / 日本語事前学習済モデル採用
却下理由: 同上 (第三者 weights 依存)。
コーパス隔離 (ADR 0002) の前提も崩れる。

### 案 C: encoder-decoder (T5)
却下理由: 対話 / 生成主用途に対して過剰構造。
現代的対話モデルは decoder-only が主流。

### 案 D: Mamba / SSM
却下理由: 実装・ツール・学術的検証の成熟が不足。Phase 5+ で再検討。

## 参照

- `hinomoto-model/hinomoto/model.py`
- `hinomoto-model/configs/` (モデル寸法)
- `hinomoto-model/README.md`
- ADR 0001 (品質指標)
- ADR 0002 (コーパス隔離)
- ADR 0007 (派生戦略)
