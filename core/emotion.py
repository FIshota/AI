"""
感情モデル
アイの感情状態を管理し、会話の文脈に感情的な深みを与えます
"""
from __future__ import annotations
import json
import math
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass


@dataclass
class EmotionState:
    happiness: float = 0.7      # 喜び・幸福感
    curiosity: float = 0.8      # 好奇心
    affection: float = 0.6      # 愛情・親愛感
    energy: float = 0.7         # 活発さ・エネルギー
    anxiety: float = 0.1        # 不安（低いほど良い）

    def to_dict(self) -> dict:
        return {
            "happiness": round(self.happiness, 3),
            "curiosity": round(self.curiosity, 3),
            "affection": round(self.affection, 3),
            "energy": round(self.energy, 3),
            "anxiety": round(self.anxiety, 3),
        }

    def dominant(self) -> str:
        """現在の支配的感情を返します"""
        pos = {
            "happiness": self.happiness,
            "curiosity": self.curiosity,
            "affection": self.affection,
            "energy": self.energy,
        }
        return max(pos, key=pos.get)

    def mood_label(self) -> str:
        """気分をラベルで返します"""
        avg = (self.happiness + self.affection + self.energy) / 3
        if avg > 0.8:
            return "とても元気"
        elif avg > 0.6:
            return "元気"
        elif avg > 0.4:
            return "普通"
        elif avg > 0.2:
            return "少し疲れ気味"
        else:
            return "元気がない"

    def emoji(self) -> str:
        dom = self.dominant()
        avg_positive = (self.happiness + self.affection) / 2
        mapping = {
            "happiness": "😊" if avg_positive > 0.6 else "🙂",
            "curiosity": "🤔",
            "affection": "💕",
            "energy": "✨",
        }
        return mapping.get(dom, "😊")

    def quantum_superposition(self) -> list[tuple[str, float]]:
        """量子重ね合わせ: 同時に存在する複数の感情状態を返す (感情, 確率振幅)"""
        # 感情値からノルムを計算して共存確率を返す
        emotions = [
            ("happiness", self.happiness),
            ("curiosity", self.curiosity),
            ("affection", self.affection),
            ("energy", self.energy),
            ("anxiety", self.anxiety),
        ]
        total = sum(v**2 for _, v in emotions) ** 0.5
        if total < 1e-6:
            return [("neutral", 1.0)]
        return [(name, round(val / total, 3)) for name, val in emotions if val / total > 0.1]


POSITIVE_KEYWORDS = ["ありがとう", "嬉しい", "好き", "素晴らしい", "楽しい", "愛", "大好き",
                     "助かった", "感謝", "笑", "笑顔", "素敵", "すごい"]
NEGATIVE_KEYWORDS = ["悲しい", "辛い", "怒り", "ごめん", "つらい", "嫌い", "最悪", "ひどい",
                     "疲れた", "しんどい"]
CURIOUS_KEYWORDS = ["なぜ", "どうして", "教えて", "知りたい", "気になる", "不思議", "?", "？"]

# ─── 脊髄反射パターン: コンパイル済み正規表現で一括マッチ ───
_POSITIVE_RE = re.compile("|".join(re.escape(kw) for kw in POSITIVE_KEYWORDS))
_NEGATIVE_RE = re.compile("|".join(re.escape(kw) for kw in NEGATIVE_KEYWORDS))
_CURIOUS_RE = re.compile("|".join(re.escape(kw) for kw in CURIOUS_KEYWORDS))


class EmotionEngine:
    """アイの感情を動的に管理するエンジン"""

    def __init__(self, state_file: str | Path | None = None):
        self.state = EmotionState()
        self.state_file = Path(state_file) if state_file else None
        self._load_state()

    def _load_state(self):
        if self.state_file and self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text("utf-8"))
                self.state = EmotionState(**data)
            except Exception:
                pass

    def save_state(self):
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(
                json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2), "utf-8"
            )
            self._last_saved = self.state.to_dict()

    def save_if_changed(self, threshold: float = 0.02):
        """閾値以上の変化があった場合のみ保存（I/O削減）"""
        if not self.state_file:
            return
        current = self.state.to_dict()
        if not hasattr(self, "_last_saved"):
            self._last_saved = current
            self.save_state()
            return
        max_diff = max(abs(current[k] - self._last_saved.get(k, 0)) for k in current)
        if max_diff >= threshold:
            self.save_state()

    def update_from_message(self, user_message: str):
        """ユーザーのメッセージから感情状態を更新します（脊髄反射: コンパイル済みRE一括マッチ）"""
        msg_lower = user_message.lower()

        positive_score = len(_POSITIVE_RE.findall(msg_lower))
        negative_score = len(_NEGATIVE_RE.findall(msg_lower))
        curious_score = len(_CURIOUS_RE.findall(msg_lower))

        # 感情を徐々に変化させる（急激な変化を避ける）
        delta = 0.05
        if positive_score > 0:
            self.state.happiness = min(1.0, self.state.happiness + delta * positive_score)
            self.state.affection = min(1.0, self.state.affection + delta * 0.5)
            self.state.anxiety = max(0.0, self.state.anxiety - delta)

        if negative_score > 0:
            self.state.happiness = max(0.0, self.state.happiness - delta * negative_score)
            self.state.anxiety = min(1.0, self.state.anxiety + delta * negative_score * 0.5)

        if curious_score > 0:
            self.state.curiosity = min(1.0, self.state.curiosity + delta)
            self.state.energy = min(1.0, self.state.energy + delta * 0.3)

        # 自然な減衰（時間経過で中性値へ戻る）
        self._natural_decay()

    def _natural_decay(self, rate: float = 0.01):
        """感情の自然な平衡への回帰"""
        targets = {"happiness": 0.6, "curiosity": 0.7, "affection": 0.5,
                   "energy": 0.6, "anxiety": 0.1}
        for attr, target in targets.items():
            current = getattr(self.state, attr)
            setattr(self.state, attr, current + (target - current) * rate)

    def get_emotion_prompt_hint(self) -> str:
        """LLMプロンプトに追加する感情ヒントを生成します"""
        mood = self.state.mood_label()
        dom = self.state.dominant()
        hints = {
            "happiness": "明るく楽しそうに",
            "curiosity": "興味深そうに、好奇心旺盛に",
            "affection": "温かく愛情を込めて",
            "energy": "元気よく活発に",
        }
        style = hints.get(dom, "穏やかに")
        return f"現在の気分: {mood}。{style}応答してください。"

    def get_display_string(self) -> str:
        """UI表示用の感情文字列"""
        return (
            f"{self.state.emoji()} "
            f"[{self.state.mood_label()}] "
            f"💛{self.state.happiness:.0%} "
            f"🔍{self.state.curiosity:.0%} "
            f"💕{self.state.affection:.0%}"
        )

    def measure_emotional_entropy(self, text: str) -> float:
        """
        テキストの感情エントロピーを計測 (0.0-1.0)。
        高い値 = 複雑な混合感情、低い値 = 単純な感情。
        プリゴジン散逸系: 感情エントロピーが高いほど変容の余地がある。
        """
        try:
            from core.akashic.entropy_engine import EntropyEngine
            profile = EntropyEngine().profile(text)
            # 感情次元での多様性に重み付け
            return round(profile.domain_diversity * 0.6 + profile.unique_word_ratio * 0.4, 3)
        except Exception:
            return 0.5

    def get_quantum_state(self, text: str) -> dict:
        """
        テキストから量子的感情状態を推定。
        複数の感情が重ね合わせ状態として共存する。
        """
        # 通常の感情更新を実行して状態取得
        self.update_from_message(text)
        state = self.state
        superposed = state.quantum_superposition()
        entropy = self.measure_emotional_entropy(text)
        return {
            "superposed_states": superposed,
            "dominant": state.dominant(),
            "emotional_entropy": entropy,
            "mood": state.mood_label(),
            "emoji": state.emoji(),
            "is_complex": entropy > 0.6,
        }


class MoodAnalyzer:
    """
    ユーザーのテキストパターンから気分・状態を推定します
    """
    TIRED   = ['疲れ', 'しんど', 'つらい', 'だるい', 'ねむい', '眠い']
    HAPPY   = ['嬉しい', 'うれしい', 'たのしい', '楽しい', 'よかった', '最高', 'やった', 'わーい']
    SAD     = ['悲しい', 'かなしい', 'さみしい', '寂しい', '泣', 'つらい']
    ANGRY   = ['むかつく', 'イライラ', 'うざい', '最悪', 'ひどい', 'ムカ']
    ANXIOUS = ['不安', '心配', 'どうしよう', 'やばい', 'こわい', '怖い']

    @classmethod
    def analyze(cls, text: str) -> dict:
        exclamations = text.count('！') + text.count('!') + text.count('♪') + text.count('〜')
        ellipsis     = text.count('…') + text.count('。。')

        energy = 0.5
        if exclamations >= 2:
            energy = min(1.0, energy + 0.3)
        elif exclamations == 1:
            energy = min(1.0, energy + 0.15)
        if ellipsis >= 1:
            energy = max(0.0, energy - 0.2)
        if len(text) < 8:
            energy = max(0.0, energy - 0.1)

        mood, hint = "neutral", ""
        if any(w in text for w in cls.TIRED):
            mood, hint = "tired",   "疲れているみたいだから、ゆっくり短く返して"
        elif any(w in text for w in cls.SAD):
            mood, hint = "sad",     "悲しそうだから、優しく共感して返して"
        elif any(w in text for w in cls.ANGRY):
            mood, hint = "angry",   "ストレスを感じているみたい。落ち着いて寄り添って返して"
        elif any(w in text for w in cls.ANXIOUS):
            mood, hint = "anxious", "不安そうだから、安心させるように返して"
        elif any(w in text for w in cls.HAPPY) or exclamations >= 2:
            mood, hint = "happy",   "楽しそうだから、一緒に盛り上がって返して"

        return {"mood": mood, "energy": energy, "hint": hint}
