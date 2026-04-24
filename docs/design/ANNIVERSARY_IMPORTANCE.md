# Anniversary 自動重要度推定 設計書

## 概要

`core/anniversary.py` の Anniversary (記念日) エントリに対して、過去会話ログから
抽出した特徴量から **0.0 - 1.0 の連続スコア** を推定し、
`low / medium / high / critical` の 4 段階 Bucket に離散化する。

目的:

- 通知タイミング / 強度の調整 (critical なら朝イチで祝う、low なら静かに記録のみ、等)
- 手動設定の初期値サジェスト
- 重要度ドリフト検出 (定期再計算)

## 特徴設計

`AnniversaryFeatures` は `@dataclass(frozen=True)` で不変化されている。

| 特徴量 | 型 | 意味 |
|---|---|---|
| `keyword` | str | Anniversary label / keyword |
| `mention_count` | int | 過去会話中に該当キーワードが言及された回数 |
| `mean_valence` | float (-1.0 ~ 1.0) | 言及された会話の平均感情価 |
| `first_seen_at` | str (ISO8601) | 初出タイムスタンプ |
| `last_seen_at` | str (ISO8601) | 最終出現タイムスタンプ |
| `session_total_minutes` | float | 関連会話の累積継続分 |

### 特徴量ごとの正規化

1. **mention_count**
   `log1p(mention_count) / log1p(30)` で対数飽和。30 回で概ね 1.0。
   さらに `session_total_minutes / 600min` を 25% 加重で加算
   (会話継続時間が長い = 話題として粘着性が高いと解釈)。
2. **mean_valence**
   `|valence|` で絶対値化。強い負の感情 (例: 喪失の記念日) も強い正の感情
   (例: 結婚記念日) と同等に重要として扱う。
3. **recency**
   `last_seen_at` から現在までの経過日数に対して **半減期 90 日** の指数減衰
   `0.5 ** (days / 90)`。パース失敗時は 0.0。

## 重み根拠

重み付き線形結合:

```
score = 0.40 * mention_norm
      + 0.40 * |valence_norm|
      + 0.20 * recency_norm
```

| 重み | 根拠 |
|---|---|
| mention 40% | 「記念日らしさ」を支える最も直接的シグナル。ただし単独では "単なる頻出語" とも区別がつかないため 50% 未満に抑える |
| valence 40% | 感情強度は人間が記念日と感じる根本条件。mention と同等に重視 |
| recency 20% | 補助。古い思い出でも重要度が落ちすぎないよう控えめ。ただしドリフト検出のシグナルとしては有効 |

重みは合計 1.0 に正規化済みで、最大特徴量では `score` が 1.0 に近づく。

## Bucket 閾値

| Bucket | 範囲 | 想定挙動 |
|---|---|---|
| LOW | `[0.00, 0.25)` | 記録のみ、通知しない |
| MEDIUM | `[0.25, 0.55)` | 当日 1 回だけ柔らかく言及 |
| HIGH | `[0.55, 0.80)` | 朝と夜に祝う |
| CRITICAL | `[0.80, 1.00]` | 前日リマインド + 当日複数回祝う |

閾値はヒューリスティック初期値。実運用データを集めて `scripts/recalibrate_anniversaries.py`
で分布を観察しチューニングする想定。

## 手動上書き UX

自動推定は `anniversary` エントリの **`auto_importance`** フィールドに書き込まれる。
手動の重要度設定 (`manual_importance`) があればそれを優先するのが原則:

```json
{
  "id": "a1b2c3",
  "label": "記念の日",
  "month": 6,
  "day": 1,
  "auto_importance": {
    "score": 0.73,
    "bucket": "high",
    "updated_at": "2026-04-24T03:00:00+00:00"
  },
  "manual_importance": "critical"
}
```

- 上書き方針: `manual_importance` が存在する限り、`auto_importance` は**参考値**として保持され
  通知ロジックでは `manual_importance` を採用する。
- UI での提示:
  - `auto_importance.bucket != manual_importance` のとき、差分を「AI の推定はこう変わっています」
    と表示して再考を促す。
- 再計算コマンド:
  ```bash
  python scripts/recalibrate_anniversaries.py           # dry-run (artifacts/ にレポート)
  python scripts/recalibrate_anniversaries.py --apply   # DB 反映
  ```

## 非破壊性

`AnniversaryManager.attach_auto_importance()` は既存フィールドに触れず `auto_importance` のみを
append する。旧バージョンは当該キーを無視するだけで動作可能。

## 今後の拡張

- キーワード共起スコア (他の記念日との近さ) を追加
- 周期性検出 (年次 / 月次 / 不定期)
- ユーザー修正履歴からの重みベイズ更新
