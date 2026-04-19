"""core/tts/engine.py のユニットテスト (Phase 0.75)."""
from __future__ import annotations

import pytest

from core.tts import create_tts_engine, EngineSpec, SpeakResult
from core.tts.engine import (
    Pyttsx3Backend, VoiceVoxBackend, SystemBackend, TTSEngine, _NoopBackend,
)


class TestEngineSpec:
    def test_default_spec(self):
        spec = EngineSpec(name="auto")
        assert spec.voicevox_host == "127.0.0.1"
        assert spec.voicevox_port == 50021
        assert spec.pyttsx3_rate == 180

    def test_frozen(self):
        spec = EngineSpec(name="pyttsx3")
        with pytest.raises(Exception):
            spec.name = "voicevox"  # type: ignore


class TestFactoryFromSettings:
    def test_empty_settings_defaults_to_auto(self):
        eng = create_tts_engine({})
        assert isinstance(eng, TTSEngine)
        assert eng.spec.name == "auto"

    def test_pyttsx3_explicit(self):
        eng = create_tts_engine({"voice": {"engine": "pyttsx3"}})
        assert eng.spec.name == "pyttsx3"

    def test_voicevox_overrides(self):
        eng = create_tts_engine({
            "voice": {
                "engine": "voicevox",
                "voicevox": {"host": "10.0.0.5", "port": 6000, "speaker_id": 3},
            }
        })
        assert eng.spec.voicevox_host == "10.0.0.5"
        assert eng.spec.voicevox_port == 6000
        assert eng.spec.voicevox_speaker_id == 3

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("AICHAN_TTS_ENGINE", "system")
        eng = create_tts_engine({"voice": {"engine": "pyttsx3"}})
        assert eng.spec.name == "system"


class TestBackendAvailability:
    def test_voicevox_unreachable_returns_false(self):
        be = VoiceVoxBackend(EngineSpec(name="voicevox",
                                        voicevox_host="127.0.0.1",
                                        voicevox_port=1))  # 確実に無効な port
        assert be.available() is False

    def test_system_depends_on_os(self):
        be = SystemBackend()
        # macOS なら True、Linux なら espeak 有無で変わる、CI でも少なくとも例外は出ない
        assert isinstance(be.available(), bool)

    def test_pyttsx3_availability_boolean(self):
        be = Pyttsx3Backend(EngineSpec(name="pyttsx3"))
        assert isinstance(be.available(), bool)


class TestResolution:
    def test_auto_falls_back_gracefully(self, monkeypatch):
        # 全バックエンドを unavailable にして noop に落ちることを検証
        def false_avail(self):
            return False
        monkeypatch.setattr(VoiceVoxBackend, "available", false_avail)
        monkeypatch.setattr(Pyttsx3Backend, "available", false_avail)
        monkeypatch.setattr(SystemBackend, "available", false_avail)
        eng = create_tts_engine({"voice": {"engine": "auto"}})
        assert eng.resolved_name == "noop"

    def test_noop_speak_returns_failure(self):
        r = _NoopBackend().speak("test")
        assert isinstance(r, SpeakResult)
        assert r.success is False
        assert r.engine == "noop"


class TestSpeakResult:
    def test_speak_result_immutable(self):
        r = SpeakResult(success=True, engine="pyttsx3", duration_sec=0.5)
        with pytest.raises(Exception):
            r.success = False  # type: ignore
        assert r.engine == "pyttsx3"
