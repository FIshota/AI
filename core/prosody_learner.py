"""
プロソディ学習エンジン

人間の音声を録音・解析し、ピッチ（声の高さ）、リズム（話速）、
ポーズ（間の取り方）のパターンを学習する。
学習結果は NeuralTTSEngine のプロソディパラメータに反映され、
より人間らしい自然な音声合成を実現する。

依存: numpy, scipy, sounddevice, soundfile（すべてインストール済み）
オプション: librosa（あればより高精度）
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.signal import correlate, medfilt

logger = logging.getLogger(__name__)

# ─── オプション依存 ──────────────────────────────────────────

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    sd = None  # type: ignore[assignment]
    SD_AVAILABLE = False

try:
    import soundfile as sf
    SF_AVAILABLE = True
except ImportError:
    sf = None  # type: ignore[assignment]
    SF_AVAILABLE = False

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    librosa = None  # type: ignore[assignment]
    LIBROSA_AVAILABLE = False


# ─── プロソディプロファイル ───────────────────────────────────

@dataclass
class ProsodyProfile:
    """学習済みプロソディパラメータ。

    人間の音声から抽出した特徴量を保持し、
    TTS のプロソディ設定に変換するためのデータ構造。
    """
    # 基本特徴量
    mean_pitch_hz: float = 0.0       # 平均ピッチ（Hz）
    pitch_range_hz: float = 0.0      # ピッチ変動幅（Hz）
    pitch_std_hz: float = 0.0        # ピッチ標準偏差（Hz）
    speech_rate_syl_sec: float = 0.0  # 発話速度（音節/秒 推定）
    mean_energy: float = 0.0          # 平均エネルギー
    energy_variation: float = 0.0     # エネルギー変動（std/mean）

    # ポーズパターン
    pause_short_ms: float = 200.0    # 短ポーズ（句読点レベル）
    pause_long_ms: float = 500.0     # 長ポーズ（文間レベル）
    pause_ratio: float = 0.15        # 全体に占めるポーズの割合

    # イントネーションパターン
    pitch_start_ratio: float = 1.0   # 文頭のピッチ比率（mean比）
    pitch_end_ratio: float = 1.0     # 文末のピッチ比率（mean比）
    pitch_contour_type: str = "falling"  # falling / rising / flat

    # 学習メタデータ
    sample_count: int = 0            # 学習サンプル数
    total_duration_sec: float = 0.0  # 累計録音時間
    last_updated: str = ""           # 最終更新日時

    # edge-tts 変換パラメータ（学習から自動計算）
    tts_rate_pct: float = 0.0        # edge-tts rate adjustment (%)
    tts_pitch_hz: float = 0.0        # edge-tts pitch adjustment (Hz)
    tts_volume_pct: float = 0.0      # edge-tts volume adjustment (%)
    tts_break_short_ms: int = 200    # 読点後の break (ms)
    tts_break_long_ms: int = 400     # 文間の break (ms)
    tts_break_thought_ms: int = 500  # 思考の break (ms)


# ─── ピッチ検出（scipy ベース）─────────────────────────────────

def _detect_pitch_autocorr(
    frame: np.ndarray, sr: int,
    fmin: float = 80.0, fmax: float = 500.0,
) -> float:
    """自己相関法によるピッチ検出。

    librosa.pyin よりシンプルだが、十分な精度で動作する。
    """
    if np.max(np.abs(frame)) < 0.01:
        return 0.0  # 無音フレーム

    corr = correlate(frame, frame, mode="full")
    corr = corr[len(corr) // 2:]  # 正のラグのみ

    min_lag = max(1, int(sr / fmax))
    max_lag = min(int(sr / fmin), len(corr) - 1)

    if min_lag >= max_lag:
        return 0.0

    search = corr[min_lag:max_lag + 1]
    if len(search) == 0 or np.max(search) <= 0:
        return 0.0

    # ピーク検出
    best_lag = min_lag + int(np.argmax(search))
    if best_lag <= 0:
        return 0.0

    # 信頼度チェック: 自己相関のピーク vs ゼロラグ
    confidence = corr[best_lag] / (corr[0] + 1e-10)
    if confidence < 0.3:
        return 0.0

    return sr / best_lag


def extract_pitch_contour(
    audio: np.ndarray, sr: int,
    frame_ms: float = 30.0, hop_ms: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    """音声からピッチ輪郭を抽出する。

    Returns:
        (pitches, times): ピッチ配列（Hz, 無声=0）と時刻配列
    """
    frame_len = int(frame_ms / 1000 * sr)
    hop_len = int(hop_ms / 1000 * sr)

    if LIBROSA_AVAILABLE:
        # librosa が使えるなら pyin（より高精度）
        f0, voiced, _ = librosa.pyin(
            audio, fmin=80, fmax=500, sr=sr,
            frame_length=frame_len, hop_length=hop_len,
        )
        f0 = np.nan_to_num(f0, nan=0.0)
        times = np.arange(len(f0)) * hop_ms / 1000
        return f0, times

    # scipy ベースのフォールバック
    pitches = []
    times = []
    for start in range(0, len(audio) - frame_len, hop_len):
        frame = audio[start : start + frame_len]
        p = _detect_pitch_autocorr(frame, sr)
        pitches.append(p)
        times.append(start / sr)

    pitches_arr = np.array(pitches)

    # メディアンフィルタでノイズ除去
    if len(pitches_arr) >= 5:
        voiced_mask = pitches_arr > 0
        if np.sum(voiced_mask) >= 5:
            smoothed = medfilt(pitches_arr, kernel_size=5)
            # 無声部分は 0 に戻す
            smoothed[~voiced_mask] = 0.0
            pitches_arr = smoothed

    return pitches_arr, np.array(times)


def extract_energy_contour(
    audio: np.ndarray, sr: int,
    frame_ms: float = 30.0, hop_ms: float = 10.0,
) -> np.ndarray:
    """フレームごとの RMS エネルギーを抽出する。"""
    frame_len = int(frame_ms / 1000 * sr)
    hop_len = int(hop_ms / 1000 * sr)

    energies = []
    for start in range(0, len(audio) - frame_len, hop_len):
        frame = audio[start : start + frame_len]
        rms = float(np.sqrt(np.mean(frame ** 2)))
        energies.append(rms)

    return np.array(energies)


def detect_pauses(
    energy: np.ndarray, times: np.ndarray,
    silence_threshold: float = 0.02, min_pause_ms: float = 100.0,
) -> list[float]:
    """エネルギー列からポーズ（無音区間）の長さリストを返す。"""
    if len(energy) == 0 or len(times) == 0:
        return []

    hop_sec = times[1] - times[0] if len(times) > 1 else 0.01
    is_silent = energy < silence_threshold
    pauses: list[float] = []
    pause_start: int | None = None

    for i, silent in enumerate(is_silent):
        if silent and pause_start is None:
            pause_start = i
        elif not silent and pause_start is not None:
            duration_ms = (i - pause_start) * hop_sec * 1000
            if duration_ms >= min_pause_ms:
                pauses.append(duration_ms)
            pause_start = None

    # 末尾が無音の場合
    if pause_start is not None:
        duration_ms = (len(is_silent) - pause_start) * hop_sec * 1000
        if duration_ms >= min_pause_ms:
            pauses.append(duration_ms)

    return pauses


def analyze_intonation_pattern(
    pitches: np.ndarray,
) -> tuple[float, float, str]:
    """ピッチ列からイントネーションパターンを分析する。

    Returns:
        (start_ratio, end_ratio, contour_type)
        start_ratio: 文頭のピッチ比率（全体平均比）
        end_ratio:   文末のピッチ比率（全体平均比）
        contour_type: "falling" / "rising" / "flat"
    """
    voiced = pitches[pitches > 0]
    if len(voiced) < 10:
        return 1.0, 1.0, "flat"

    mean_p = float(np.mean(voiced))
    if mean_p < 1.0:
        return 1.0, 1.0, "flat"

    # 先頭 20% と末尾 20% の平均ピッチ
    n = len(voiced)
    head_n = max(1, n // 5)
    tail_n = max(1, n // 5)

    head_mean = float(np.mean(voiced[:head_n]))
    tail_mean = float(np.mean(voiced[-tail_n:]))

    start_ratio = head_mean / mean_p
    end_ratio = tail_mean / mean_p

    # パターン判定
    diff_ratio = (tail_mean - head_mean) / mean_p
    if diff_ratio < -0.05:
        contour_type = "falling"
    elif diff_ratio > 0.05:
        contour_type = "rising"
    else:
        contour_type = "flat"

    return start_ratio, end_ratio, contour_type


# ─── プロソディ学習エンジン ───────────────────────────────────

class ProsodyLearner:
    """人間の音声からプロソディパターンを学習するエンジン。

    使い方:
    1. record_and_learn() で音声を録音・解析
    2. learn_from_file() でファイルから学習
    3. get_profile() で学習済みプロファイルを取得
    4. NeuralTTSEngine に適用

    学習は蓄積式: サンプルを追加するほどプロファイルが洗練される。
    """

    PROFILE_FILE = "prosody_profile.json"
    SAMPLES_DIR = "prosody_samples"

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self._profile_path = self.data_dir / self.PROFILE_FILE
        self._samples_dir = self.data_dir / self.SAMPLES_DIR
        self._profile: ProsodyProfile = ProsodyProfile()
        self._lock = threading.Lock()

        # 全サンプルの蓄積統計
        self._all_pitches: list[float] = []
        self._all_energies: list[float] = []
        self._all_pauses: list[float] = []
        self._all_rates: list[float] = []

        # ディレクトリ作成
        self._samples_dir.mkdir(parents=True, exist_ok=True)

        # 既存プロファイルの読み込み
        self._load_profile()

    # ─── 公開API ────────────────────────────────────────────

    def record_and_learn(
        self, duration_sec: float = 5.0, sr: int = 22050,
    ) -> dict:
        """マイクから録音してプロソディを学習する。

        Returns:
            {"success": bool, "message": str, "profile": dict}
        """
        if not SD_AVAILABLE:
            return {
                "success": False,
                "message": "sounddevice がインストールされていません",
            }

        try:
            print(f"🎙️ {duration_sec}秒間、自然に話してください...", flush=True)
            audio = sd.rec(
                int(duration_sec * sr), samplerate=sr,
                channels=1, dtype="float32",
            )
            sd.wait()
            audio = audio.flatten()
            print("🎙️ 録音完了！解析中...", flush=True)

            # 録音を保存
            sample_path = self._save_sample(audio, sr)

            # 解析・学習
            result = self._analyze_and_update(audio, sr)
            result["sample_path"] = str(sample_path)
            return result

        except Exception as exc:
            logger.warning("録音失敗: %s", exc)
            return {"success": False, "message": f"録音エラー: {exc}"}

    def learn_from_file(self, file_path: str | Path) -> dict:
        """音声ファイルからプロソディを学習する。

        WAV, FLAC, OGG 等の soundfile 対応形式。
        """
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "message": f"ファイルが見つかりません: {path}"}

        if not SF_AVAILABLE:
            return {"success": False, "message": "soundfile がインストールされていません"}

        try:
            audio, sr = sf.read(str(path), dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)  # ステレオ→モノラル
            return self._analyze_and_update(audio, sr)
        except Exception as exc:
            return {"success": False, "message": f"ファイル読み込みエラー: {exc}"}

    def get_profile(self) -> ProsodyProfile:
        """現在の学習済みプロファイルを返す。"""
        return self._profile

    def has_learned(self) -> bool:
        """学習データがあるかどうか。"""
        return self._profile.sample_count > 0

    def get_tts_overrides(self) -> dict:
        """NeuralTTSEngine に渡すプロソディオーバーライドを返す。

        Returns:
            {
                "rate_pct": float,     # edge-tts rate (%)
                "pitch_hz": float,     # edge-tts pitch offset (Hz)
                "volume_pct": float,   # edge-tts volume (%)
                "break_short_ms": int, # 読点後の break
                "break_long_ms": int,  # 文間の break
                "break_thought_ms": int, # 思考ポーズの break
                "pitch_start_offset": int,  # 文頭ピッチ補正 (Hz)
                "pitch_end_offset": int,    # 文末ピッチ補正 (Hz)
            }
        """
        p = self._profile
        if p.sample_count == 0:
            return {}

        return {
            "rate_pct": p.tts_rate_pct,
            "pitch_hz": p.tts_pitch_hz,
            "volume_pct": p.tts_volume_pct,
            "break_short_ms": p.tts_break_short_ms,
            "break_long_ms": p.tts_break_long_ms,
            "break_thought_ms": p.tts_break_thought_ms,
            "pitch_start_offset": self._ratio_to_hz(p.pitch_start_ratio),
            "pitch_end_offset": self._ratio_to_hz(p.pitch_end_ratio),
            "contour_type": p.pitch_contour_type,
        }

    def get_status_text(self) -> str:
        """学習状態のテキスト表示。"""
        p = self._profile
        lines = ["🎓 プロソディ学習ステータス\n"]

        if p.sample_count == 0:
            lines.append("  まだ学習データがありません。")
            lines.append("  「イントネーション学習」で声を聞かせてね！")
            return "\n".join(lines)

        lines.append(f"  学習サンプル数: {p.sample_count}")
        lines.append(f"  累計録音時間: {p.total_duration_sec:.1f}秒")
        lines.append(f"  最終更新: {p.last_updated}")
        lines.append("")
        lines.append("  【学習した特徴】")
        lines.append(f"  平均ピッチ: {p.mean_pitch_hz:.0f} Hz")
        lines.append(f"  ピッチ変動: ±{p.pitch_range_hz:.0f} Hz")
        lines.append(f"  話速: {p.speech_rate_syl_sec:.1f} 音節/秒")
        lines.append(f"  イントネーション: {self._contour_label(p.pitch_contour_type)}")
        lines.append(f"    文頭: {p.pitch_start_ratio:.2f}x  文末: {p.pitch_end_ratio:.2f}x")
        lines.append("")
        lines.append("  【TTS適用パラメータ】")
        lines.append(f"  速度: {p.tts_rate_pct:+.0f}%")
        lines.append(f"  ピッチ: {p.tts_pitch_hz:+.0f}Hz")
        lines.append(f"  ポーズ(短): {p.tts_break_short_ms}ms  (長): {p.tts_break_long_ms}ms")

        return "\n".join(lines)

    def reset(self) -> None:
        """学習データをリセットする。"""
        with self._lock:
            self._profile = ProsodyProfile()
            self._all_pitches.clear()
            self._all_energies.clear()
            self._all_pauses.clear()
            self._all_rates.clear()
            self._save_profile()

    # ─── 内部: 解析・更新 ──────────────────────────────────

    def _analyze_and_update(self, audio: np.ndarray, sr: int) -> dict:
        """音声を解析してプロファイルを更新する。"""
        duration = len(audio) / sr
        if duration < 1.0:
            return {"success": False, "message": "音声が短すぎます（1秒以上必要）"}

        # 正規化
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.9

        # ピッチ抽出
        pitches, times = extract_pitch_contour(audio, sr)
        voiced_pitches = pitches[pitches > 0]

        if len(voiced_pitches) < 10:
            return {"success": False, "message": "音声が検出できませんでした。もう少し大きな声で話してみてね"}

        # エネルギー抽出
        energy = extract_energy_contour(audio, sr)

        # ポーズ検出
        pause_times = times if len(times) == len(energy) else np.linspace(0, duration, len(energy))
        pauses = detect_pauses(energy, pause_times)

        # イントネーションパターン
        start_r, end_r, contour = analyze_intonation_pattern(pitches)

        # 発話速度推定（有声フレーム数から概算）
        voiced_frames = np.sum(pitches > 0)
        voiced_duration = voiced_frames * 0.01  # 10ms hop
        # 日本語: 平均約 6-8 モーラ/秒
        estimated_rate = max(3.0, min(12.0, voiced_duration * 7.0 / duration))

        # 蓄積
        with self._lock:
            self._all_pitches.extend(voiced_pitches.tolist())
            self._all_energies.extend(energy[energy > 0.01].tolist())
            self._all_pauses.extend(pauses)
            self._all_rates.append(estimated_rate)

            # プロファイル更新
            self._update_profile(
                duration, start_r, end_r, contour,
            )
            self._save_profile()

        p = self._profile
        return {
            "success": True,
            "message": (
                f"学習完了！（サンプル #{p.sample_count}）\n"
                f"  ピッチ: {p.mean_pitch_hz:.0f}Hz (±{p.pitch_range_hz:.0f}Hz)\n"
                f"  イントネーション: {self._contour_label(contour)}\n"
                f"  ポーズ: 短={p.tts_break_short_ms}ms 長={p.tts_break_long_ms}ms"
            ),
            "profile": asdict(p),
        }

    def _update_profile(
        self,
        duration: float,
        start_ratio: float,
        end_ratio: float,
        contour: str,
    ) -> None:
        """蓄積統計からプロファイルを再計算する。"""
        p = self._profile
        pitches = np.array(self._all_pitches)
        energies = np.array(self._all_energies) if self._all_energies else np.array([0.0])
        pauses = self._all_pauses
        rates = self._all_rates

        p.sample_count += 1
        p.total_duration_sec += duration
        p.last_updated = time.strftime("%Y-%m-%d %H:%M")

        # ピッチ統計
        p.mean_pitch_hz = float(np.mean(pitches))
        p.pitch_std_hz = float(np.std(pitches))
        p.pitch_range_hz = float(np.percentile(pitches, 90) - np.percentile(pitches, 10))

        # エネルギー統計
        p.mean_energy = float(np.mean(energies))
        p.energy_variation = float(np.std(energies) / (np.mean(energies) + 1e-10))

        # ポーズ統計
        if pauses:
            sorted_pauses = sorted(pauses)
            short_pauses = [x for x in sorted_pauses if x < 400]
            long_pauses = [x for x in sorted_pauses if x >= 400]
            p.pause_short_ms = float(np.mean(short_pauses)) if short_pauses else 200.0
            p.pause_long_ms = float(np.mean(long_pauses)) if long_pauses else 500.0
            p.pause_ratio = sum(pauses) / (p.total_duration_sec * 1000 + 1e-10)

        # 発話速度
        p.speech_rate_syl_sec = float(np.mean(rates))

        # イントネーション（指数移動平均で蓄積）
        alpha = 1.0 / p.sample_count  # 新しいサンプルほど重みが小さい（平均に収束）
        p.pitch_start_ratio = (1 - alpha) * p.pitch_start_ratio + alpha * start_ratio
        p.pitch_end_ratio = (1 - alpha) * p.pitch_end_ratio + alpha * end_ratio
        p.pitch_contour_type = contour  # 最新のパターンを使用

        # ─── TTS パラメータへの変換 ───────────────────────
        self._compute_tts_params(p)

    def _compute_tts_params(self, p: ProsodyProfile) -> None:
        """プロソディ特徴量 → edge-tts パラメータに変換する。"""

        # 速度: 日本語の平均（約7音節/秒）との差分をパーセンテージに
        # 6 syl/sec = ゆっくり (-10%), 7 = 標準 (0%), 9 = 速い (+15%)
        rate_diff = (p.speech_rate_syl_sec - 7.0) / 7.0 * 100
        p.tts_rate_pct = max(-20.0, min(20.0, rate_diff))

        # ピッチ: NanamiNeural の基準ピッチ（約250Hz）との差分
        # 実際のユーザーのピッチを直接反映するのではなく、
        # ピッチの「変動の大きさ」を反映する
        pitch_variability = p.pitch_std_hz / (p.mean_pitch_hz + 1e-10)
        # 変動が大きい人 = 抑揚がある → ピッチレンジを広げる
        if pitch_variability > 0.15:
            p.tts_pitch_hz = 3.0  # 少し抑揚を付ける
        elif pitch_variability < 0.08:
            p.tts_pitch_hz = -2.0  # 落ち着いた感じ
        else:
            p.tts_pitch_hz = 0.0

        # ボリューム: エネルギー変動を反映
        if p.energy_variation > 0.5:
            p.tts_volume_pct = 5.0  # ダイナミックな人
        else:
            p.tts_volume_pct = 0.0

        # ブレイクタイミング: 学習したポーズを反映
        p.tts_break_short_ms = max(100, min(400, int(p.pause_short_ms)))
        p.tts_break_long_ms = max(250, min(800, int(p.pause_long_ms)))
        p.tts_break_thought_ms = max(300, min(1000, int(p.pause_long_ms * 1.2)))

    # ─── ユーティリティ ─────────────────────────────────────

    @staticmethod
    def _ratio_to_hz(ratio: float) -> int:
        """ピッチ比率（mean比）をHz オフセットに変換。"""
        # 1.05x → +3Hz, 0.95x → -3Hz
        return int((ratio - 1.0) * 60)

    @staticmethod
    def _contour_label(contour: str) -> str:
        labels = {
            "falling": "⬇ 下降型（自然な日本語）",
            "rising": "⬆ 上昇型（疑問・興奮）",
            "flat": "➡ 平坦型",
        }
        return labels.get(contour, contour)

    def _save_sample(self, audio: np.ndarray, sr: int) -> Path:
        """録音サンプルをファイルに保存する。"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = self._samples_dir / f"sample_{timestamp}.wav"
        if SF_AVAILABLE:
            sf.write(str(path), audio, sr)
        return path

    def _save_profile(self) -> None:
        """プロファイルをJSONに保存する。"""
        try:
            data = asdict(self._profile)
            self._profile_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception as exc:
            logger.warning("プロファイル保存失敗: %s", exc)

    def _load_profile(self) -> None:
        """保存済みプロファイルを読み込む。"""
        if not self._profile_path.exists():
            return
        try:
            data = json.loads(self._profile_path.read_text("utf-8"))
            # dataclass フィールドのみ取り出す
            valid_fields = {f.name for f in self._profile.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in valid_fields}
            self._profile = ProsodyProfile(**filtered)
            logger.info(
                "プロソディプロファイル読み込み: %d サンプル",
                self._profile.sample_count,
            )
        except Exception as exc:
            logger.warning("プロファイル読み込み失敗: %s", exc)
