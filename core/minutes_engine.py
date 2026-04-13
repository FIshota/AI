"""
議事録エンジン
音声録音 → 文字起こし → 議事録整形 → PDF出力 → 履歴管理
オフラインファースト: 全処理ローカル実行
"""
from __future__ import annotations
import json
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

# ─── 音声関連 ────────────────────────────────────────────────────
try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    AUDIO_OK = True
except ImportError:
    AUDIO_OK = False

# ─── 文字起こし (mlx-whisper優先 → faster-whisper フォールバック) ──
import os as _os
_os.environ.setdefault("PATH", _os.environ.get("PATH", "") +
                       ":/usr/local/bin:" + str(Path.home() / "bin"))

try:
    import mlx_whisper as _mlx_whisper
    import soundfile as _sf_mlx
    MLX_OK = True
except ImportError:
    MLX_OK = False

try:
    from faster_whisper import WhisperModel
    WHISPER_OK = True
except ImportError:
    WHISPER_OK = False

# mlx-whisperモデルID (Apple Silicon Metal)
_MLX_MODELS = {
    "tiny":   "mlx-community/whisper-tiny-mlx",
    "small":  "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large":  "mlx-community/whisper-large-v3-mlx",
}

# ─── PDF ────────────────────────────────────────────────────────
try:
    from fpdf import FPDF
    FPDF_OK = True
except ImportError:
    FPDF_OK = False

# 日本語フォント候補（優先順 — 壊れたフォントは除外済み）
_FONT_CANDIDATES = [
    Path.home() / "Library/Fonts/LINESeedJP_TTF_Th.ttf",
    Path.home() / "Library/Fonts/irohamaru-mikami-Regular.ttf",
    Path.home() / "Library/Fonts/irohamaru-mikami-Medium.ttf",
    Path.home() / "Library/Fonts/LINESeedJP_TTF_Bd.ttf",
    Path("/Library/Fonts/Arial Unicode.ttf"),
]


def _find_japanese_font() -> Path | None:
    for p in _FONT_CANDIDATES:
        if p.exists():
            return p
    return None


# ─── 議事録テンプレート ──────────────────────────────────────────
# Map段階: 各チャンクから構造化情報を抽出（箇条書きのみ、最終整形はしない）
MINUTES_EXTRACT_PROMPT = """以下は長い会議の文字起こしの一部です。この**部分だけ**を対象に、
情報を構造化して箇条書きで抽出してください。整形や要約は最小限で、情報の取りこぼしを防ぐことを最優先にしてください。

【抽出ルール】
- 発言者が特定できる場合は「〔名前〕発言内容」の形式で記録
- 事実と意見を区別し、対立意見があれば両方記録
- 数値・期日・固有名詞は必ず保持
- 「えー」「あの」「そうですね」等のフィラーは無視
- 同じ話が繰り返された場合は1回にまとめる
- この部分に該当する項目が無ければそのセクションは空欄（「なし」と記入）
- 推測で情報を追加しない。文字起こしに無い内容を書かない

【出力フォーマット】
### 論点・議論
・（この部分で議論されたトピックと主な発言を列挙）

### 決定事項（確定したもののみ）
・（「〜に決めた」「〜とする」「〜で合意」等が明確なものだけ）

### アクションアイテム（担当/内容/期限）
・〔担当者〕内容（期限: YYYY-MM-DD または 要確認）

### 重要な数値・固有名詞
・（金額、日付、製品名、組織名等）

### キー引用（そのまま残すべき発言）
・「原文どおりの発言」

【文字起こし（部分 {chunk_no}/{chunk_total}）】
{transcript}"""


# Reduce段階: 複数チャンクの抽出結果を統合して最終議事録を生成
MINUTES_REDUCE_PROMPT = """以下は、長い会議の文字起こしをチャンクごとに抽出した結果です。
これらを統合して、**重複を排除した最終議事録**を作成してください。

【統合ルール】
- 同じ論点が複数チャンクに出てきたら1つにまとめる
- アクションアイテムは「担当者/内容/期限」で重複排除
- 時系列ではなく**トピック別**に整理する
- 決定事項と論点（未決）は厳密に分離する
- 文字起こしに無い内容は絶対に加えない
- 「（推測）」「（憶測）」「（不明）」は使わず、不明な場合は「要確認」と記す

【チャンク別抽出結果】
{chunks_combined}

【最終出力フォーマット】（必ず以下の見出しで出力）
## 議題・目的
（1〜2文で会議の目的）

## 参加者・背景
（分かる範囲で）

## 論点ごとの議論
### 論点1: （トピック名）
・論点の背景と主な発言
・賛成意見 / 反対意見があればそれぞれ明記

### 論点2: …
（同じ構造で）

## 決定事項
・決まったことを箇条書き（曖昧なものは入れない）

## アクションアイテム
| 担当 | 内容 | 期限 |
|------|------|------|
| 〔名前〕 | 〜 | YYYY-MM-DD または 要確認 |

## 未決事項・持ち越し
・次回までに決める必要がある項目

## 重要な数値・キー引用
・数値や原文引用を保持

## 次回に向けて
・申し送り事項

日本語のみで、簡潔かつ情報密度高く出力してください。"""


# 後方互換: 短い会議向けのシングルショットプロンプト
MINUTES_FORMAT_PROMPT = """以下の文字起こしを議事録として整形してください。

【厳守ルール】
- 文字起こしに無い情報は絶対に追加しない
- 「えー」「あの」等のフィラーは無視
- 決定事項と議論（未決）を厳密に分離
- 数値・期日・固有名詞は必ず保持
- 時系列ではなくトピック別に整理
- 日本語のみで出力

【文字起こし】
{transcript}

【出力フォーマット】
## 議題・目的
（1〜2文）

## 論点ごとの議論
### 論点1: （トピック）
・主な発言・賛否両論

## 決定事項
・明確に決まったもののみ

## アクションアイテム
| 担当 | 内容 | 期限 |
|------|------|------|
| 〔名前〕 | 〜 | 要確認 |

## 未決事項
・持ち越し項目

## 次回に向けて
・申し送り"""


class MinutesEngine:
    """議事録エンジン: 録音・文字起こし・整形・保存・PDF出力を担当"""

    def __init__(self, data_dir: Path):
        self.data_dir  = Path(data_dir)
        self.audio_dir = self.data_dir / "minutes" / "audio"
        self.pdf_dir   = self.data_dir / "minutes" / "pdf"
        self.db_path   = self.data_dir / "minutes" / "minutes.jsonl"
        for d in [self.audio_dir, self.pdf_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Whisper (faster-whisper fallback)
        self._whisper: "WhisperModel | None" = None
        self._whisper_lock     = threading.Lock()
        self._whisper_loading  = False
        self._whisper_ready_ev = threading.Event()  # ロード完了通知
        # mlx-whisper モデル名キャッシュ
        self._mlx_model_id: str | None = None
        # 録音
        self._recording          = False
        self._audio_frames: list = []
        self._audio_lock         = threading.Lock()  # オーディオスレッド競合対策
        self._stream             = None  # sd.InputStream | None
        self._sample_rate        = 16000   # Whisper用(リサンプル後)
        self._record_rate        = 0       # デバイスのネイティブsr(起動時に検出)
        self._on_status: Callable[[str], None] | None = None

    # ─── ステータスコールバック ──────────────────────────────────

    def set_status_callback(self, cb: Callable[[str], None]):
        self._on_status = cb

    def _status(self, msg: str):
        print(f"[Minutes] {msg}", flush=True)
        if self._on_status:
            self._on_status(msg)

    # ─── Whisper 初期化 ─────────────────────────────────────────

    def load_whisper_async(self, model_size: str = "small"):
        """バックグラウンドでWhisperをウォームアップ（初回呼び出しコストをゼロに）"""
        with self._whisper_lock:
            if self._whisper_loading or self._whisper_ready_ev.is_set():
                return
            self._whisper_loading = True
        model_id = _MLX_MODELS.get(model_size, _MLX_MODELS["small"])
        self._mlx_model_id = model_id

        if MLX_OK:
            def _warmup():
                try:
                    self._status(f"🔥 Whisper ウォームアップ中 ({model_size})…")
                    import numpy as _np
                    _dummy = _np.zeros(16000, dtype="float32")  # 1秒の無音
                    _mlx_whisper.transcribe(
                        _dummy, path_or_hf_repo=model_id,
                        language="ja", fp16=True,
                        no_speech_threshold=0.6,
                    )
                    self._status("✅ Whisper 準備完了 (Apple Silicon 高速モード)")
                except Exception as e:
                    self._status(f"Whisperウォームアップ失敗: {e}")
                finally:
                    self._whisper_loading = False
                    self._whisper_ready_ev.set()
            try:
                threading.Thread(target=_warmup, daemon=True).start()
            except Exception as e:
                self._whisper_loading = False
                self._status(f"スレッド起動失敗: {e}")
            return

        # ── faster-whisper (CPU) fallback ──
        if self._whisper:
            self._whisper_loading = False
            self._whisper_ready_ev.set()
            return

        def _load():
            try:
                self._status(f"Whisper ({model_size}) を読み込み中…")
                with self._whisper_lock:
                    if not self._whisper:
                        self._whisper = WhisperModel(
                            model_size, device="cpu", compute_type="int8"
                        )
                self._status("✅ Whisper 準備完了")
            except Exception as e:
                self._status(f"Whisper 読み込み失敗: {e}")
            finally:
                self._whisper_loading = False
                self._whisper_ready_ev.set()

        threading.Thread(target=_load, daemon=True).start()

    @property
    def whisper_ready(self) -> bool:
        return self._whisper_ready_ev.is_set()

    # ─── 録音 ───────────────────────────────────────────────────

    def _detect_device_samplerate(self) -> int:
        """デフォルト入力デバイスのネイティブサンプルレートを取得"""
        try:
            default = sd.default.device
            if default is None:
                return 48000
            dev_idx = default[0] if isinstance(default, (tuple, list)) else default
            if dev_idx is None or (isinstance(dev_idx, int) and dev_idx < 0):
                self._status("入力デバイス未設定 — 48000Hz で続行")
                return 48000
            dev = sd.query_devices(dev_idx, 'input')
            sr  = int(dev.get('default_samplerate', 48000))
            self._status(f"入力デバイス: {dev['name']} ({sr}Hz)")
            return sr
        except Exception as e:
            self._status(f"デバイス検出失敗 — 48000Hz で続行: {e}")
            return 48000

    def start_recording(self) -> bool:
        if not AUDIO_OK:
            self._status("sounddevice が未インストールです")
            return False
        if self._recording:
            return False

        # デバイスのネイティブレートを使用（権限なしで0が返る問題を回避）
        if self._record_rate == 0:
            self._record_rate = self._detect_device_samplerate()

        with self._audio_lock:
            self._audio_frames = []
            self._recording    = True

        def _callback(indata, frames, time_info, status):
            if status:
                print(f"[録音] 警告: {status}", flush=True)
            # オーディオスレッドから呼ばれるためロックで保護
            with self._audio_lock:
                if self._recording:
                    self._audio_frames.append(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self._record_rate,
                channels=1,
                dtype="float32",
                callback=_callback,
                blocksize=4096,        # バッファサイズを大きめに
            )
            self._stream.start()
            self._status(f"⏺ 録音開始 ({self._record_rate}Hz)")
            return True
        except Exception as e:
            self._recording = False
            self._status(f"録音開始失敗: {e}\n→ システム設定→プライバシー→マイクで権限を確認してください")
            return False

    def stop_recording(self) -> Path | None:
        """録音を停止してwavファイルを保存（16kHzにリサンプリング）"""
        with self._audio_lock:
            if not self._recording:
                return None
            self._recording = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        finally:
            self._stream = None

        # ロック内でフレームのスナップショットを取得
        with self._audio_lock:
            if not self._audio_frames:
                self._status("録音データがありません")
                return None
            frames = list(self._audio_frames)
            self._audio_frames = []

        audio = np.concatenate(frames, axis=0)

        # 無音チェック（権限なしの場合は全サンプルが0）
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 1e-9:
            self._status(
                "⚠️ 録音音量がゼロです。\n"
                "システム設定 → プライバシーとセキュリティ → マイク\n"
                "→ 「ターミナル」をオンにしてからアプリを再起動してください"
            )

        # デバイスレートがWhisper用16kHzと異なる場合はリサンプリング
        record_rate = self._record_rate or 48000
        if record_rate != self._sample_rate:
            ratio   = self._sample_rate / record_rate
            new_len = int(len(audio) * ratio)
            audio   = np.interp(
                np.linspace(0, len(audio), new_len),
                np.arange(len(audio)),
                audio.flatten()
            ).astype("float32")

        filename = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        wav_path = self.audio_dir / filename
        sf.write(str(wav_path), audio, self._sample_rate)
        duration = len(audio) / self._sample_rate
        self._status(f"録音完了: {duration:.1f}秒 / RMS={rms:.5f}")
        return wav_path

    # ─── 文字起こし ──────────────────────────────────────────────

    def transcribe(self, wav_path: Path,
                   progress_cb: Callable[[str], None] | None = None) -> str:
        """音声ファイルを文字起こし (mlx-whisper優先・faster-whisper fallback)"""
        if not (MLX_OK or WHISPER_OK):
            return "(whisper 未インストール: pip install mlx-whisper)"

        # ── mlx-whisper (Apple Silicon Metal) ──────────────────
        if MLX_OK:
            return self._transcribe_mlx(wav_path, progress_cb)

        # ── faster-whisper fallback (CPU) ──────────────────────
        return self._transcribe_faster(wav_path, progress_cb)

    def _transcribe_mlx(self, wav_path: Path,
                        progress_cb: Callable[[str], None] | None = None) -> str:
        """mlx-whisperで文字起こし"""
        import soundfile as sf_
        # ウォームアップ完了を最大15秒待機（初回起動時のみ）
        if not self._whisper_ready_ev.is_set():
            if progress_cb:
                progress_cb("⏳ Whisper ウォームアップ完了待機中…")
            self._whisper_ready_ev.wait(timeout=15)
        if progress_cb:
            progress_cb("🚀 高速文字起こし中 (Apple Silicon)…")
        try:
            t0 = time.perf_counter()
            # soundfileでnumpy配列として読み込み（ffmpeg不要）
            audio_np, sr = sf_.read(str(wav_path), dtype="float32")
            if audio_np.ndim > 1:
                audio_np = audio_np[:, 0]   # モノラル化
            # リサンプリング(必要な場合)
            if sr != 16000:
                import numpy as np_
                ratio   = 16000 / sr
                new_len = int(len(audio_np) * ratio)
                audio_np = np_.interp(
                    np_.linspace(0, len(audio_np), new_len),
                    np_.arange(len(audio_np)),
                    audio_np
                ).astype("float32")

            model_id = self._mlx_model_id or _MLX_MODELS["small"]
            result   = _mlx_whisper.transcribe(
                audio_np,
                path_or_hf_repo=model_id,
                language="ja",
                fp16=True,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
            )
            text    = (result.get("text") or "").strip()
            elapsed = time.perf_counter() - t0
            if not text:
                text = "(音声が検出されませんでした。マイク入力や録音時間を確認してください)"
            if progress_cb:
                progress_cb(f"✅ 文字起こし完了: {len(text)}文字 ({elapsed:.1f}秒)")
            return text
        except Exception as e:
            self._status(f"mlx文字起こし失敗 → fallback: {e}")
            import traceback; traceback.print_exc()
            return self._transcribe_faster(wav_path, progress_cb)

    def _transcribe_faster(self, wav_path: Path,
                           progress_cb: Callable[[str], None] | None = None) -> str:
        """faster-whisperで文字起こし (CPUフォールバック)"""
        if not WHISPER_OK:
            return "(faster-whisper 未インストール)"

        # Whisperロード待機（競合防止）
        if self._whisper_loading:
            if progress_cb:
                progress_cb("Whisperモデル読み込み待機中…")
            self._whisper_ready_ev.wait(timeout=60)

        with self._whisper_lock:
            if not self._whisper:
                if progress_cb:
                    progress_cb("Whisperモデルをロード中… (初回のみ30秒ほどかかります)")
                try:
                    self._whisper = WhisperModel(
                        "small", device="cpu", compute_type="int8"
                    )
                except Exception as e:
                    return f"(Whisperロード失敗: {e})"

        if progress_cb:
            progress_cb("文字起こし中… (CPU処理・しばらくお待ちください)")
        try:
            t0 = time.perf_counter()
            segments, _ = self._whisper.transcribe(
                str(wav_path),
                language="ja",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
                beam_size=1,
                condition_on_previous_text=False,
            )
            parts: list[str] = []
            seg_count = 0
            for seg in segments:
                seg_text = seg.text.strip()
                if seg_text:
                    parts.append(seg_text)
                seg_count += 1
                if progress_cb and seg_count % 3 == 0:
                    elapsed = time.perf_counter() - t0
                    progress_cb(f"文字起こし中… {seg_count}セグメント ({elapsed:.0f}秒)")
            text = " ".join(parts)
            elapsed = time.perf_counter() - t0
            if not text.strip():
                text = "(音声が検出されませんでした)"
            if progress_cb:
                progress_cb(f"✅ 文字起こし完了: {len(text)}文字 ({elapsed:.1f}秒)")
            return text
        except Exception as e:
            self._status(f"文字起こし失敗: {e}")
            import traceback; traceback.print_exc()
            return f"(文字起こし失敗: {e})"

    # ─── 議事録整形 ──────────────────────────────────────────────

    def format_minutes(
        self,
        transcript: str,
        llm_engine=None,
        title: str = "",
        attendees: str = "",
        progress_cb: Callable[[str], None] | None = None,
        stream_cb: Callable[[str], None] | None = None,
    ) -> str:
        """文字起こしテキストを議事録形式に整形。llm_engineがNoneなら簡易整形。"""
        if not transcript or not transcript.strip():
            return _fallback_format("（テキストなし）", title, attendees)

        if progress_cb:
            progress_cb("文字起こしを前処理中…")

        # 1) 前処理: フィラー除去・重複排除・文境界整備（LLM有無に関わらず実施）
        cleaned_transcript = _preprocess_transcript(transcript)

        # LLMがない場合はフォールバック（前処理済みを渡す）
        if llm_engine is None or not getattr(llm_engine, "_loaded", False):
            if progress_cb:
                progress_cb("LLMなしで簡易整形します")
            return _fallback_format(cleaned_transcript, title, attendees)

        system_msg = {
            "role": "system",
            "content": (
                "あなたは議事録作成の専門家です。必ず日本語のみで出力します。"
                "文字起こしに無い情報は絶対に追加せず、推測や創作をしません。"
                "情報の取りこぼしを防ぐことを最優先にし、決定事項と議論（未決）を厳密に区別します。"
            ),
        }

        try:
            # 2) 短い会議はシングルショット、長い会議はMap-Reduce
            CHUNK_THRESHOLD = 2200  # この文字数以下ならシングルショット
            if len(cleaned_transcript) <= CHUNK_THRESHOLD:
                if progress_cb:
                    progress_cb("LLMで議事録を生成中…")
                prompt = MINUTES_FORMAT_PROMPT.format(transcript=cleaned_transcript)
                result = llm_engine.generate_chat(
                    [system_msg, {"role": "user", "content": prompt}],
                    max_tokens=1600,
                    stream_cb=stream_cb,
                )
            else:
                # Map-Reduce: 長い会議を分割して精度を保つ
                chunks = _chunk_transcript(cleaned_transcript, size=1800, overlap=200)
                total = len(chunks)
                if progress_cb:
                    progress_cb(f"長い会議を{total}チャンクに分割して抽出します…")

                extracted_parts: list[str] = []
                for idx, chunk in enumerate(chunks, start=1):
                    if progress_cb:
                        progress_cb(f"チャンク {idx}/{total} を抽出中…")
                    ext_prompt = MINUTES_EXTRACT_PROMPT.format(
                        transcript=chunk, chunk_no=idx, chunk_total=total
                    )
                    part = llm_engine.generate_chat(
                        [system_msg, {"role": "user", "content": ext_prompt}],
                        max_tokens=1200,
                        stream_cb=None,  # Map段階はUIに流さない
                    )
                    if part and part.strip():
                        extracted_parts.append(f"【チャンク {idx}/{total}】\n{part.strip()}")

                if not extracted_parts:
                    raise ValueError("Map段階で抽出結果が得られませんでした")

                # Reduce: 抽出結果を統合
                if progress_cb:
                    progress_cb("抽出結果を統合して最終議事録を生成中…")
                chunks_combined = "\n\n".join(extracted_parts)
                # Reduceプロンプトが長すぎるとコンテキスト超過するのでガード
                if len(chunks_combined) > 8000:
                    chunks_combined = chunks_combined[:8000] + "\n…(以下省略)"
                reduce_prompt = MINUTES_REDUCE_PROMPT.format(
                    chunks_combined=chunks_combined
                )
                result = llm_engine.generate_chat(
                    [system_msg, {"role": "user", "content": reduce_prompt}],
                    max_tokens=2400,
                    stream_cb=stream_cb,
                )

            if not result or len(result.strip()) < 30:
                raise ValueError(f"生成結果が短すぎます ({len(result) if result else 0} 文字)")

            # 英語混入や空セクションを除去
            result = _clean_minutes_text(result)
        except Exception as e:
            self._status(f"LLM整形失敗: {e} → 原文を整形して返します")
            import traceback; traceback.print_exc()
            # フォールバック: 文字起こし原文をセクション付きで整形
            result = _fallback_format(cleaned_transcript, title, attendees)

        if progress_cb:
            progress_cb("整形完了")
        return result

    # ─── 保存 ────────────────────────────────────────────────────

    def save_minutes(
        self,
        transcript: str,
        formatted: str,
        title: str = "",
        attendees: str = "",
        wav_path: Path | None = None,
    ) -> dict:
        """議事録をJSONLに保存して辞書を返す"""
        mid = str(uuid.uuid4())[:8]
        now = datetime.now()
        entry = {
            "id":          mid,
            "title":       title or f"会議 {now.strftime('%Y-%m-%d %H:%M')}",
            "date":        now.strftime("%Y-%m-%d"),
            "time":        now.strftime("%H:%M"),
            "attendees":   attendees,
            "transcript":  transcript,
            "formatted":   formatted,
            "wav_path":    str(wav_path) if wav_path else "",
            "pdf_path":    "",
            "created_at":  now.isoformat()[:16],
        }
        with open(self.db_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._status(f"議事録保存完了: {entry['title']}")
        return entry

    # ─── 履歴取得 ────────────────────────────────────────────────

    def list_minutes(self) -> list[dict]:
        """保存済み議事録を新しい順に返す"""
        if not self.db_path.exists():
            return []
        entries = {}
        for line in self.db_path.read_text("utf-8").splitlines():
            if line.strip():
                try:
                    e = json.loads(line)
                    entries[e["id"]] = e   # 上書きで最新状態を使う
                except Exception:
                    pass
        return list(reversed(list(entries.values())))

    def get_minutes(self, mid: str) -> dict | None:
        for m in self.list_minutes():
            if m["id"] == mid:
                return m
        return None

    def update_minutes(self, mid: str, **kwargs):
        """既存議事録の特定フィールドを更新（pdf_pathなど、アトミック書き込み）"""
        entries = self.list_minutes()
        lines   = []
        for e in reversed(entries):
            if e["id"] == mid:
                e.update(kwargs)
            lines.append(json.dumps(e, ensure_ascii=False))
        # アトミック書き込み: 一時ファイルに書いて os.replace で差し替え
        import os as _os
        tmp = self.db_path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(lines) + "\n", "utf-8")
        _os.replace(str(tmp), str(self.db_path))

    # ─── PDF 出力 ────────────────────────────────────────────────

    def export_pdf(self, mid: str) -> Path | None:
        """指定IDの議事録をPDFに書き出してPathを返す"""
        entry = self.get_minutes(mid)
        if not entry:
            self._status(f"議事録が見つかりません: {mid}")
            return None
        if not FPDF_OK:
            self._status("fpdf2 が未インストールです")
            return None

        font_path = _find_japanese_font()
        if not font_path:
            self._status("日本語フォントが見つかりません")
            return None

        filename  = f"minutes_{entry['date'].replace('-','')}"
        safe_title = re.sub(r'[^\w\s]', '', entry['title'])[:20]
        pdf_path  = self.pdf_dir / f"{filename}_{safe_title}.pdf"

        try:
            pdf = FPDF(orientation="P", unit="mm", format="A4")
            pdf.set_margins(20, 20, 20)
            pdf.set_auto_page_break(auto=True, margin=20)
            pdf.add_page()
            pdf.add_font("JP", fname=str(font_path))

            # ─ タイトルブロック ─
            pdf.set_font("JP", size=18)
            pdf.set_text_color(50, 20, 80)
            pdf.cell(0, 12, "議  事  録", ln=True, align="C")
            pdf.ln(2)

            # 水平線
            pdf.set_draw_color(180, 130, 200)
            pdf.set_line_width(0.6)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(4)

            # メタ情報
            pdf.set_font("JP", size=10)
            pdf.set_text_color(80, 80, 100)
            pdf.cell(0, 6, f"タイトル: {entry['title']}", ln=True)
            pdf.cell(0, 6, f"日　　時: {entry['date']} {entry['time']}", ln=True)
            if entry.get("attendees"):
                pdf.cell(0, 6, f"参 加 者: {entry['attendees']}", ln=True)
            pdf.ln(4)

            pdf.set_draw_color(200, 170, 220)
            pdf.set_line_width(0.3)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(5)

            # 本文
            pdf.set_text_color(30, 20, 45)
            formatted = entry.get("formatted", "")
            for line in formatted.splitlines():
                line = line.rstrip()
                if line.startswith("## "):
                    # セクションヘッダー
                    pdf.ln(3)
                    pdf.set_font("JP", size=12)
                    pdf.set_text_color(100, 50, 150)
                    heading = line.lstrip("# ").strip()
                    pdf.cell(0, 8, f"▍ {heading}", ln=True)
                    pdf.set_text_color(30, 20, 45)
                    pdf.set_font("JP", size=10)
                elif line.startswith(("・", "•", "-", "＊", "*")) or re.match(r'^[\d１-９][\.\．]', line):
                    pdf.set_font("JP", size=10)
                    _pdf_multiline(pdf, "    " + line.lstrip("-・•＊* "), 170)
                elif line == "":
                    pdf.ln(2)
                else:
                    pdf.set_font("JP", size=10)
                    _pdf_multiline(pdf, line, 170)

            # フッター（ページ番号）
            pdf.set_font("JP", size=8)
            pdf.set_text_color(160, 140, 180)
            pdf.set_y(-15)
            pdf.cell(0, 5, f"議事録 ID: {mid}  /  作成: {entry['created_at']}",
                     ln=True, align="C")

            pdf.output(str(pdf_path))
            self._status(f"PDF出力完了: {pdf_path.name}")

            # DB にパスを保存
            self.update_minutes(mid, pdf_path=str(pdf_path))
            return pdf_path

        except Exception as e:
            self._status(f"PDF出力失敗: {e}")
            import traceback; traceback.print_exc()
            return None

    # ─── ai-chan 学習連携 ────────────────────────────────────────

    def build_learning_text(self, entry: dict) -> str:
        """議事録を ai-chan の学習テキストに変換"""
        lines = [
            f"会議「{entry['title']}」（{entry['date']}）の議事録",
            entry.get("formatted", entry.get("transcript", ""))[:800],
        ]
        return "\n".join(lines)


# ─── ヘルパー ────────────────────────────────────────────────────

def _fallback_format(transcript: str, title: str = "", attendees: str = "") -> str:
    """LLMが使えない場合やタイムアウト時の簡易フォールバック整形"""
    lines = [
        "## 議題・目的",
        f"（{title or '会議'}の議事録）",
        "",
        "## 主な議論内容",
    ]
    for line in transcript.splitlines():
        line = line.strip()
        if line:
            lines.append(f"・{line[:100]}")
    lines += [
        "",
        "## 決定事項",
        "・（LLMが利用できないため自動抽出できませんでした）",
        "",
        "## アクションアイテム",
        "・（LLMが利用できないため自動抽出できませんでした）",
        "",
        "## 次回に向けて",
        "・（LLMが利用できないため自動抽出できませんでした）",
    ]
    return "\n".join(lines)


def _pdf_multiline(pdf: "FPDF", text: str, max_width: float):
    """長いテキストを折り返して出力"""
    if not text:
        return
    # fpdf2 の multi_cell を使う
    pdf.multi_cell(max_width, 6, text, ln=True)


# ─── トランスクリプト前処理 ─────────────────────────────────────

# Whisperがよく残す日本語フィラー（単独で出現した場合のみ除去）
_FILLERS = (
    "えー", "えーと", "えっと", "あの", "あのー", "そのー", "まあ", "うーん",
    "なんか", "ま、", "えっとですね", "そうですね", "はい、はい", "うん",
)

# 長いフィラーから先にマッチさせるため降順ソート
_FILLERS_SORTED = tuple(sorted(_FILLERS, key=len, reverse=True))

# 同じ文が連続する場合、最大1回だけ残す（2回目以降はWhisperのループ出力として削除）
_MAX_REPEAT = 1


def _preprocess_transcript(text: str) -> str:
    """文字起こしの前処理: フィラー除去・重複排除・文境界整備。

    - 行頭/行末の空白を削除
    - 単独で出現するフィラーを除去
    - 同一文が連続する場合は最大_MAX_REPEAT回まで
    - 句点「。」のない長い行に句点を補完（簡易）
    """
    if not text:
        return ""

    # まず全角空白/改行を正規化
    text = text.replace("\u3000", " ")

    # 文単位に分割（「。」「?」「？」「!」「！」を境界として扱い、改行も境界）
    sentences: list[str] = []
    buffer = []
    for ch in text:
        buffer.append(ch)
        if ch in "。．.?？!！\n":
            s = "".join(buffer).strip()
            if s:
                sentences.append(s)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)

    # フィラー除去＆重複排除
    cleaned: list[str] = []
    prev_sentence = ""
    repeat_count = 0
    for sent in sentences:
        # フィラーのみの行はスキップ
        stripped = sent.strip("。．.?？!！ 　")
        if not stripped:
            continue
        if stripped in _FILLERS_SORTED:
            continue
        # 先頭フィラーを落とす（長いものから試す。反復的に剥がす）
        changed = True
        while changed:
            changed = False
            for f in _FILLERS_SORTED:
                if stripped.startswith(f):
                    stripped = stripped[len(f):].lstrip("、，,. ")
                    changed = True
                    break
        if not stripped:
            continue

        # 連続重複チェック
        if stripped == prev_sentence:
            repeat_count += 1
            if repeat_count >= _MAX_REPEAT:
                continue
        else:
            repeat_count = 0
        prev_sentence = stripped

        # 末尾が句読点で終わっていなければ句点を付与
        if stripped[-1] not in "。．.?？!！":
            stripped += "。"
        cleaned.append(stripped)

    return "\n".join(cleaned)


def _chunk_transcript(text: str, size: int = 1800, overlap: int = 200) -> list[str]:
    """長いトランスクリプトをオーバーラップ付きでチャンク分割。

    できるだけ文境界（改行または句点）で切る。overlapで前チャンクの末尾を
    次チャンクの先頭に含めることで、境界での情報ロスを防ぐ。
    """
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        # 文境界で切る: endから遡って近い「。」「\n」を探す
        if end < n:
            cut = -1
            for sep in ("\n", "。", "．", "！", "？", "!", "?"):
                idx = text.rfind(sep, start + size // 2, end)
                if idx > cut:
                    cut = idx
            if cut > start:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def _clean_minutes_text(text: str) -> str:
    """LLM出力から英語メタ注釈などを除去"""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        # 英語注釈行を除去
        if re.match(r'^\((?:Note|Translation|Instruction)[:\s]', stripped, re.I):
            continue
        has_jp = bool(re.search(r'[\u3040-\u9FFF]', stripped))
        only_en_words = bool(re.search(r'[a-zA-Z]{4,}', stripped))
        if only_en_words and not has_jp and not stripped.startswith("##"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()
