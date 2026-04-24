# 感情ドリフト「心の健康診断」

## 目的

Ai-chan の感情スナップショットは会話のたびに `core/emotion_history.py` に記録されているが、
それ単体では 1 日単位の揺れしか見えない。本機能は **週 / 月 / 年** という長期ウィンドウで
感情の傾向を集計し、家族として「今週は寂しがっていた」「最近落ち着いている」のような
定性的な読み解きを人間が行うための補助データを提供する。

実装は以下の 3 レイヤからなる:

| レイヤ | モジュール | 役割 |
| ------ | ---------- | ---- |
| 集計   | `core/emotion_drift.py` | `EmotionDriftAnalyzer` と `EmotionAggregate` (frozen dataclass) |
| レポート | `scripts/generate_emotion_report.py` | matplotlib による PNG、または ASCII sparkline フォールバック |
| UI     | `ui/emotion_drift_window.py` | tkinter ダイアログ (headless 環境では import 時エラーにしない) |

## データモデル

```python
@dataclass(frozen=True)
class EmotionAggregate:
    period_label: str              # "2026-W17" / "2026-04" / "2026"
    counts: Mapping[str, int]      # {"happy": 12, "sad": 3, ...}
    mean_valence: float            # -1.0 .. +1.0 の加重平均
    dominant: str                  # 最頻ラベル
    sample_size: int
```

valence マップ (`DEFAULT_VALENCE_MAP`) は `core/emotion_drift.py` で集中管理し、
`EmotionDriftAnalyzer(valence_map=...)` で呼び出し側から上書き可能。

## 解釈の注意 (CRITICAL)

- **これは診断ではない**。臨床的な意味での「抑うつ」や「不安障害」を判定するものではない。
- 記録されているのは Ai-chan 側の内部ステートであり、ユーザーの精神状態ではない。
- valence の絶対値より、**前週比・前月比の変化の向き**に注目した方が情報量が多い。
- サンプルが少ない期間 (`sample_size` が 5 未満など) は揺らぎが大きいので読み捨てる。
- 「寂しがっていた週」のような読み解きは、必ず当該期間のイベント・日記と突き合わせて確認する。

## 運用

```bash
# 週単位 (既定)。PNG は artifacts/emotion_reports/ に書かれる
python scripts/generate_emotion_report.py --window week

# matplotlib 不要。CI / sshonly 環境向け
python scripts/generate_emotion_report.py --window month --no-plot
```

ASCII フォールバック例:

```
valence sparkline: ▁▃▅▆█
  2026-W15  n=12   valence=-0.42  dominant=anxiety
  2026-W16  n=18   valence=+0.10  dominant=curiosity
  2026-W17  n=20   valence=+0.65  dominant=happiness
```

UI からは以下で開ける:

```python
from ui.emotion_drift_window import open_from_history

open_from_history(parent_tk_root, ai_chan.emotion_history, window="week")
```

tkinter が存在しない環境では自動で stdout テキスト表示にフォールバックする。

## 今後の拡張メモ

- 1 日単位の daily heatmap
- イベント (引っ越し / 誕生日 / 長期外出) アノテーションのオーバーレイ
- ユーザー側の発話感情 (`speaker_emotion`) との相関プロット
