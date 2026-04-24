# ADR 0009: 初期 SFT コーパスは Dolly-15k-ja / 分割マニフェスト固定

- Status: Accepted
- Date: 2026-04-23
- Deciders: honnsipittu

## コンテキスト

HinoMoto の Phase 2 (instruction tuning) で使用する SFT コーパスを選定する
必要があった。要件:

- 日本語 instruction-response 対
- ライセンスが明瞭 (ADR 0008 のライセンス明瞭性方針に沿う)
- サイズが単独開発で扱える規模
- 品質がベンチ可能

候補:
- Dolly-15k-ja (CC-BY-SA 3.0)
- databricks-dolly-15k (英語、翻訳ベース)
- ichikara-instruction (CC BY-NC-SA、商用不可)
- oasst1-ja (Apache 2.0 だが品質ばらつき)

## 決定

**Dolly-15k-ja (CC-BY-SA 3.0)** を初期 SFT コーパスとして採用する。

分割は `scripts/build_dolly_splits.py` で以下を固定:
- train / val / test = 13500 / 750 / 750
- 分割は決定的 (seed=20260101 固定 / ハッシュ順ソート)
- 各ファイルの sha256 を `data/sft/manifest.json` に記録
- CI / eval 時にマニフェストの sha256 を検証、不一致なら fail

## 理由

- **ライセンス**: CC-BY-SA 3.0 は公開派生 YAMATO で扱いやすい
  (ichikara は NC のため公開不可)。
- **品質**: 人手作成ベースでノイズが少ない。
- **再現性**: sha256 マニフェストで「同じ split で学習したか」が保証される。
  分割バグを境に評価値が動く事故を排除。
- **評価セパレーション**: ADR 0001 で定義した BLEU 参考計測 (Dolly holdout 500)
  の基盤となる。

## 結果 / トレードオフ

- `data/sft/train.jsonl` / `val.jsonl` / `test.jsonl` および
  `manifest.json` が確立。
- SFT 13050 step で ADR 0001 の指標セット (PPL 13.58 / 反復率 ~0%) を達成。
- トレードオフ: Dolly-15k-ja は量が限定的。Phase 4 で合成データ / 追加
  日本語 instruction corpus の導入が必要。
- CC-BY-SA の SA 条項により、学習済みモデルの公開時にライセンス継承
  (または免除解釈の明記) が必要。法務整理は YAMATO 公開前に実施。

## 代替案 (検討して却下)

### 案 A: ichikara-instruction
却下理由: NC 条項。公開派生 YAMATO (ADR 0007) と衝突。

### 案 B: OpenAssistant ja 部分のみ
却下理由: 品質ばらつきが大きく、手選別コストが単独開発で重い。

### 案 C: 自前で instruction データを手作成
却下理由: スケール不可能。将来少量の高品質カスタム部分を追加する路線は残す。

### 案 D: 分割を決定的にせず毎回ランダム
却下理由: 評価比較が崩壊する。ADR 0001 の指標が再現しない。

## 参照

- `hinomoto-model/data/sft/` (train/val/test/manifest)
- `hinomoto-model/scripts/build_dolly_splits.py`
- `hinomoto-model/README.md`
- ADR 0001 (評価指標)
- ADR 0007 (公開派生のライセンス要件)
- ADR 0008 (ライセンス明瞭性方針)
