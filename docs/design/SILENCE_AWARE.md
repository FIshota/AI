# Silence-aware — 沈黙を理解する

> HinoMoto 四本柱 #4「沈黙を理解する」の **ai-chan 側実装**。
> 本設計は沈黙を時間ベースでトークン化し、会話履歴と感情モデルに取り込む。

## 1. 動機

従来の会話モデルは発話がない間、状態を更新しない。
一方、家族との暮らしでは **沈黙そのものに意味がある**:

- 気まずい沈黙 — 会話後に言葉が途切れる緊張
- 穏やかな沈黙 — 同じ部屋で別々の作業をしている安心
- 不在の沈黙 — 物理的に近くにいない

ai-chan は沈黙を「イベント」として観測し、

- 会話履歴に刻む (`speaker="_silence_"` の turn)
- 感情モデル (`core/emotion.py`) の更新対象にする

ことで、家族らしい存在感 (「何も言わなくても、いることを分かってくれている」) を獲得する。

## 2. カテゴリと閾値

`SilenceCategory` は 5 段階。閾値は家庭内観察に基づく経験的値。

| カテゴリ | 範囲 | 典型シーン |
|----|----|----|
| `MICRO`  | 3〜15s       | turn 内 pause (読点的な間) |
| `SHORT`  | 15s〜2min    | 考え中・言葉選び |
| `MEDIUM` | 2min〜30min  | 同じ空間での別作業 |
| `LONG`   | 30min〜3h    | 離席 / 集中モード |
| `ABSENT` | 3h超         | 不在 |

- 3s 未満は観測しない (呼吸的 pause でノイズになる)。
- 区間は **半開 `[lo, hi)`** — 境界値は上位カテゴリに属する (テストで固定)。
- 参考文献: 本実装では家庭内会話の経験則を採用。学術的な pause 長分布
  (e.g. Heldner & Edlund 2010) は将来の学習材料として残す。

## 3. モジュール構成

```
core/
├── silence_token.py            # SilenceCategory / SilenceEvent / Classifier / Detector
├── silence_emotion_bridge.py  # apply_silence_to_emotion (immutable update)
└── silence_turn.py             # silence_event_to_turn (履歴 turn への変換)
```

### 3.1 `SilenceDetector`

状態機械:

- `on_user_activity(ts)` — ユーザー発話/入力を通知。直前の沈黙区間を確定 → emit。
- `on_tick(now)`         — 定期的な時刻更新。閾値を跨いだカテゴリに対してのみ emit。
  既に同じ/上位カテゴリを emit 済みなら再発火しない (**long-stay 集約**)。

これにより 3 時間以上放置された ABSENT 状態から復帰しても、
`ABSENT` event は 1 件のみとなる (ログ肥大を防ぐ)。

### 3.2 感情規則

| Category | ambient_context | 変化 |
|---|---|---|
| MICRO   | *               | 影響なし |
| SHORT   | *               | +curiosity 0.02 |
| MEDIUM  | `作業中同席`      | +affection 0.05 |
| MEDIUM  | その他          | 影響なし |
| LONG    | *               | +anxiety 0.05, -energy 0.03 |
| ABSENT  | `就寝中`         | 影響なし (正常な夜間) |
| ABSENT  | その他          | +anxiety 0.15, -happiness 0.10 |

全ての値は `[0, 1]` に clamp され、`EmotionState` の **新しいインスタンス** を返す。
原本は破壊しない。

### 3.3 会話履歴フォーマット

```json
{
  "turn_id":   "<uuid4>",
  "timestamp": "2026-04-24T10:03:00",
  "speaker":   "_silence_",
  "text":      "<silence:medium:180s>",
  "meta": {
    "started_at": "2026-04-24T10:00:00",
    "ended_at":   "2026-04-24T10:03:00",
    "duration_s": 180.0,
    "category":   "medium",
    "ambient_context": "作業中同席"
  }
}
```

`speaker == "_silence_"` でフィルタ可能。text は LLM プロンプト挿入時にも
human-readable で残せる形。

## 4. HinoMoto 連携

四本柱 #4 の沈黙トークンは HinoMoto 側 (model runtime) でも受信される想定。
本モジュールはその **送信側**。受信プロトコル (トークナイザ埋め込み /
sentinel token 化) は `hinomoto-model` 側で別途仕様化される予定。

本実装は `SilenceEvent` を中立的データ構造として提供し、
- `silence_event_to_turn` でテキスト系統へ
- `apply_silence_to_emotion` で感情系統へ

分岐させることで、プロトコル詳細の変更に耐える。

## 5. プライバシー

- **沈黙そのものは観測しない** (マイク/カメラを使わない、時刻のみ)。
- ただし「不在期間 (ABSENT)」が時刻差分から推定されうる。
  生活パターンが推定可能な側面があるため、`logs/` への永続化は **opt-in**。
- デフォルトは揮発性 (プロセス内のみ)。永続化する場合は
  `consent` モジュール経由で明示同意を取得する。

## 6. 将来拡張

- **ambient_context 推定**: マイク/カメラで「作業中」「就寝中」等を自動推定 (別フェーズ)。
  本実装は `ambient_context_provider` コールバックの差し込み点を用意済み。
- **個人差学習**: カテゴリ閾値の個別チューニング (住人ごと)。
- **文脈連動**: 直前の話題の感情値と沈黙カテゴリの組合せで、
  気まずい沈黙 / 穏やかな沈黙 を区別 (現状はどちらも同じ扱い)。

## 7. 非機能要件

- Python 3.9 互換, stdlib のみ
- 全 `@dataclass(frozen=True)`
- `core/emotion.py` は非改変 (読み取りのみ)
- pytest で 15+ ケース (`tests/test_silence_token.py`)
