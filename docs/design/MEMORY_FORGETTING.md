# Memory Forgetting: Ebbinghaus + Pin

## 背景と目的

ai-chan は 10 年単位の長期運用を前提とする。何もしないと memory DB
はひたすら肥大化し、

- ディスク圧迫
- 検索レイテンシ悪化
- 本当に大事な記憶がノイズに埋もれる

という 3 点で劣化する。解決策として、心理学的に裏付けのある
**Ebbinghaus 忘却曲線** に基づく自動減衰と、ユーザーが明示的に
**pin** したエントリの永続保持 を組み合わせたポリシーを導入する。

## 理論的根拠

### Ebbinghaus (1885)

Hermann Ebbinghaus は無意味綴りを用いた自己実験で、記憶保持率が
時間に対して概ね指数的に減衰することを示した。今日的には

```
R(t) = exp(-t / S)
```

- `R(t)`: 時刻 `t` での保持率 (0.0 - 1.0)
- `t`: 最後の想起からの経過時間
- `S`: 記憶強度 (memory strength)

という形で表現される。

### Anderson & Schooler (1991) — rational analysis

John R. Anderson と Lael Schooler は「何を忘れるか」を
**環境統計への合理的適応** として定式化した。過去の出現頻度と
最近性から将来の有用性を推定し、使われそうにない情報を捨てるのは
合理的行動である、という視点。

本実装はこの視点に沿い、**rehearsal (想起)** が記憶強度 `S` を
引き上げる形で組み込んでいる。

### 本実装の式

```
S_eff = S0 * half_life * (1 + rehearsals * boost)
R(t)  = exp(-t / S_eff)
```

デフォルト値:

| パラメータ          | 値    | 意味                                      |
|---------------------|-------|-------------------------------------------|
| `initial_strength`  | 1.0   | S0                                        |
| `half_life_days`    | 7.0   | 未想起で 7 日後に R ≈ 0.37 に減衰する基準  |
| `rehearsal_boost`   | 0.5   | 想起 1 回ごとに S を 50% 伸ばす           |
| `threshold`         | 0.2   | R がこの値未満になると「忘却候補」        |

## Pin 運用

- ユーザーが `is_protected = 1` または `is_core = 1` を立てたエントリは
  `pinned = True` とみなし、どれだけ古くても `retention = 1.0` 扱い。
- pin は「このエージェントのアイデンティティを構成する記憶」や
  「家族としての約束」など、忘れられては困るコアメモリに使う。
- `ForgettingPolicy.should_forget()` は pinned を最優先で判定し、
  他のパラメータがどうであっても常に `False` を返す。

## API

```python
from core.memory_forgetting import (
    ForgettingCurveParams, ForgettingPolicy, MemoryEntry, retention_score,
)

policy = ForgettingPolicy(
    threshold=0.2,
    params=ForgettingCurveParams(half_life_days=7.0, rehearsal_boost=0.5),
)

kept, forgotten = policy.apply(entries, now=datetime.now())
```

- `retention_score(elapsed_days, rehearsals, params) -> float`
- `ForgettingPolicy.should_forget(entry, now) -> bool`
- `ForgettingPolicy.apply(entries, now) -> (kept, forgotten)`

## Sweep スクリプト

```bash
# dry-run (既定)
python scripts/sweep_memory_forgetting.py

# 実際に適用
python scripts/sweep_memory_forgetting.py --apply --threshold 0.2
```

- 忘却候補は `memory_type` を `long` に降格 (hard-delete しない)。
- すべての判定結果は `audit_chain` に追記され、改竄検知可能。

## MemoryCompressor との関係

`core.memory_compressor.MemoryCompressor` は後方互換のために
コンストラクタに `forgetting_policy: Optional[ForgettingPolicy] = None`
を **追加引数** として持つ。既存ロジックは一切変更しておらず、
policy を渡さなければ従来どおり。

追加 API `classify_for_forgetting(entries)` が `(kept, forgotten)`
を返す。実際に DB を書き換えるのは sweep スクリプト側。

## 10 年シミュレーション見積り

モデル:

- 1000 エントリ、毎週ランダム 5 件を想起 (rehearsal_count += 1)
- 10 年 = 520 週
- 既定パラメータ (`half_life_days=7.0`, `threshold=0.2`)

想起頻度に応じた定常状態での retention 分布:

| 想起回数 (期待) | 経過 (日) | R       | 状態       |
|------------------|----------|---------|------------|
| 0                | 3650     | ~0.0    | 忘却       |
| 1                | 365      | ~1e-11  | 忘却       |
| 10               | 90       | ~0.22   | ぎりぎり残存 |
| 50               | 30       | ~0.92   | 強い残存   |
| 任意 (pinned)    | -        | 1.0     | 永続        |

したがって 10 年地平でおおよそ:

- **10 % 前後** (頻繁に想起される + pinned) が残存
- **90 % 前後** が `long` へ降格 (将来さらなる要約対象)

という見積りになる。これは
*1000 → 約 100 アクティブ + 900 アーカイブ*
に落ち着くイメージで、ストレージ爆発を防ぐ上で十分な効き方。

パラメータは `ForgettingCurveParams` を通じて運用時に調整可能。
short-term は `half_life_days=1.0`、long-term (圧縮済み) は
`half_life_days=90.0` のように階層ごとに変えることも想定される。

## テスト

`tests/test_memory_forgetting.py`: 単調減少 / rehearsal boost / pin /
threshold 境界 / policy apply / 0 day / 極端値 を含む 15 ケース。
