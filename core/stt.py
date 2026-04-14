"""
音声入力エンジン（機能⑦）
faster-whisper を使ってマイク入力をテキストに変換します。
モデルは初回起動時に自動ダウンロード（~150MB, 以降オフライン）。

Phase C: 連続リスニングモード
  - start_continuous_listening(): VAD ベースの自動発話検出と送信
  - 振幅ベースの無音検出で発話終了を判定

インストール: pip install faster-whisper sounddevice soundfile
"""
from __future__ import annotations
import threading
import tempfile
import os
import platform
import time
from pathlib import Path
from typing import Callable, Optional

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

        # 連続リスニング状態（Phase C）
        self._continuous_active = False
        self._continuous_paused = False  # TTS 読み上げ中の一時停止
        self._continuous_thread: Optional[threading.Thread] = None

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

    # ─── 連続リスニング（Phase C） ─────────────────────────────────

    def start_continuous_listening(
        self,
        on_text: Callable[[str], None],
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
        min_speech_duration: float = 0.3,
    ) -> bool:
        """
        連続リスニングモードを開始する。
        音声を検出し、無音が silence_duration 秒続いたら自動的に変換して
        on_text コールバックを呼ぶ。その後、再びリスニングを再開する。

        Args:
            on_text: 認識テキストを受け取るコールバック
            silence_threshold: 無音判定の振幅閾値
            silence_duration: 発話終了と判定する無音の秒数
            min_speech_duration: 最小発話時間（秒、ノイズ除去用）

        Returns:
            開始成功なら True
        """
        if self._continuous_active:
            return False
        if not self.is_ready():
            print("[STT] モデル未ロード — 連続リスニング開始不可", flush=True)
            return False

        self._continuous_active = True
        self._continuous_paused = False
        self._continuous_thread = threading.Thread(
            target=self._continuous_loop,
            args=(on_text, silence_threshold, silence_duration, min_speech_duration),
            daemon=True,
        )
        self._continuous_thread.start()
        print("[STT] 連続リスニング開始", flush=True)
        return True

    def stop_continuous_listening(self):
        """連続リスニングモードを停止する"""
        self._continuous_active = False
        self._continuous_paused = False
        # 進行中の録音ストリームも停止
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        print("[STT] 連続リスニング停止", flush=True)

    def pause_continuous_listening(self):
        """連続リスニングを一時停止する（TTS 読み上げ中など）"""
        self._continuous_paused = True

    def resume_continuous_listening(self):
        """連続リスニングを再開する"""
        self._continuous_paused = False

    @property
    def is_continuous_active(self) -> bool:
        return self._continuous_active

    @property
    def is_continuous_paused(self) -> bool:
        return self._continuous_paused

    def _continuous_loop(
        self,
        on_text: Callable[[str], None],
        silence_threshold: float,
        silence_duration: float,
        min_speech_duration: float,
    ):
        """連続リスニングのメインループ"""
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            print("[STT] sounddevice/numpy が見つかりません", flush=True)
            self._continuous_active = False
            return

        chunk_duration = 0.1  # 100ms ごとにチェック
        chunk_samples = int(SAMPLE_RATE * chunk_duration)

        while self._continuous_active:
            # 一時停止中はスリープして待機
            if self._continuous_paused:
                time.sleep(0.2)
                continue

            speech_chunks: list = []
            silence_start: Optional[float] = None
            speech_detected = False
            speech_start_time: Optional[float] = None

            try:
                stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="float32",
                    blocksize=chunk_samples,
                )
                stream.start()
                self._stream = stream
            except Exception as e:
                print(f"[STT] ストリーム開始エラー: {e}", flush=True)
                time.sleep(1.0)
                continue

            try:
                while self._continuous_active and not self._continuous_paused:
                    data, overflowed = stream.read(chunk_samples)
                    amplitude = float(np.abs(data).mean())

                    if amplitude >= silence_threshold:
                        # 音声あり
                        speech_chunks.append(data.copy())
                        silence_start = None
                        if not speech_detected:
                            speech_detected = True
                            speech_start_time = time.monotonic()
                    else:
                        # 無音
                        if speech_detected:
                            # 発話後の無音 — バッファには追加（末尾の無音も含める）
                            speech_chunks.append(data.copy())
                            if silence_start is None:
                                silence_start = time.monotonic()
                            elif (time.monotonic() - silence_start) >= silence_duration:
                                # 無音が十分長い → 発話終了
                                speech_elapsed = (
                                    time.monotonic() - speech_start_time
                                    if speech_start_time
                                    else 0
                                )
                                if speech_elapsed >= min_speech_duration:
                                    break  # 変換へ進む
                                else:
                                    # 短すぎる — ノイズとみなしてリセット
                                    speech_chunks = []
                                    speech_detected = False
                                    speech_start_time = None
                                    silence_start = None
                        # 発話前の無音はスキップ
            except Exception as e:
                print(f"[STT] 連続リスニングエラー: {e}", flush=True)
            finally:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                self._stream = None

            # 変換（発話データがある場合のみ）
            if speech_chunks and self._continuous_active and not self._continuous_paused:
                text = self._transcribe_buffer(speech_chunks)
                if text and self._continuous_active:
                    on_text(text)

        self._continuous_active = False

    @staticmethod
    def _is_silence(audio_chunk, threshold: float = 0.01) -> bool:
        """音声チャンクが無音かどうか判定する"""
        import numpy as np
        return float(np.abs(audio_chunk).mean()) < threshold

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
