# 音声認識 (STT) — Phase 1 ドキュメント

## 方針: 完全ローカル・ゼロコスト

ai-chan の音声認識は **faster-whisper** (MIT, CTranslate2 ベース) を使用し、
一度モデルを DL すれば完全オフラインで動作する。クラウド音声 API
(OpenAI Whisper API / Google Cloud STT など) は一切使用しない。

### なぜ faster-whisper なのか

| 選択肢 | ライセンス | ローカル | 精度 (ja) | 採用 |
|:--|:--|:--:|:--:|:--:|
| faster-whisper | MIT | ○ | 高 (Whisper large-v3 相当) | ✓ |
| whisper.cpp | MIT | ○ | 高 | 代替候補 |
| openai-whisper (原実装) | MIT | ○ | 高 | — (PyTorch 依存が重い) |
| OpenAI Whisper API | — | × | 最高 | × (有料・送信) |
| Google Cloud STT | — | × | 高 | × (有料・送信) |
| SpeechRecognition + Google Web | — | × | 中 | × (送信) |

採用理由:
- CTranslate2 による int8 量子化で **CPU 推論が 4x 速い**
- 依存が軽い (PyTorch 不要)
- arm64 macOS / x86_64 Linux 両対応
- 音声データはすべて一時ファイル経由でローカル処理、外部送信ゼロ

## モデルサイズ

| size | VRAM/RAM | 精度 | 速度目安 |
|:--|:--|:--:|:--|
| tiny   |  ~75MB | 低 | 10x RT |
| base   | ~140MB | 中 |  7x RT |
| **small** (default) | ~460MB | 高 |  4x RT |
| medium | ~1.5GB | 高+ |  2x RT |
| large-v3 |  ~3GB | 最高 | 1x RT |

既定は `small` (コスパ最良)。`core/stt.py::STTEngine(model_size="small")`。

初回起動時に HuggingFace Hub (`Systran/faster-whisper-small`) から
`model.bin` を DL してキャッシュ (`~/.cache/huggingface/hub/`)。以降は
オフラインで動作する。

## プライバシー

- 録音バッファは `numpy.float32` 配列としてメモリ上のみに保持
- Whisper への入力は `tempfile.NamedTemporaryFile(suffix=".wav")` を使い、
  `_transcribe_*` の `finally` で `os.unlink` により即座に削除
- 連続リスニングモードでも、認識後のオーディオは直ちに破棄

## 連続リスニング (Phase C)

`STTEngine.start_continuous_listening(on_text=callback)` で開始。

- 無音判定: 振幅 `silence_threshold` 未満 かつ 継続時間 `silence_duration` 秒
- 最小発話: `min_speech_duration` 秒以上 (ノイズ弾き)
- TTS 発話中の誤認識防止: `pause_continuous_listening()` を TTS 再生開始時に呼ぶ

## 複数話者 (Phase D)

`voice_id` を有効化すると MFCC ベースの話者識別と連携して
`list[SpeakerUtterance]` を返す。話者閾値は `VoiceIDManager.match_threshold`。

## 依存

```
faster-whisper>=1.0
sounddevice>=0.5
soundfile>=0.13
```

いずれも PyPI から pip 取得可能で、完全にオープンソース。

## 動作確認

```bash
python3 -c "
from core.stt import STTEngine
e = STTEngine(model_size='tiny')   # テスト用に tiny
e.load_model_async()
import time
for _ in range(60):
    if e.is_ready(): break
    time.sleep(1)
print('status:', e.get_status())
"
```

## Phase 1 完了定義

- [x] faster-whisper 採用 (MIT, ローカル)
- [x] モデルは DL 後オフライン
- [x] 一時 WAV は `finally` で確実削除
- [x] 連続リスニング + 話者識別統合
- [ ] (Phase 2) Metal GPU 対応 (faster-whisper の CoreML backend 検証)
