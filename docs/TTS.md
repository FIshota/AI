# ai-chan TTS (Text-to-Speech) — Phase 0.75 γ 切替式

## 概要

ai-chan は **完全ローカル動作** を前提とするため、
音声合成エンジンはライセンス・プライバシー・品質のバランスで選択可能です。

## 🎛 対応エンジン一覧

| エンジン | ライセンス | 外部送信 | 品質 | 起動コスト | 既定 |
|---|---|---|---|---|---|
| **pyttsx3** | BSD-3 | なし | ★★☆ | 軽量 | ✅ (default) |
| **VOICEVOX** | LGPL (エンジン) / 各キャラ規約 | なし (localhost) | ★★★★★ | 別途エンジン起動 | オプション |
| **system** (macOS say / espeak) | OS バンドル | なし | ★☆☆ | 軽量 | フォールバック |
| ~~edge-tts~~ | GPL-3.0 (汚染リスク) | **Azure に送信** | ★★★★ | 軽量 | 🚫 非推奨 (Phase 1 削除) |

## 設定方法

`config/settings.json`:

```json
{
  "voice": {
    "engine": "pyttsx3",
    "pyttsx3": {
      "rate": 180,
      "volume": 0.9,
      "voice_id": null
    },
    "voicevox": {
      "host": "127.0.0.1",
      "port": 50021,
      "speaker_id": 1
    }
  }
}
```

## エンジン別セットアップ

### 1. pyttsx3 (既定・何もしなくて OK)

```bash
pip install pyttsx3
```

macOS では内部で `NSSpeechSynthesizer` を呼びます (日本語 Kyoko / Otoya)。
Linux では espeak-ng を経由します。

### 2. VOICEVOX (推奨・高音質)

VOICEVOX エンジンを別プロセスで起動します:

```bash
# Docker で起動 (CPU 版・無料)
docker run -d -p 50021:50021 --name voicevox \
  voicevox/voicevox_engine:cpu-latest

# 動作確認
curl http://127.0.0.1:50021/version
```

その後 `settings.json > voice.engine = "voicevox"` に変更。
キャラクター一覧は `curl http://127.0.0.1:50021/speakers` で確認可能。

**代表的な speaker_id**:
- `1`: 四国めたん (ノーマル)
- `3`: ずんだもん (ノーマル)
- `8`: 春日部つむぎ
- `10`: 雨晴はう

### 3. system (フォールバック専用)

macOS: `say -v Kyoko` / Linux: `espeak-ng -v ja`
品質は低いがネットワーク不要・追加インストール不要。

### 4. ~~edge-tts~~ (非推奨)

**削除予定**。外部送信 + GPL 汚染リスクのため Phase 1 で完全撤去。
現状では `pip install edge-tts` すれば互換レイヤ経由で動作しますが非推奨。

## 自動選択 (engine: "auto")

`auto` の場合、以下の順で試行します:
1. VOICEVOX (127.0.0.1:50021 が応答すれば)
2. pyttsx3 (インストール済みなら)
3. system (macOS say / Linux espeak)
4. noop (全滅時 — ログだけ出して無音)

## 環境変数 override (CI 用)

```bash
AICHAN_TTS_ENGINE=system python3 main.py    # 強制的に system
```

## 開発用 API

```python
from core.tts import create_tts_engine

settings = {"voice": {"engine": "auto"}}
tts = create_tts_engine(settings)
print("resolved:", tts.resolved_name)       # "voicevox" | "pyttsx3" | "system"

result = tts.speak("こんにちは、家族になりましょう", emotion="happy")
print(result)  # SpeakResult(success=True, engine='pyttsx3', duration_sec=1.23)
```

## ライセンス注意

- **pyttsx3**: BSD-3 — 再配布自由
- **VOICEVOX 本体**: LGPL — 動的リンクのみなら OK
- **VOICEVOX キャラ音声**: **各キャラごとの利用規約**あり (商用利用時は要確認)
- **edge-tts**: GPL-3.0 — ai-chan 本体に同梱しない (ユーザー明示選択時のみ)

## Phase ロードマップ

- **Phase 0.75** (現在): γ 切替実装、edge-tts optional 化
- **Phase 1**: edge-tts コード物理削除、neural_tts.py → tts/ へ吸収
- **Phase 2**: 声質学習 (prosody_learner との統合) を新 API に移植
