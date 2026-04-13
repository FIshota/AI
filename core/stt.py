"""
音声入力エンジン（機能⑦）
faster-whisper を使ってマイク入力をテキストに変換します。
モデルは初回起動時に自動ダウンロード（~150MB, 以降オフライン）。

インストール: pip install faster-whisper sounddevice soundfile
"""
from __future__ import annotations
import threading
import tempfile
import os
import platform
from pathlib import Path

IS_MAC = platform.system() == "Darwin"

# サンプリングレート（Whisper の推奨値）
SAMPLE_RATE = 16000
CHANNELS    = 1


class STTEngine:
    """
    音声認識エンジン。
    - faster-whisper が利用可能な場合は完全ローカル推論
    - 未インストールの場合はロード失敗メッセージのみ返す
    """

    def __init__(self, model_size: str = "small", language: str = "ja"):
        self.model_size = model_size
        self.language   = language
        self._model     = None
        self._loaded    = False
        self._loading   = False
        self._load_error: str | None = None

        # 録音状態
        self._recording  = False
        self._audio_data: list = []
        self._stream     = None
        self._audio_lock = threading.Lock()
        self._load_lock  = threading.Lock()

    # ─── モデル管理 ──────────────────────────────────────────────

    def load_model_async(self):
        """バックグラウンドでモデルを読み込む"""
        with self._load_lock:
            if self._loaded or self._loading:
                return
            self._loading = True
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel
            print(f"[STT] Whisper {self.model_size} を読み込み中...", flush=True)
            model = WhisperModel(
                self.model_size,
                device="cpu",           # MPS は未対応のため CPU
                compute_type="int8",    # arm64 macOS で安定動作
            )
            with self._load_lock:
                self._model   = model
                self._loaded  = True
                self._loading = False
            print(f"[STT] ✓ Whisper {self.model_size} 読み込み完了", flush=True)
        except ImportError:
            self._load_error = (
                "faster-whisper が見つかりません。\n"
                "pip install faster-whisper sounddevice soundfile でインストールしてね。"
            )
            with self._load_lock:
                self._loading = False
        except Exception as e:
            self._load_error = f"モデル読み込みエラー: {e}"
            with self._load_lock:
                self._loading = False

    def is_ready(self) -> bool:
        return self._loaded and self._model is not None

    def get_status(self) -> str:
        if self._loaded:
            return "ready"
        if self._loading:
            return "loading"
        if self._load_error:
            return f"error: {self._load_error}"
        return "not_started"

    # ─── 録音 ────────────────────────────────────────────────────

    def start_recording(self) -> bool:
        """マイク録音を開始する。sounddevice が必要。"""
        if self._recording:
            return False
        try:
            import sounddevice as sd
            with self._audio_lock:
                self._audio_data = []
                self._recording  = True

            def _callback(indata, frames, time_info, status):
                # オーディオスレッドから呼ばれるためロックで保護
                with self._audio_lock:
                    if self._recording:
                        self._audio_data.append(indata.copy())

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                callback=_callback,
            )
            self._stream.start()
            print("[STT] 録音開始", flush=True)
            return True
        except ImportError:
            print("[STT] sounddevice が見つかりません", flush=True)
            return False
        except Exception as e:
            print(f"[STT] 録音開始エラー: {e}", flush=True)
            self._recording = False
            return False

    def stop_recording_and_transcribe(self) -> str:
        """
        録音を停止してテキストに変換する。
        戻り値: 認識テキスト（失敗時は空文字列）
        """
        with self._audio_lock:
            if not self._recording:
                return ""
            self._recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # ロック内で audio_data のスナップショットを取得
        with self._audio_lock:
            if not self._audio_data:
                return ""
            buf = list(self._audio_data)
            self._audio_data = []

        return self._transcribe_buffer(buf)

    def _transcribe_buffer(self, buf: list | None = None) -> str:
        """録音バッファを Whisper でテキスト変換"""
        if not self.is_ready():
            return ""
        if buf is None:
            buf = self._audio_data
        if not buf:
            return ""
        tmp_path = None
        try:
            import numpy as np
            import soundfile as sf

            # バッファを結合して一時 WAV ファイルに保存
            audio = np.concatenate(buf, axis=0).flatten()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            sf.write(tmp_path, audio, SAMPLE_RATE)

            # Whisper で認識
            segments, _ = self._model.transcribe(
                tmp_path,
                language=self.language,
                beam_size=5,
                vad_filter=True,        # 無音区間をスキップ
            )
            text = " ".join(seg.text.strip() for seg in segments)

            print(f"[STT] 認識結果: {text[:80]}", flush=True)
            return text.strip()

        except Exception as e:
            print(f"[STT] 変換エラー: {e}", flush=True)
            return ""
        finally:
            # 例外が発生しても必ず一時ファイルを削除
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    # ─── ワンショット認識 ────────────────────────────────────────

    def transcribe_file(self, audio_path: str) -> str:
        """既存の音声ファイルをテキスト変換する"""
        if not self.is_ready():
            return ""
        try:
            segments, _ = self._model.transcribe(
                audio_path,
                language=self.language,
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segments)
        except Exception as e:
            print(f"[STT] ファイル認識エラー: {e}", flush=True)
            return ""
