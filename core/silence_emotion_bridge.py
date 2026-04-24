"""
沈黙イベントを感情状態に反映させる薄いアダプタ層。

設計原則:
- `core/emotion.py` は非改変。EmotionState を "読み取り + 新しいインスタンスを返す" 形で immutable update。
- EmotionState は frozen ではないが、本モジュールは原本を破壊的変更しない (dataclasses.replace 相当を手書き)。
- 規則は家族生活で観察される沈黙の意味づけに基づく。詳細は docs/design/SILENCE_AWARE.md。

Python 3.9 互換, stdlib のみ。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.silence_token import SilenceCategory, SilenceEvent

if TYPE_CHECKING:
    from core.emotion import EmotionState  # 型参照のみ


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _copy_state(state: Any) -> Any:
    """EmotionState を複製 (import を実行時に遅延して循環を避ける)。"""
    from core.emotion import EmotionState

    return EmotionState(
        happiness=state.happiness,
        curiosity=state.curiosity,
        affection=state.affection,
        energy=state.energy,
        anxiety=state.anxiety,
    )


def apply_silence_to_emotion(emotion_state: Any, event: SilenceEvent) -> Any:
    """
    沈黙イベントを感情状態に適用し、新しい EmotionState を返す (immutable update)。

    規則 (設計根拠):
      - MICRO    : turn 内の自然な pause。会話のテンポの一部で、感情に影響は与えない。
      - SHORT    : 考え込み。穏やかな期待・関心が生まれる → curiosity +0.02。
      - MEDIUM   : 同じ空間で別作業中の同席感。
                   context="作業中同席" なら安心感 → affection +0.05。
      - LONG     : 長時間の沈黙。軽微な不安と気疲れ → anxiety +0.05, energy -0.03。
      - ABSENT   : 不在 (3h超)。不安と寂しさ → anxiety +0.15, happiness -0.10。
                   ただし context="就寝中" は正常な不在なので影響ゼロ。
    """
    new_state = _copy_state(emotion_state)
    cat = event.category
    ctx = event.ambient_context

    if cat is SilenceCategory.MICRO:
        # 影響なし
        pass
    elif cat is SilenceCategory.SHORT:
        new_state.curiosity = _clamp(new_state.curiosity + 0.02)
    elif cat is SilenceCategory.MEDIUM:
        if ctx == "作業中同席":
            new_state.affection = _clamp(new_state.affection + 0.05)
    elif cat is SilenceCategory.LONG:
        new_state.anxiety = _clamp(new_state.anxiety + 0.05)
        new_state.energy = _clamp(new_state.energy - 0.03)
    elif cat is SilenceCategory.ABSENT:
        if ctx == "就寝中":
            # 正常な夜間の沈黙 — 感情に影響させない
            pass
        else:
            new_state.anxiety = _clamp(new_state.anxiety + 0.15)
            new_state.happiness = _clamp(new_state.happiness - 0.10)

    return new_state


__all__ = ["apply_silence_to_emotion"]
