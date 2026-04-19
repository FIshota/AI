"""
BGM 提案エンジン（Sprint 4-C）
アイの感情状態に合わせて YouTube 検索 URL を生成して音楽を提案する。
Spotify / Apple Music API は使わず、無料・APIキー不要。
"""
from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_YOUTUBE_BASE = "https://www.youtube.com/results?search_query="


@dataclass
class BGMSuggestion:
    mood: str
    playlist_name: str
    youtube_url: str   # https://www.youtube.com/results?search_query=...
    message: str       # 「今の気分に合いそうな曲だよ」


class BGMSuggester:
    """アイの感情状態に合わせて音楽を提案する。"""

    MOOD_PLAYLISTS: dict[str, list[str]] = {
        "happy":     ["明るい BGM 作業用", "ポップス 元気"],
        "focused":   ["集中 BGM ローファイ", "勉強 BGM"],
        "calm":      ["リラックス BGM 自然音", "ジャズ カフェ"],
        "energetic": ["アップテンポ BGM", "モチベーション 音楽"],
        "sad":       ["癒し BGM ピアノ", "スローテンポ"],
    }

    # 感情キー → ムードのマッピング
    _EMOTION_TO_MOOD: dict[str, str] = {
        "happiness": "happy",
        "curiosity": "focused",
        "affection": "calm",
        "energy": "energetic",
        "anxiety": "calm",   # 不安が高いときは落ち着く音楽
    }

    _MOOD_MESSAGES: dict[str, str] = {
        "happy":     "今の気分に合いそうな明るい曲だよ🎵 楽しんでね！",
        "focused":   "集中できそうな BGM を選んだよ🎧 頑張ってね！",
        "calm":      "落ち着いた雰囲気の曲だよ🎶 ゆっくりしてね。",
        "energetic": "テンションあがる曲だよ🎸 一緒に盛り上がろう！",
        "sad":       "癒してくれる曲を選んだよ🎹 ゆっくり聴いてね。",
    }

    def suggest(self, emotion_state: dict | None = None) -> BGMSuggestion:
        """
        感情状態からムードを判定し、YouTube 検索 URL を含む BGMSuggestion を返す。
        emotion_state は {"happiness": 0.7, "energy": 0.8, ...} 形式。
        """
        try:
            mood = self._detect_mood(emotion_state or {})
            playlists = self.MOOD_PLAYLISTS.get(mood, self.MOOD_PLAYLISTS["calm"])
            # リストの最初を採用（拡張時にランダム選択に変更可）
            playlist_name = playlists[0]
            youtube_url = _YOUTUBE_BASE + urllib.parse.quote(playlist_name)
            message = self._MOOD_MESSAGES.get(mood, "今の気分に合いそうな曲だよ🎵")

            return BGMSuggestion(
                mood=mood,
                playlist_name=playlist_name,
                youtube_url=youtube_url,
                message=message,
            )
        except Exception as e:
            logger.warning("[BGMSuggester] suggest error: %s", e)
            # フォールバック
            fallback_name = "リラックス BGM"
            return BGMSuggestion(
                mood="calm",
                playlist_name=fallback_name,
                youtube_url=_YOUTUBE_BASE + urllib.parse.quote(fallback_name),
                message="BGM を探してみたよ🎵",
            )

    def suggest_with_entropy(self, text: str, emotion_state: dict | None = None) -> BGMSuggestion:
        """
        アカシックエントロピーを使ったBGM提案。
        テキストの感情エントロピーを計測し、
        高エントロピー(複雑感情) → 安定化音楽
        低エントロピー(単純感情) → 感情増幅音楽
        """
        suggestion = self.suggest(emotion_state)
        try:
            from core.akashic.entropy_engine import EntropyEngine
            profile = EntropyEngine().profile(text)
            entropy = profile.domain_diversity * 0.6 + profile.unique_word_ratio * 0.4
            # 高エントロピー(0.6+) = 複雑感情 → 落ち着かせる方向に補正
            if entropy > 0.6:
                mood = "calm"
                playlists = self.MOOD_PLAYLISTS.get(mood, self.MOOD_PLAYLISTS["calm"])
                import random as _r
                query = _r.choice(playlists)
                import urllib.parse as _u
                return BGMSuggestion(
                    mood=mood,
                    playlist_name=query,
                    youtube_url=_YOUTUBE_BASE + _u.quote(query),
                    message=f"気持ちが複雑そうだから、少し落ち着ける音楽にしてみたよ🎵 (エントロピー={entropy:.2f})",
                )
        except Exception:
            pass
        return suggestion

    # ──────────────────────────────────────────────────────────────
    # 内部ヘルパー
    # ──────────────────────────────────────────────────────────────

    def _detect_mood(self, emotion_state: dict) -> str:
        """
        感情状態辞書から支配的なムードを判定する。
        anxiety が高い（0.6 以上）場合は calm を返す。
        """
        if not emotion_state:
            return "calm"

        anxiety = float(emotion_state.get("anxiety", 0.0))
        if anxiety >= 0.6:
            return "calm"

        # anxiety を除く感情値の最大値
        relevant = {
            k: float(v)
            for k, v in emotion_state.items()
            if k != "anxiety" and k in self._EMOTION_TO_MOOD
        }
        if not relevant:
            return "calm"

        dominant_emotion = max(relevant, key=relevant.get)
        mood = self._EMOTION_TO_MOOD.get(dominant_emotion, "calm")

        # energy > 0.8 は energetic に上書き
        energy = float(emotion_state.get("energy", 0.0))
        if energy >= 0.8:
            mood = "energetic"

        return mood
