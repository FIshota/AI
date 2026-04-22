"""TTS エンジン抽象 + ファクトリ (Phase 0.75 / γ 切替式).

エンジン選択順序 (settings > engine が "auto" の場合):
    1. VOICEVOX (対応 host が応答する場合)
    2. pyttsx3 (インストール済みの場合)
    3. system (macOS `say` / Linux `espeak-ng`)

明示指定 (settings.json > voice.engine):
    "pyttsx3" | "voicevox" | "system" | "edge" (非推奨) | "auto"
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


@dataclass(frozen=True)
class SpeakResult:
    """speak() の結果を表す不変データ。"""
    success: bool
    engine: str
    duration_sec: float = 0.0
    error: Optional[str] = None
    audio_path: Optional[Path] = None


@dataclass(frozen=True)
class EngineSpec:
    """エンジン設定の不変データ。"""
    name: str                        # "pyttsx3" | "voicevox" | "system" | "edge" | "auto"
    voicevox_host: str = "127.0.0.1"
    voicevox_port: int = 50021
    voicevox_speaker_id: int = 1
    pyttsx3_rate: int = 180          # WPM
    pyttsx3_volume: float = 0.9
    pyttsx3_voice_id: Optional[str] = None


class TTSBackend(Protocol):
    """TTS バックエンドのインターフェイス。"""
    name: str

    def available(self) -> bool:
        """このバックエンドが現環境で使えるか。"""
        ...

    def speak(self, text: str, emotion: str = "neutral") -> SpeakResult:
        """テキストを発話する。"""
        ...


# ─── pyttsx3 バックエンド ────────────────────────────────────

class Pyttsx3Backend:
    name = "pyttsx3"

    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec
        self._engine = None

    def available(self) -> bool:
        try:
            import pyttsx3  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure_engine(self):
        if self._engine is None:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.spec.pyttsx3_rate)
            self._engine.setProperty("volume", self.spec.pyttsx3_volume)
            if self.spec.pyttsx3_voice_id:
                self._engine.setProperty("voice", self.spec.pyttsx3_voice_id)
        return self._engine

    def speak(self, text: str, emotion: str = "neutral") -> SpeakResult:
        import time
        start = time.monotonic()
        try:
            eng = self._ensure_engine()
            # 感情に応じて rate を微調整 (簡易プロソディ)
            base_rate = self.spec.pyttsx3_rate
            rate_map = {
                "excited": base_rate + 30, "happy": base_rate + 15,
                "sad": base_rate - 30, "whisper": base_rate - 40,
                "angry": base_rate + 10, "loving": base_rate - 10,
                "calm": base_rate - 10, "neutral": base_rate,
            }
            eng.setProperty("rate", rate_map.get(emotion, base_rate))
            eng.say(text)
            eng.runAndWait()
            return SpeakResult(success=True, engine=self.name,
                               duration_sec=time.monotonic() - start)
        except Exception as e:
            logger.warning("pyttsx3 speak failed: %s", e)
            return SpeakResult(success=False, engine=self.name,
                               duration_sec=time.monotonic() - start,
                               error=str(e))


# ─── VOICEVOX バックエンド ───────────────────────────────────

class VoiceVoxBackend:
    name = "voicevox"

    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec
        self._base = f"http://{spec.voicevox_host}:{spec.voicevox_port}"

    def available(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self._base}/version", timeout=0.5)
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def speak(self, text: str, emotion: str = "neutral") -> SpeakResult:
        import tempfile
        import time
        import requests
        start = time.monotonic()
        try:
            # 1. audio_query
            r1 = requests.post(
                f"{self._base}/audio_query",
                params={"text": text, "speaker": self.spec.voicevox_speaker_id},
                headers={"Accept": "application/json"},
                timeout=5,
            )
            r1.raise_for_status()
            query = r1.json()

            # 感情プロソディ
            if emotion in ("excited", "happy"):
                query["speedScale"] = 1.15
                query["pitchScale"] = 0.03
            elif emotion in ("sad", "whisper"):
                query["speedScale"] = 0.90
                query["volumeScale"] = 0.85
            elif emotion == "angry":
                query["volumeScale"] = 1.1

            # 2. synthesis
            r2 = requests.post(
                f"{self._base}/synthesis",
                params={"speaker": self.spec.voicevox_speaker_id},
                json=query,
                headers={"Accept": "audio/wav"},
                timeout=30,
            )
            r2.raise_for_status()
            wav = r2.content

            # 3. 再生
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav)
                wav_path = Path(f.name)
            self._play(wav_path)
            try:
                wav_path.unlink()
            except Exception:
                pass

            return SpeakResult(success=True, engine=self.name,
                               duration_sec=time.monotonic() - start)
        except Exception as e:
            logger.warning("voicevox speak failed: %s", e)
            return SpeakResult(success=False, engine=self.name,
                               duration_sec=time.monotonic() - start, error=str(e))

    @staticmethod
    def _play(wav: Path) -> None:
        if IS_MAC:
            subprocess.run(["afplay", str(wav)], check=False)
        elif IS_LINUX:
            for player in ("aplay", "paplay", "play"):
                if shutil.which(player):
                    subprocess.run([player, str(wav)], check=False)
                    return
        else:
            # Windows: 将来対応
            pass


# ─── System バックエンド (macOS say / Linux espeak) ──────────

class SystemBackend:
    name = "system"

    def available(self) -> bool:
        if IS_MAC:
            return bool(shutil.which("say"))
        if IS_LINUX:
            return bool(shutil.which("espeak-ng") or shutil.which("espeak"))
        return False

    def speak(self, text: str, emotion: str = "neutral") -> SpeakResult:
        import time
        start = time.monotonic()
        try:
            if IS_MAC:
                # macOS 標準の Kyoko (日本語) を優先
                cmd = ["say", "-v", "Kyoko", text]
                subprocess.run(cmd, check=False, timeout=30)
            elif IS_LINUX:
                bin_ = shutil.which("espeak-ng") or shutil.which("espeak")
                if not bin_:
                    return SpeakResult(success=False, engine=self.name,
                                       error="espeak not installed")
                subprocess.run([bin_, "-v", "ja", text], check=False, timeout=30)
            else:
                return SpeakResult(success=False, engine=self.name,
                                   error="unsupported OS")
            return SpeakResult(success=True, engine=self.name,
                               duration_sec=time.monotonic() - start)
        except Exception as e:
            return SpeakResult(success=False, engine=self.name,
                               duration_sec=time.monotonic() - start, error=str(e))


# ─── ファクトリ ───────────────────────────────────────────

class TTSEngine:
    """上位 API。settings.json の値を解決して適切なバックエンドを選択する。"""

    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec
        self._backend: Optional[TTSBackend] = None
        self._resolved_name: Optional[str] = None

    @property
    def backend(self) -> TTSBackend:
        if self._backend is None:
            self._backend = self._resolve()
        return self._backend

    @property
    def resolved_name(self) -> str:
        _ = self.backend  # ensure resolved
        return self._resolved_name or "unknown"

    def _resolve(self) -> TTSBackend:
        name = self.spec.name.lower()

        candidates: list[TTSBackend]
        if name == "pyttsx3":
            candidates = [Pyttsx3Backend(self.spec), SystemBackend()]
        elif name == "voicevox":
            candidates = [VoiceVoxBackend(self.spec), Pyttsx3Backend(self.spec), SystemBackend()]
        elif name == "system":
            candidates = [SystemBackend()]
        elif name == "edge":
            # 非推奨 — 互換のため残す
            logger.warning("[TTS] 'edge' is DEPRECATED (GPL risk + Azure transmission). "
                           "Phase 1 で削除予定。")
            try:
                from core.neural_tts import create_neural_tts, EDGE_TTS_AVAILABLE
                if EDGE_TTS_AVAILABLE:
                    return _EdgeCompat(create_neural_tts())
            except Exception as e:
                logger.warning("edge fallback failed: %s", e)
            candidates = [Pyttsx3Backend(self.spec), SystemBackend()]
        else:  # "auto" or unknown
            candidates = [
                VoiceVoxBackend(self.spec),
                Pyttsx3Backend(self.spec),
                SystemBackend(),
            ]

        for be in candidates:
            if be.available():
                self._resolved_name = be.name
                logger.info("[TTS] resolved backend: %s (requested: %s)", be.name, name)
                return be

        # Nothing worked — return a no-op that always fails politely
        logger.warning("[TTS] no backend available; speech will be silent")
        self._resolved_name = "noop"
        return _NoopBackend()

    def speak(self, text: str, emotion: str = "neutral") -> SpeakResult:
        return self.backend.speak(text, emotion)


class _NoopBackend:
    name = "noop"

    def available(self) -> bool:
        return True

    def speak(self, text: str, emotion: str = "neutral") -> SpeakResult:
        logger.info("[TTS/noop] (would speak): %s", text[:60])
        return SpeakResult(success=False, engine=self.name, error="no backend")


class _EdgeCompat:
    """既存 neural_tts.py を新 interface にアダプト (移行用)。"""
    name = "edge"

    def __init__(self, old_engine) -> None:
        self._old = old_engine

    def available(self) -> bool:
        return True

    def speak(self, text: str, emotion: str = "neutral") -> SpeakResult:
        import time
        start = time.monotonic()
        try:
            # 旧 API: synthesize() など — ケースバイケースで呼ぶ
            if hasattr(self._old, "speak"):
                self._old.speak(text)
            elif hasattr(self._old, "synthesize"):
                self._old.synthesize(text)
            return SpeakResult(success=True, engine=self.name,
                               duration_sec=time.monotonic() - start)
        except Exception as e:
            return SpeakResult(success=False, engine=self.name,
                               duration_sec=time.monotonic() - start, error=str(e))


def create_tts_engine(settings: dict | None = None) -> TTSEngine:
    """settings.json の 'voice' セクションから TTSEngine を構築する。"""
    settings = settings or {}
    voice = settings.get("voice", {}) if isinstance(settings, dict) else {}
    vv = voice.get("voicevox", {}) or {}
    pt = voice.get("pyttsx3", {}) or {}

    # 環境変数で override 可能 (CI 用)
    engine_name = os.environ.get("AICHAN_TTS_ENGINE") or voice.get("engine", "auto")

    spec = EngineSpec(
        name=engine_name,
        voicevox_host=vv.get("host", "127.0.0.1"),
        voicevox_port=int(vv.get("port", 50021)),
        voicevox_speaker_id=int(vv.get("speaker_id", 1)),
        pyttsx3_rate=int(pt.get("rate", 180)),
        pyttsx3_volume=float(pt.get("volume", 0.9)),
        pyttsx3_voice_id=pt.get("voice_id"),
    )
    return TTSEngine(spec)
