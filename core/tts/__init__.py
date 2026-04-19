"""ai-chan TTS エンジン抽象 (Phase 0.75).

設計方針 (γ 切替式):
  - 既定: pyttsx3 (BSD License, 完全ローカル, 軽量)
  - オプション: VOICEVOX (エンジン別途起動必要, 高音質日本語)
  - フォールバック: macOS `say` / Linux `espeak`
  - 非推奨: edge-tts (GPL-3.0 汚染リスク + Azure 外部送信)

settings.json:
    "voice": {
        "engine": "pyttsx3",    # "pyttsx3" | "voicevox" | "system" | "auto"
        "voicevox": {
            "host": "127.0.0.1",
            "port": 50021,
            "speaker_id": 1      # 1=ずんだもん, etc.
        },
        "pyttsx3": {
            "rate": 180,         # WPM
            "volume": 0.9
        }
    }
"""
from __future__ import annotations

from .engine import TTSEngine, create_tts_engine, EngineSpec, SpeakResult

__all__ = ["TTSEngine", "create_tts_engine", "EngineSpec", "SpeakResult"]
