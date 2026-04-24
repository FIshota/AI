# ADR 0003: 生成時の既定値 repetition_penalty=1.3 / min_gen_chars=5

- Status: Accepted
- Date: 2026-04-23
- Deciders: honnsipittu

## コンテキスト

HinoMoto 初期 SFT (~step 6000-10000) で、生成応答が同一 n-gram を繰り返して
無限ループに陥る現象が頻発した。典型的な症状:

- 「はい。はい。はい。...」 (1-gram loop)
- 「ありがとう ございます。 ありがとう ございます。...」 (3-gram loop)
- EOS に到達せず max_new_tokens まで同語反復で消化

原因は、5.3M パラメータの小規模 decoder-only モデルが low-entropy 状態に
落ちやすいこと、また SFT 初期で EOS 学習が弱いことに由来する。

## 決定

HinoMoto 生成パイプライン (`hinomoto-model/hinomoto/generate.py` および
`ai-chan/core/llm.py` の HinoMotoBridge 経路) の既定値を以下に固定する。

| パラメータ | 既定値 | 理由 |
|---|---|---|
| `repetition_penalty` | **1.3** | 1.0 はループ頻発、1.5 以上は自然さが崩れる |
| `min_gen_chars` | **5** | 極短応答 (「。」だけ等) の EOS 早漏を防ぐ |
| `temperature` | 0.8 (既存) | - |
| `top_p` | 0.9 (既存) | - |

`repetition_penalty` は HuggingFace 標準の logits warping 方式で実装。
`min_gen_chars` に満たない場合は EOS logits を -inf にマスクする。

## 理由

- **1.3 の根拠**: 1.1 / 1.2 / 1.3 / 1.5 で比較測定し、1.3 で反復率が 5% 以下に
  落ち、かつ自然さの主観評価が崩れない閾値であった (RESEARCH_LOG.md 参照)。
- **1.5 以上は副作用**: 正当な繰り返し (敬語、助詞、句読点) まで抑制され、
  文法破綻や語彙の不自然な揺らぎが増える。
- **min_gen_chars=5**: step 初期に「。」「はい」だけで EOS する退行を抑制。
  5 文字は最小限の意味単位。
- **ADR 0001 の評価指標 (反復率 5%以下)** を satisfy する運用デフォルトとして
  必要。

## 結果 / トレードオフ

- SFT step 13050 時点で反復率 ~0% を達成 (ADR 0001 計測)。
- トレードオフ: 意図的な反復表現 (詩・呼びかけ) も一部抑制される。
  API 呼び出し側から override 可能にしており、常用は既定値で十分。
- scaled_v3 (将来、より大きいモデル) では緩和の余地あり、Phase 4 で再検証。

## 代替案 (検討して却下)

### 案 A: no_repeat_ngram_size=3
却下理由: 正当な 3-gram (「よろしくお願い」等) まで禁止され、
敬語表現が崩壊した。

### 案 B: top_k を強くする
却下理由: top_k=20 程度ではループ抑制にならず、top_k=5 まで下げると
応答が単調になる。

### 案 C: beam search
却下理由: 対話応答には不向き (多様性喪失)、かつ CPU 推論で遅い。

## 参照

- `hinomoto-model/hinomoto/generate.py`
- `ai-chan/core/llm.py` (HinoMotoBridge)
- `hinomoto-model/RESEARCH_LOG.md` (repetition penalty sweep)
- ADR 0001 (反復率 5% 以下の指標)
- ADR 0005 (HinoMotoBridge)
