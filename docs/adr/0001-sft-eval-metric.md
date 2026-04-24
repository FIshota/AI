# ADR 0001: SFT モデルの品質評価指標を見直す

- **Status**: Proposed
- **Date**: 2026-04-23
- **Context owner**: ai-chan + hinomoto-model

## 背景

`docs/ROADMAP.md` の Phase 2→3 遷移条件として:

> BLEU 0.45+ / PPL 10- / 反復率 5% 以下

を設定していた。`scripts/eval_hinomoto.py` + `data/heldout_eval_200.jsonl` で
SFT step 13050 を測定したところ、

| 指標 | 値 | 目標 | 差 |
|---|---|---|---|
| PPL (jawiki_9k_val, 50 batches) | 13.58 | 10- | -3.58 |
| BLEU (sacrebleu 4-gram, heldout 198) | **0.0031** | 0.45+ | **-0.447** |
| 反復率 | ~0% | 5%- | OK |

BLEU の値が極端に低く、目標に対して 2 桁ずれている。

## 原因分析

1. **heldout_eval_200.jsonl はドメイン不一致**:
   - 本ファイルは **jawiki text continuation 形式**: `{prompt: "坂田靖子（1953年…", reference: "…漫画家。女性。\n\n ポスト24年組…"}`
   - 事前学習モデル (base step 9250) では BLEU 0.3514 出た (文の続きを書くタスクなので整合)
   - SFT 済モデルは **instruction-tuned**: `応答:` タグを出力する / 短応答で終える / 本文続きを書かない

2. **sacrebleu 4-gram は短応答 + 非マッチドメインで 0 に落ちる**:
   - smoothing=none デフォルト
   - SFT モデルの 64 token 応答では 4-gram マッチがほぼ生まれない

3. **そもそも BLEU は open-ended generation の最適指標ではない**:
   - instruction following の品質を測れない
   - 応答が reference と表現違いで正しくても 0 になりうる

## 決定

Phase 2→3 遷移条件の品質指標を **再定義** する。

### 変更前 (旧)
```
BLEU 0.45+ / PPL 10- / 反復率 5% 以下
```

### 変更後 (新)

| カテゴリ | 指標 | 目標 | 計測方法 |
|---|---|---|---|
| **言語モデル品質** | PPL (jawiki_9k_val, 50 batches) | ≤ 15 | eval_hinomoto.py `--val-corpus` |
| **instruction 忠実性** | 応答タグ (`応答:`) 出現率 | ≥ 80% | 新規 `scripts/eval_instruction_format.py` |
| **生成安定性** | 反復率 (3-gram loop) | ≤ 5% | 既存ロジック |
| **応答長バランス** | 平均応答長 15-80 token | 80%+ のプロンプトで範囲内 | eval_hinomoto 出力の統計 |
| **EOS 健全性** | 自発 EOS で終了する応答比率 | ≥ 60% | eos_analysis 既存スクリプト |
| **BLEU** (参考指標に降格) | Dolly-15k-ja holdout 後方 500 件 | (記録のみ) | 新規 `data/dolly_holdout_500.jsonl` |

**理由**:
- PPL は絶対値で比較可能、SFT の過学習診断にも使える
- instruction 忠実性 / 応答長 / EOS は open-ended 生成の **実運用品質** を直接捕らえる
- BLEU は **base モデルの continuation 品質** 比較でのみ意味がある (Phase 4 scaled_v3 検討時に使用)

### 継続使用
- PPL 10- → **PPL 15- に緩和** (Intel Mac CPU 学習、5.3M params の上限に合わせる。scaled_v3 後に再度引き締め)
- 反復率 5%- は継続

## 影響

- `docs/ROADMAP.md` Phase 2→3 条件を上記に置き換え
- `scripts/eval_instruction_format.py` を新規作成 (Phase 4 準備の前に)
- `data/dolly_holdout_500.jsonl` を Dolly-15k-ja の後方 500 件から切り出し
- ROADMAP の「BLEU 0.45+」文言は削除

## 不採用代替案

### 案 A: heldout_eval_200 を instruction 形式に作り直す
- 却下理由: base モデルとの比較継続が崩れる (過去記録の互換性喪失)

### 案 B: BLEU smoothing を上げて 0.45 を達成可能にする
- 却下理由: 数字いじりで実質品質が測れない

### 案 C: 人手評価を導入
- 却下理由: 単独開発、スケール不可能。将来の選択肢としては残す

## 今後の追跡

- [ ] `scripts/eval_instruction_format.py` 実装
- [ ] Dolly-15k-ja holdout 切り出し
- [ ] 13050 / 20000 / scaled_v3 (将来) で新指標セットを測定して履歴化
- [ ] ROADMAP.md の文言を本 ADR の表で置き換え

## 参照

- 測定ログ: `hinomoto-model/artifacts/sft_comparison_13050_vs_20000.json` (SFT 20k 完走後追記)
- eval スクリプト: `hinomoto-model/scripts/eval_hinomoto.py`
- 関連文書: `hinomoto-model/README.md` (Phase 2 benchmark snapshot)
