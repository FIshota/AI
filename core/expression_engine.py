"""
表情エンジン (Expression Engine)
Sprint 3.0-D: 感情に連動してキャラクターの表情・色味を変える。

Pillow で元画像にリアルタイムで色調補正をかけて感情を視覚化する。
別途表情差分画像がある場合はそちらを優先使用する。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PILImage

try:
    from PIL import Image, ImageEnhance, ImageFilter
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


# 感情 → 視覚パラメータのマッピング
# (color_shift_hue, saturation_mult, brightness_mult, blur_radius)
EMOTION_VISUAL = {
    "happy":    (0.0,   1.15, 1.08, 0),      # 明るく鮮やか
    "excited":  (0.0,   1.25, 1.12, 0),      # より鮮やかに
    "calm":     (0.0,   0.95, 1.00, 0),      # 落ち着いた色
    "sad":      (0.0,   0.70, 0.85, 0.5),    # 彩度低下、暗め
    "anxious":  (0.0,   0.85, 0.92, 0),      # やや暗い
    "tired":    (0.0,   0.75, 0.88, 1.0),    # 彩度低下、ぼかし
    "angry":    (0.0,   1.20, 0.95, 0),      # 鮮やか、やや暗い
    "neutral":  (0.0,   1.00, 1.00, 0),      # そのまま
}


def classify_emotion(emotion_state: dict) -> str:
    """EmotionState の dict から主要な感情を分類する"""
    happiness = emotion_state.get("happiness", 0.5)
    energy = emotion_state.get("energy", 0.5)
    anxiety = emotion_state.get("anxiety", 0.1)
    affection = emotion_state.get("affection", 0.5)

    if anxiety > 0.6:
        return "anxious"
    if happiness > 0.8 and energy > 0.7:
        return "excited"
    if happiness > 0.6:
        return "happy"
    if happiness < 0.3:
        return "sad"
    if energy < 0.3:
        return "tired"
    if happiness < 0.4 and energy > 0.6:
        return "angry"
    return "calm" if affection > 0.5 else "neutral"


class ExpressionEngine:
    """
    感情状態に応じてキャラクター画像を変化させる。

    使い方:
      expr = ExpressionEngine(base_dir)
      modified_image = expr.apply_emotion(base_image, emotion_dict)
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._expressions_dir = self._base / "assets" / "expressions"
        self._expression_cache: dict[str, "PILImage.Image"] = {}
        self._last_emotion = "neutral"

    def apply_emotion(
        self,
        base_image: "PILImage.Image",
        emotion_state: dict,
    ) -> "PILImage.Image":
        """
        感情に応じて画像を加工して返す。
        元画像は変更しない（新しいImageを返す）。
        """
        if not PILLOW_AVAILABLE:
            return base_image

        emotion = classify_emotion(emotion_state)
        self._last_emotion = emotion

        # 表情差分画像があればそちらを優先
        expr_image = self._load_expression(emotion)
        if expr_image is not None:
            return expr_image

        # なければ色調補正で表現
        return self._apply_color_shift(base_image, emotion)

    def get_current_emotion(self) -> str:
        return self._last_emotion

    def get_emotion_emoji(self) -> str:
        """現在の感情に対応する絵文字を返す"""
        emoji_map = {
            "happy": "😊",
            "excited": "🤩",
            "calm": "😌",
            "sad": "😢",
            "anxious": "😰",
            "tired": "😴",
            "angry": "😤",
            "neutral": "🙂",
        }
        return emoji_map.get(self._last_emotion, "🙂")

    # ─── private ─────────────────────────────────────────────

    def _load_expression(self, emotion: str) -> "PILImage.Image | None":
        """
        assets/expressions/{emotion}.png があればロードして返す。
        なければ None。
        """
        if emotion in self._expression_cache:
            return self._expression_cache[emotion]

        path = self._expressions_dir / f"{emotion}.png"
        if not path.exists():
            return None

        try:
            img = Image.open(path).convert("RGBA")
            self._expression_cache[emotion] = img
            return img
        except Exception:
            return None

    def _apply_color_shift(
        self,
        base_image: "PILImage.Image",
        emotion: str,
    ) -> "PILImage.Image":
        """Pillow で色調補正を適用する"""
        params = EMOTION_VISUAL.get(emotion, EMOTION_VISUAL["neutral"])
        _, sat_mult, bright_mult, blur_radius = params

        img = base_image.copy()

        # 彩度調整
        if abs(sat_mult - 1.0) > 0.01:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(sat_mult)

        # 明度調整
        if abs(bright_mult - 1.0) > 0.01:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(bright_mult)

        # ぼかし（疲れ・悲しみ）
        if blur_radius > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        return img
