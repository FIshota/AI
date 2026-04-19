"""
音声入力エンジン（機能⑦）
faster-whisper を使ってマイク入力をテキストに変換します。
モデルは初回起動時に自動ダウンロード（~150MB, 以降オフライン）。

Phase C: 連続リスニングモード
  - start_continuous_listening(): VAD ベースの自動発話検出と送信
  - 振幅ベースの無音検出で発話終了を判定

Phase D: 複数話者対応
  - 録音音声を無音区間で分割し、セグメントごとに話者識別 + 変換
  - voice_id (MFCC) を使った軽量な話者識別
  - セグメント単位の逐次処理で体感速度を改善

インストール: pip install faster-whisper sounddevice soundfile
"""
from __future__ import annotations
import threading
import tempfile
import os
import platform
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.voice_id import VoiceIDManager

logger = logging.getLogger(__name__)

IS_MAC = platform.system() == "Darwin"

# サンプリングレート（Whisper の推奨値）
SAMPLE_RATE = 16000
CHANNELS    = 1

# Phase D: セグメント分割パラメータ
_WINDOW_MS       = 20      # 振幅判定の窓サイズ (ms)
_MIN_SILENCE_MS  = 400     # 話者交代とみなす無音長 (ms)
_MIN_SEGMENT_MS  = 800     # 有効セグメントの最短長 (ms)


@dataclass
class SpeakerUtterance:
    """話者ごとの発話結果"""
    speaker: str        # 話者名（識別できなければ空文字列）
    text: str           # 認識テキスト
    confidence: float   # 話者識別の信頼度 (0.0–1.0)


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

        # Phase D: 話者識別連携
        self._voice_id: Optional[VoiceIDManager] = None

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

    # ─── Phase D: 話者識別連携 ─────────────────────────────────────

    def set_voice_id(self, voice_id: VoiceIDManager) -> None:
        """話者識別マネージャを設定して複数話者モードを有効にする"""
        self._voice_id = voice_id
        logger.info("[STT] 話者識別を有効化 (プロファイル数=%d)",
                     len(voice_id.profiles))

    @property
    def multi_speaker_enabled(self) -> bool:
        """複数話者モードが利用可能かどうか"""
        return self._voice_id is not None and len(self._voice_id.profiles) > 0

    # ─── Phase D: 音声セグメント分割 ────────────────────────────────

    @staticmethod
    def segment_audio_by_silence(
        audio: "np.ndarray",
        sr: int = SAMPLE_RATE,
        silence_threshold: float = 0.008,
        min_silence_ms: int = _MIN_SILENCE_MS,
        min_segment_ms: int = _MIN_SEGMENT_MS,
    ) -> "list[np.ndarray]":
        """音声を無音区間で分割して話者ターンごとのセグメントにする。

        Args:
            audio: 1次元 float32 波形
            sr: サンプリングレート
            silence_threshold: 無音判定の振幅閾値
            min_silence_ms: 話者交代とみなす最小無音長 (ms)
            min_segment_ms: 有効セグメントの最短長 (ms)

        Returns:
            分割された音声セグメントのリスト
        """
        import numpy as np

        window_samples = int(sr * _WINDOW_MS / 1000)
        min_silence_windows = max(1, min_silence_ms // _WINDOW_MS)
        min_segment_samples = int(sr * min_segment_ms / 1000)

        # 各窓の振幅を計算
        n_windows = len(audio) // window_samples
        if n_windows == 0:
            return [audio] if len(audio) >= min_segment_samples else []

        amplitudes = []
        for i in range(n_windows):
            start = i * window_samples
            end = start + window_samples
            amplitudes.append(float(np.abs(audio[start:end]).mean()))

        # 無音区間でセグメント境界を検出
        segments: list[np.ndarray] = []
        seg_start_window = 0
        silence_count = 0
        in_speech = False

        for i, amp in enumerate(amplitudes):
            if amp >= silence_threshold:
                if not in_speech:
                    in_speech = True
                silence_count = 0
            else:
                silence_count += 1
                if in_speech and silence_count >= min_silence_windows:
                    # 無音が十分長い → セグメント境界
                    seg_end = (i - silence_count + 1) * window_samples
                    seg_start = seg_start_window * window_samples
                    segment = audio[seg_start:seg_end]
                    if len(segment) >= min_segment_samples:
                        segments.append(segment)
                    seg_start_window = i + 1
                    in_speech = False
                    silence_count = 0

        # 残りの音声をセグメントとして追加
        remaining_start = seg_start_window * window_samples
        if remaining_start < len(audio):
            remaining = audio[remaining_start:]
            if len(remaining) >= min_segment_samples:
                segments.append(remaining)

        # セグメントが一つも取れなかった場合は全体を返す
        if not segments:
            return [audio] if len(audio) >= min_segment_samples else []

        logger.info("[STT] 音声を %d セグメントに分割", len(segments))
        return segments

    def _identify_speaker(self, audio_segment: "np.ndarray") -> tuple[str, float]:
        """音声セグメントから話者を識別する。

        Returns:
            (話者名, 信頼度) — 識別できなければ ("", 0.0)
        """
        if self._voice_id is None:
            return ("", 0.0)
        try:
            from core.voice_id import extract_voice_features, cosine_similarity
            import numpy as np

            query = extract_voice_features(audio_segment, sr=SAMPLE_RATE)

            best_name = ""
            best_score = 0.0
            for profile in self._voice_id.profiles.values():
                if not profile.has_voice_print:
                    continue
                stored = np.array(profile.voice_features, dtype=np.float32)
                score = cosine_similarity(query, stored)
                if score > best_score:
                    best_score = score
                    best_name = profile.name

            threshold = self._voice_id.match_threshold
            if best_score >= threshold:
                return (best_name, best_score)
            return ("", best_score)

        except (ImportError, ValueError) as exc:
            logger.debug("[STT] 話者識別スキップ: %s", exc)
            return ("", 0.0)

    def _transcribe_segment(self, audio: "np.ndarray") -> str:
        """単一セグメントをテキスト変換する（軽量版）"""
        if not self.is_ready():
            return ""
        tmp_path = None
        try:
            import soundfile as sf

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            sf.write(tmp_path, audio, SAMPLE_RATE)

            segments, _ = self._model.transcribe(
                tmp_path,
                language=self.language,
                beam_size=3,        # セグメント単位なので beam を小さくして高速化
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:
            logger.warning("[STT] セグメント変換エラー: %s", e)
            return ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def transcribe_multi_speaker(
        self, buf: list
    ) -> list[SpeakerUtterance]:
        """録音バッファを話者ごとに分割して変換する。

        ① 音声を無音区間でセグメント分割
        ② 各セグメントで話者識別 (MFCC)
        ③ 各セグメントを Whisper で変換
        ④ 話者付きの結果リストを返す

        Returns:
            SpeakerUtterance のリスト
        """
        import numpy as np

        if not self.is_ready() or not buf:
            return []

        audio = np.concatenate(buf, axis=0).flatten()
        segments = self.segment_audio_by_silence(audio)

        results: list[SpeakerUtterance] = []
        for seg in segments:
            text = self._transcribe_segment(seg)
            if not text:
                continue
            speaker, conf = self._identify_speaker(seg)
            results.append(SpeakerUtterance(
                speaker=speaker,
                text=text,
                confidence=conf,
            ))

        logger.info(
            "[STT] 複数話者変換完了: %d 発話 (話者: %s)",
            len(results),
            ", ".join(r.speaker or "不明" for r in results),
        )
        return results

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

    def stop_recording_and_transcribe_multi(self) -> list[SpeakerUtterance]:
        """録音を停止して複数話者対応でテキスト変換する。

        Returns:
            SpeakerUtterance のリスト（話者識別無効時は単一要素）
        """
        with self._audio_lock:
            if not self._recording:
                return []
            self._recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._audio_lock:
            if not self._audio_data:
                return []
            buf = list(self._audio_data)
            self._audio_data = []

        if self.multi_speaker_enabled:
            return self.transcribe_multi_speaker(buf)
        else:
            text = self._transcribe_buffer(buf)
            if text:
                return [SpeakerUtterance(speaker="", text=text, confidence=0.0)]
            return []

    def _transcribe_buffer(self, buf: list | None = None) -> str:
        """録音バッファを Whisper でテキスト変換。

        音声が長い場合は自動的にセグメント分割して高速化する。
        """
        if not self.is_ready():
            return ""
        if buf is None:
            buf = self._audio_data
        if not buf:
            return ""
        try:
            import numpy as np

            audio = np.concatenate(buf, axis=0).flatten()
            duration_sec = len(audio) / SAMPLE_RATE

            # 2秒超の音声はセグメント分割して高速化
            if duration_sec > 2.0:
                segments = self.segment_audio_by_silence(audio)
                if len(segments) > 1:
                    logger.info(
                        "[STT] %.1f秒の音声を %d セグメントに分割して変換",
                        duration_sec, len(segments),
                    )
                    texts = []
                    for seg in segments:
                        t = self._transcribe_segment(seg)
                        if t:
                            texts.append(t)
                    result = " ".join(texts).strip()
                    print(f"[STT] 認識結果(分割): {result[:80]}", flush=True)
                    return result

            # 短い音声 or 分割不要な場合は一括変換
            return self._transcribe_single(audio)

        except Exception as e:
            print(f"[STT] 変換エラー: {e}", flush=True)
            return ""

    def _transcribe_single(self, audio: "np.ndarray") -> str:
        """単一の音声配列を一括でWhisper変換する"""
        if not self.is_ready():
            return ""
        tmp_path = None
        try:
            import soundfile as sf

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            sf.write(tmp_path, audio, SAMPLE_RATE)

            segments, _ = self._model.transcribe(
                tmp_path,
                language=self.language,
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            print(f"[STT] 認識結果: {text[:80]}", flush=True)
            return text.strip()

        except Exception as e:
            print(f"[STT] 変換エラー: {e}", flush=True)
            return ""
        finally:
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
                if self.multi_speaker_enabled:
                    # Phase D: 複数話者モード — セグメント分割+話者識別
                    utterances = self.transcribe_multi_speaker(speech_chunks)
                    for utt in utterances:
                        if not self._continuous_active:
                            break
                        # 話者名付きのテキストをコールバックに渡す
                        labeled = (
                            f"[{utt.speaker}] {utt.text}"
                            if utt.speaker
                            else utt.text
                        )
                        on_text(labeled)
                else:
                    # 従来の単一話者モード
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
        """既存の音声ファイルをテキスト変換する。

        Item #P7: word-level confidence フィルタと重複フレーム除去を適用。
        - avg_logprob が極端に低い segment を棄却
        - no_speech_prob が高い segment を棄却
        - 同一テキストの連続重複を除去
        """
        if not self.is_ready():
            return ""
        try:
            segments, _ = self._model.transcribe(
                audio_path,
                language=self.language,
                vad_filter=True,
                # Item #P7: 無音検出強化 + より厳しい閾値
                vad_parameters={"min_silence_duration_ms": 500},
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
            )
            parts: list[str] = []
            last_text = ""
            for seg in segments:
                text = (getattr(seg, "text", "") or "").strip()
                if not text:
                    continue
                # 信頼度フィルタ
                avg_lp = getattr(seg, "avg_logprob", 0.0)
                no_speech = getattr(seg, "no_speech_prob", 0.0)
                if avg_lp < -1.0 or no_speech > 0.6:
                    continue
                # 直前と重複するテキストをスキップ
                if text == last_text:
                    continue
                last_text = text
                parts.append(text)
            return " ".join(parts)
        except Exception as e:
            print(f"[STT] ファイル認識エラー: {e}", flush=True)
            return ""
