"""
声紋認証システム

MFCC特徴量を用いた声紋登録・照合を提供する。
名前ベース識別もフォールバックとして維持。

機能:
- MFCC + デルタ特徴量抽出 (39次元ベクトル)
- 声紋登録 (3サンプル平均)
- コサイン類似度による話者識別
- 信頼レベル管理
- JSON永続化 (後方互換)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Trust levels
TRUST_OWNER = 100
TRUST_FAMILY = 85
TRUST_FRIEND = 70
TRUST_COLLEAGUE = 60
TRUST_GUEST = 40

# 声紋照合のデフォルト閾値
DEFAULT_MATCH_THRESHOLD = 0.85

# 録音パラメータ
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_RECORD_DURATION = 3.0
REGISTRATION_SAMPLES = 3


def extract_voice_features(
    audio_data: "np.ndarray",
    sr: int = DEFAULT_SAMPLE_RATE,
) -> "np.ndarray":
    """音声データからMFCC + デルタ特徴量を抽出する。

    13次元MFCC、1次デルタ、2次デルタを結合し、
    時間軸方向の平均を取って固定長39次元ベクトルを返す。

    Args:
        audio_data: 音声波形 (1次元 float32 配列)
        sr: サンプリングレート

    Returns:
        特徴量ベクトル (shape: (39,))

    Raises:
        ImportError: librosa が未インストールの場合
        ValueError: 音声データが短すぎる場合
    """
    import numpy as np

    try:
        import librosa
    except ImportError as exc:
        raise ImportError(
            "声紋特徴量抽出には librosa が必要です: pip install librosa"
        ) from exc

    if audio_data.size == 0:
        raise ValueError("音声データが空です")

    # 無音・極短音声のガード
    if len(audio_data) < sr * 0.5:
        raise ValueError(
            f"音声データが短すぎます ({len(audio_data)} サンプル, "
            f"最低 {int(sr * 0.5)} サンプル必要)"
        )

    audio_float = audio_data.astype(np.float32)

    mfcc = librosa.feature.mfcc(y=audio_float, sr=sr, n_mfcc=13)
    delta = librosa.feature.delta(mfcc)
    delta2 = librosa.feature.delta(mfcc, order=2)

    features = np.concatenate([
        np.mean(mfcc, axis=1),
        np.mean(delta, axis=1),
        np.mean(delta2, axis=1),
    ])
    return features  # shape: (39,)


def cosine_similarity(a: "np.ndarray", b: "np.ndarray") -> float:
    """2つのベクトル間のコサイン類似度を計算する。

    Args:
        a: ベクトルA
        b: ベクトルB

    Returns:
        コサイン類似度 (-1.0 ~ 1.0)
    """
    import numpy as np

    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / max(norm, 1e-8))


def record_voice(
    duration: float = DEFAULT_RECORD_DURATION,
    sr: int = DEFAULT_SAMPLE_RATE,
) -> "np.ndarray":
    """マイクから音声を録音する。

    Args:
        duration: 録音時間 (秒)
        sr: サンプリングレート

    Returns:
        録音された音声波形 (1次元 float32 配列)

    Raises:
        ImportError: sounddevice が未インストールの場合
        RuntimeError: マイクアクセスに失敗した場合
    """
    import numpy as np

    try:
        import sounddevice as sd
    except ImportError as exc:
        raise ImportError(
            "音声録音には sounddevice が必要です: pip install sounddevice"
        ) from exc

    try:
        audio = sd.rec(
            int(duration * sr),
            samplerate=sr,
            channels=1,
            dtype="float32",
        )
        sd.wait()
    except sd.PortAudioError as exc:
        raise RuntimeError(
            "マイクへのアクセスに失敗しました。"
            "システム環境設定でマイクの使用を許可してください。"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"録音中にエラーが発生しました: {exc}") from exc

    return audio.flatten()


@dataclass(frozen=True)
class VoiceProfile:
    """声紋プロファイル

    Attributes:
        user_id: ユーザー識別子
        name: 表示名
        trust_level: 信頼レベル (0-100)
        registered_at: 登録日時 ISO 文字列
        voice_features: MFCC特徴量ベクトル (39次元, JSON用にリスト化)
    """

    user_id: str
    name: str
    trust_level: int = TRUST_GUEST
    registered_at: str = ""
    voice_features: Optional[List[float]] = None

    @property
    def has_voice_print(self) -> bool:
        """声紋データが登録済みかどうかを返す。"""
        return self.voice_features is not None and len(self.voice_features) > 0


class VoiceIDManager:
    """声紋認証マネージャ

    MFCC特徴量によるフル声紋認証と、名前ベースの
    フォールバック識別の両方を提供する。
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    ) -> None:
        """初期化。

        Args:
            data_dir: プロファイル保存ディレクトリ (デフォルト: data/)
            match_threshold: 声紋照合の類似度閾値 (デフォルト: 0.85)
        """
        self._profiles: Dict[str, VoiceProfile] = {}
        self._current_user: Optional[str] = None
        self._match_threshold = match_threshold
        self._data_path = (data_dir or Path("data")) / "voice_profiles.json"
        self._load_profiles()

    # ------------------------------------------------------------------ #
    #  永続化
    # ------------------------------------------------------------------ #

    def _load_profiles(self) -> None:
        """保存済みプロファイルを読み込む。

        voice_features フィールドが存在しない旧フォーマットにも対応する。
        """
        if not self._data_path.exists():
            return
        try:
            raw = self._data_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            for uid, info in data.items():
                raw_features = info.get("voice_features")
                features: Optional[List[float]] = None
                if raw_features is not None and isinstance(raw_features, list):
                    features = [float(v) for v in raw_features]

                self._profiles[uid] = VoiceProfile(
                    user_id=uid,
                    name=info.get("name", ""),
                    trust_level=info.get("trust_level", TRUST_GUEST),
                    registered_at=info.get("registered_at", ""),
                    voice_features=features,
                )
            logger.info("声紋プロファイル読込: %d 件", len(self._profiles))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("声紋プロファイル読込失敗: %s", exc)

    def _save_profiles(self) -> None:
        """プロファイルをファイルに保存する。"""
        try:
            self._data_path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, dict] = {}
            for uid, profile in self._profiles.items():
                entry = asdict(profile)
                # None の voice_features はキーごと省略して後方互換を維持
                if entry.get("voice_features") is None:
                    del entry["voice_features"]
                data[uid] = entry
            self._data_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("声紋プロファイル保存失敗: %s", exc)

    # ------------------------------------------------------------------ #
    #  名前ベース識別 (既存 API — 後方互換)
    # ------------------------------------------------------------------ #

    def register_user(
        self, name: str, trust_level: int = TRUST_GUEST
    ) -> VoiceProfile:
        """テキストベースのユーザー登録（声紋なし）。

        Args:
            name: ユーザー名
            trust_level: 信頼レベル

        Returns:
            作成された VoiceProfile
        """
        from datetime import datetime

        uid = name.lower().replace(" ", "_")
        existing = self._profiles.get(uid)
        # 既存プロファイルの声紋データを保持する
        existing_features = (
            existing.voice_features if existing is not None else None
        )

        profile = VoiceProfile(
            user_id=uid,
            name=name,
            trust_level=trust_level,
            registered_at=datetime.now().isoformat(),
            voice_features=existing_features,
        )
        self._profiles[uid] = profile
        self._current_user = uid
        self._save_profiles()
        logger.info("ユーザー登録: %s (trust=%d)", name, trust_level)
        return profile

    def identify_by_name(self, name: str) -> Optional[VoiceProfile]:
        """名前ベースの識別（声紋認証の代替）。

        Args:
            name: 検索するユーザー名

        Returns:
            一致する VoiceProfile。見つからなければ None
        """
        uid = name.lower().replace(" ", "_")
        profile = self._profiles.get(uid)
        if profile:
            self._current_user = uid
        return profile

    # ------------------------------------------------------------------ #
    #  声紋認証 (新規 API)
    # ------------------------------------------------------------------ #

    def record_sample(
        self,
        duration: float = DEFAULT_RECORD_DURATION,
        sr: int = DEFAULT_SAMPLE_RATE,
    ) -> "np.ndarray":
        """マイクから音声サンプルを録音する。

        Args:
            duration: 録音時間 (秒)
            sr: サンプリングレート

        Returns:
            録音された音声波形

        Raises:
            RuntimeError: 録音に失敗した場合
        """
        return record_voice(duration=duration, sr=sr)

    def register_voice(
        self,
        name: str,
        trust_level: int = TRUST_GUEST,
        samples: Optional[List["np.ndarray"]] = None,
        duration: float = DEFAULT_RECORD_DURATION,
        sr: int = DEFAULT_SAMPLE_RATE,
    ) -> VoiceProfile:
        """声紋付きでユーザーを登録する。

        samples が渡されなければマイクから REGISTRATION_SAMPLES 回
        録音して特徴量を取得する。

        Args:
            name: ユーザー名
            trust_level: 信頼レベル
            samples: 事前録音済み音声配列のリスト (省略時はマイク録音)
            duration: 録音時間 (秒, samples 省略時のみ使用)
            sr: サンプリングレート

        Returns:
            声紋登録済みの VoiceProfile

        Raises:
            ImportError: 必要なライブラリが未インストールの場合
            RuntimeError: 録音に失敗した場合
            ValueError: 特徴量抽出に失敗した場合
        """
        import numpy as np
        from datetime import datetime

        if samples is None:
            samples = []
            for i in range(REGISTRATION_SAMPLES):
                logger.info(
                    "声紋サンプル録音 %d/%d — 話してください...",
                    i + 1,
                    REGISTRATION_SAMPLES,
                )
                audio = record_voice(duration=duration, sr=sr)
                samples.append(audio)
                logger.info("サンプル %d 録音完了", i + 1)

        # 各サンプルから特徴量を抽出し平均化
        feature_list: List["np.ndarray"] = []
        for idx, sample in enumerate(samples):
            try:
                feat = extract_voice_features(sample, sr=sr)
                feature_list.append(feat)
            except ValueError as exc:
                logger.warning("サンプル %d の特徴量抽出失敗: %s", idx + 1, exc)

        if not feature_list:
            raise ValueError(
                "有効な音声サンプルがありません。"
                "静かな環境で再度お試しください。"
            )

        avg_features = np.mean(feature_list, axis=0)

        uid = name.lower().replace(" ", "_")
        profile = VoiceProfile(
            user_id=uid,
            name=name,
            trust_level=trust_level,
            registered_at=datetime.now().isoformat(),
            voice_features=avg_features.tolist(),
        )
        self._profiles[uid] = profile
        self._current_user = uid
        self._save_profiles()

        logger.info(
            "声紋登録完了: %s (trust=%d, サンプル数=%d)",
            name,
            trust_level,
            len(feature_list),
        )
        return profile

    def identify_by_voice(
        self,
        audio: Optional["np.ndarray"] = None,
        duration: float = DEFAULT_RECORD_DURATION,
        sr: int = DEFAULT_SAMPLE_RATE,
    ) -> Tuple[Optional[VoiceProfile], float]:
        """声紋で話者を識別する。

        audio が渡されなければマイクから録音する。
        登録済みプロファイルとコサイン類似度で照合し、
        閾値を超える最も類似度の高いプロファイルを返す。

        Args:
            audio: 識別対象の音声 (省略時はマイク録音)
            duration: 録音時間 (秒, audio 省略時のみ使用)
            sr: サンプリングレート

        Returns:
            (一致したプロファイル or None, 最大類似度)
            一致がなければ (None, 最大類似度) を返す

        Raises:
            ImportError: 必要なライブラリが未インストールの場合
            RuntimeError: 録音に失敗した場合
        """
        import numpy as np

        if audio is None:
            logger.info("声紋識別のため録音を開始します...")
            audio = record_voice(duration=duration, sr=sr)

        try:
            query_features = extract_voice_features(audio, sr=sr)
        except ValueError as exc:
            logger.warning("声紋特徴量抽出失敗: %s", exc)
            return None, 0.0

        best_profile: Optional[VoiceProfile] = None
        best_score = -1.0

        for profile in self._profiles.values():
            if not profile.has_voice_print:
                continue
            stored = np.array(profile.voice_features, dtype=np.float32)
            score = cosine_similarity(query_features, stored)
            logger.debug(
                "声紋照合: %s — 類似度 %.4f", profile.name, score
            )
            if score > best_score:
                best_score = score
                best_profile = profile

        if best_profile is not None and best_score >= self._match_threshold:
            self._current_user = best_profile.user_id
            logger.info(
                "声紋識別成功: %s (類似度=%.4f)",
                best_profile.name,
                best_score,
            )
            return best_profile, best_score

        logger.info(
            "声紋識別失敗: 閾値 %.2f を超える一致なし (最大=%.4f)",
            self._match_threshold,
            best_score,
        )
        return None, best_score

    # ------------------------------------------------------------------ #
    #  共通ユーティリティ (既存 API — 後方互換)
    # ------------------------------------------------------------------ #

    def get_current_user(self) -> Optional[VoiceProfile]:
        """現在のユーザーを返す。"""
        if self._current_user:
            return self._profiles.get(self._current_user)
        return None

    def get_trust_level(self) -> int:
        """現在のユーザーの信頼レベルを返す。"""
        user = self.get_current_user()
        return user.trust_level if user else TRUST_GUEST

    def can_access_agent_mode(self) -> bool:
        """エージェントモードへのアクセス可否を判定する。"""
        return self.get_trust_level() >= TRUST_COLLEAGUE

    def get_greeting(self) -> str:
        """ユーザーに応じた挨拶を返す。"""
        user = self.get_current_user()
        if user:
            return f"{user.name}さん、こんにちは！"
        return (
            "はじめまして、私はアイちゃんです。"
            "よろしければお名前を教えていただけますか？"
        )

    @property
    def match_threshold(self) -> float:
        """声紋照合の類似度閾値を返す。"""
        return self._match_threshold

    @match_threshold.setter
    def match_threshold(self, value: float) -> None:
        """声紋照合の類似度閾値を設定する。

        Args:
            value: 新しい閾値 (0.0 ~ 1.0)

        Raises:
            ValueError: 範囲外の値が指定された場合
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"閾値は 0.0〜1.0 の範囲で指定してください: {value}"
            )
        self._match_threshold = value

    @property
    def profiles(self) -> Dict[str, VoiceProfile]:
        """登録済みプロファイルの読み取り専用コピーを返す。"""
        return dict(self._profiles)
