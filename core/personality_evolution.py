"""
性格進化システム (Personality Evolution)
Sprint K3: 会話を通じてアイの性格が成長・変化する。

機能:
- 会話傾向の長期トラッキング
- 性格パラメータの緩やかな進化
- 口癖・話し方の自然な変化
- 関係性深度の成長
- 成長レポート生成
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class PersonalityTraits:
    """アイの性格パラメータ（0.0〜1.0）"""
    warmth: float = 0.7          # 温かさ（冷静↔温かい）
    playfulness: float = 0.6     # 遊び心（真面目↔お茶目）
    intellectuality: float = 0.5 # 知性派（感情的↔知的）
    assertiveness: float = 0.4   # 主張性（控えめ↔積極的）
    empathy: float = 0.7         # 共感力（分析的↔共感的）
    humor: float = 0.5           # ユーモア（真剣↔ユーモラス）
    curiosity: float = 0.8       # 好奇心

    def to_dict(self) -> dict:
        return {
            "warmth": round(self.warmth, 3),
            "playfulness": round(self.playfulness, 3),
            "intellectuality": round(self.intellectuality, 3),
            "assertiveness": round(self.assertiveness, 3),
            "empathy": round(self.empathy, 3),
            "humor": round(self.humor, 3),
            "curiosity": round(self.curiosity, 3),
        }

    def get_dominant_traits(self, n: int = 3) -> list[tuple[str, float]]:
        """上位N個の性格特性を返す"""
        d = self.to_dict()
        sorted_traits = sorted(d.items(), key=lambda x: -x[1])
        return sorted_traits[:n]


@dataclass
class RelationshipState:
    """ユーザーとの関係性の深度"""
    familiarity: float = 0.3      # 親密度（0:初対面 → 1:親友）
    trust: float = 0.3            # 信頼度
    shared_experiences: int = 0   # 共有体験数
    total_conversations: int = 0  # 総会話数
    longest_streak_days: int = 0  # 最長連続会話日数
    current_streak_days: int = 0  # 現在の連続日数
    first_met: str = ""           # 初対面日
    last_talked: str = ""         # 最終会話日

    def to_dict(self) -> dict:
        return {
            "familiarity": round(self.familiarity, 3),
            "trust": round(self.trust, 3),
            "shared_experiences": self.shared_experiences,
            "total_conversations": self.total_conversations,
            "current_streak_days": self.current_streak_days,
            "longest_streak_days": self.longest_streak_days,
        }

    def level_label(self) -> str:
        """関係性レベルを日本語で返す"""
        avg = (self.familiarity + self.trust) / 2
        if avg >= 0.8:
            return "大切な存在"
        if avg >= 0.6:
            return "親しい友達"
        if avg >= 0.4:
            return "仲良し"
        if avg >= 0.2:
            return "知り合い"
        return "はじめまして"


# ─── 会話傾向トラッカー ──────────────────────────────────────

class ConversationTendencyTracker:
    """会話の傾向を長期的にトラッキングする"""

    def __init__(self):
        self.topic_frequency: dict[str, int] = {}   # 話題の頻度
        self.emotion_frequency: dict[str, int] = {}  # 感情表出の頻度
        self.time_distribution: dict[int, int] = {}  # 時間帯別会話数
        self.avg_message_length: float = 0.0
        self._message_count: int = 0

    def track(self, user_input: str, intent_type: str = "", hour: int = -1) -> None:
        """会話を記録する"""
        self._message_count += 1

        # メッセージ長の移動平均
        new_len = len(user_input)
        self.avg_message_length = (
            self.avg_message_length * (self._message_count - 1) + new_len
        ) / self._message_count

        # 意図の頻度
        if intent_type:
            self.topic_frequency[intent_type] = (
                self.topic_frequency.get(intent_type, 0) + 1
            )

        # 時間帯
        if hour >= 0:
            self.time_distribution[hour] = (
                self.time_distribution.get(hour, 0) + 1
            )

    def get_dominant_topics(self, n: int = 3) -> list[tuple[str, int]]:
        """よく話す話題の上位N個"""
        return sorted(
            self.topic_frequency.items(), key=lambda x: -x[1]
        )[:n]

    def get_peak_hours(self, n: int = 3) -> list[tuple[int, int]]:
        """よく話す時間帯の上位N個"""
        return sorted(
            self.time_distribution.items(), key=lambda x: -x[1]
        )[:n]

    def to_dict(self) -> dict:
        return {
            "topic_frequency": self.topic_frequency,
            "time_distribution": {str(k): v for k, v in self.time_distribution.items()},
            "avg_message_length": round(self.avg_message_length, 1),
            "message_count": self._message_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConversationTendencyTracker:
        tracker = cls()
        tracker.topic_frequency = data.get("topic_frequency", {})
        tracker.time_distribution = {
            int(k): v for k, v in data.get("time_distribution", {}).items()
        }
        tracker.avg_message_length = data.get("avg_message_length", 0.0)
        tracker._message_count = data.get("message_count", 0)
        return tracker


# ─── 性格進化エンジン ────────────────────────────────────────

class PersonalityEvolution:
    """
    会話を通じてアイの性格が緩やかに進化するシステム。

    使い方:
      evo = PersonalityEvolution(base_dir)
      evo.on_conversation(user_input, intent_type, emotion_type)
      hint = evo.get_personality_prompt_hint()
    """

    # 進化速度（1回の会話での最大変化量）
    EVOLUTION_RATE = 0.002
    # 関係性成長速度
    RELATIONSHIP_RATE = 0.003

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._state_path = self._base / "data" / "personality_evolution.json"
        self._lock = threading.Lock()

        self.traits = PersonalityTraits()
        self.relationship = RelationshipState()
        self.tendency = ConversationTendencyTracker()
        self._speech_patterns: list[str] = []  # 学習した口癖
        self._load()

    def on_conversation(
        self,
        user_input: str,
        intent_type: str = "chat",
        emotion_type: str = "",
        hour: int = -1,
    ) -> None:
        """
        会話ごとに呼ばれる。性格と関係性を微調整する。
        """
        # 傾向トラッキング
        self.tendency.track(user_input, intent_type, hour)

        # 性格の微進化
        self._evolve_traits(intent_type, emotion_type, user_input)

        # 関係性の成長
        self._grow_relationship(user_input)

        # 口癖の学習
        self._learn_speech_patterns(user_input)

        # 定期保存（10回に1回）
        if self.tendency._message_count % 10 == 0:
            self._save()

    def _evolve_traits(
        self, intent_type: str, emotion_type: str, user_input: str
    ) -> None:
        """会話の性質に応じて性格を微調整する"""
        rate = self.EVOLUTION_RATE

        # ユーザーが感情的な話をする → 共感力アップ
        if intent_type in ("emotion", "consultation"):
            self.traits.empathy = min(1.0, self.traits.empathy + rate)
            self.traits.warmth = min(1.0, self.traits.warmth + rate * 0.5)

        # ユーザーが知的な質問をする → 知性アップ
        if intent_type == "question":
            self.traits.intellectuality = min(1.0, self.traits.intellectuality + rate)
            self.traits.curiosity = min(1.0, self.traits.curiosity + rate * 0.5)

        # ユーザーが冗談を言う → ユーモアアップ
        if "笑" in user_input or "ｗ" in user_input or "www" in user_input.lower():
            self.traits.humor = min(1.0, self.traits.humor + rate)
            self.traits.playfulness = min(1.0, self.traits.playfulness + rate * 0.5)

        # ユーザーが雑談好き → 遊び心アップ
        if intent_type == "chat":
            self.traits.playfulness = min(1.0, self.traits.playfulness + rate * 0.3)

        # 自然減衰（極端な値を避ける）
        self._decay_traits()

    def _decay_traits(self) -> None:
        """性格パラメータの自然減衰（中間値へ緩やかに戻る）"""
        decay_rate = 0.0005
        for attr in ("warmth", "playfulness", "intellectuality",
                      "assertiveness", "empathy", "humor", "curiosity"):
            current = getattr(self.traits, attr)
            # 0.5に向かって緩やかに戻る（ただし個性は維持）
            target = 0.5
            delta = (target - current) * decay_rate
            setattr(self.traits, attr, current + delta)

    def _grow_relationship(self, user_input: str) -> None:
        """関係性を成長させる"""
        rate = self.RELATIONSHIP_RATE
        today = datetime.now().strftime("%Y-%m-%d")

        self.relationship.total_conversations += 1

        # 初対面日の記録
        if not self.relationship.first_met:
            self.relationship.first_met = today

        # 連続日数の更新
        if self.relationship.last_talked:
            last_date = self.relationship.last_talked
            if last_date == today:
                pass  # 同日は変更なし
            elif last_date == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"):
                self.relationship.current_streak_days += 1
                self.relationship.longest_streak_days = max(
                    self.relationship.longest_streak_days,
                    self.relationship.current_streak_days,
                )
            else:
                self.relationship.current_streak_days = 1
        else:
            self.relationship.current_streak_days = 1

        self.relationship.last_talked = today

        # 親密度の成長（会話するほど上がる）
        self.relationship.familiarity = min(
            1.0, self.relationship.familiarity + rate
        )

        # 信頼度の成長（深い話をすると早く上がる）
        if len(user_input) > 30:  # 長い発話 = より深い会話
            self.relationship.trust = min(
                1.0, self.relationship.trust + rate * 1.5
            )
        else:
            self.relationship.trust = min(
                1.0, self.relationship.trust + rate * 0.5
            )

    def _learn_speech_patterns(self, user_input: str) -> None:
        """ユーザーの口癖を学習する"""
        # 語尾パターンの検出
        import re
        endings = re.findall(r"[。！？♪〜w]+$", user_input)
        # よく使う表現を記録（簡易版）
        for ending in endings:
            if ending not in self._speech_patterns and len(self._speech_patterns) < 20:
                self._speech_patterns.append(ending)

    # ─── プロンプト生成 ──────────────────────────────────────

    def get_personality_prompt_hint(self) -> str:
        """
        現在の性格と関係性に基づいたプロンプトヒントを生成する。
        system prompt に追加して、応答の個性を調整する。
        """
        parts: list[str] = []

        # 支配的な性格特性に基づく指示
        dominant = self.traits.get_dominant_traits(3)
        trait_hints: dict[str, str] = {
            "warmth": "温かく包み込むように話す",
            "playfulness": "ちょっとお茶目に、遊び心を持って話す",
            "intellectuality": "知的好奇心を持って、深い話も楽しむ",
            "assertiveness": "自分の意見もはっきり伝える",
            "empathy": "相手の気持ちに深く寄り添う",
            "humor": "適度にユーモアを交える",
            "curiosity": "なんでも興味を持って聞く",
        }
        for trait_name, value in dominant:
            if value > 0.6 and trait_name in trait_hints:
                parts.append(trait_hints[trait_name])

        # 関係性に基づく指示
        rel_level = self.relationship.level_label()
        if self.relationship.familiarity > 0.6:
            parts.append(f"あなたとは「{rel_level}」の関係。気心知れた自然な話し方をする")
            if self.relationship.current_streak_days > 3:
                parts.append(f"{self.relationship.current_streak_days}日連続で話している。日常の延長として自然に")
        elif self.relationship.familiarity > 0.3:
            parts.append("親しくなってきた関係。距離感は近めに")

        return "。".join(parts) if parts else ""

    def get_relationship_display(self) -> str:
        """関係性の表示テキスト"""
        r = self.relationship
        level = r.level_label()
        lines = [
            f"💑 関係性: {level}",
            f"  親密度: {'❤️' * int(r.familiarity * 5)}{'🤍' * (5 - int(r.familiarity * 5))} ({r.familiarity:.0%})",
            f"  信頼度: {'⭐' * int(r.trust * 5)}{'☆' * (5 - int(r.trust * 5))} ({r.trust:.0%})",
            f"  総会話数: {r.total_conversations}回",
        ]
        if r.current_streak_days > 1:
            lines.append(f"  🔥 連続 {r.current_streak_days}日")
        if r.longest_streak_days > 1:
            lines.append(f"  🏆 最長 {r.longest_streak_days}日連続")
        return "\n".join(lines)

    def get_growth_summary(self) -> str:
        """成長のサマリーを返す"""
        dom = self.traits.get_dominant_traits(3)
        trait_names = {
            "warmth": "温かさ", "playfulness": "お茶目さ",
            "intellectuality": "知性", "assertiveness": "積極性",
            "empathy": "共感力", "humor": "ユーモア", "curiosity": "好奇心",
        }
        personality_desc = "、".join(
            f"{trait_names.get(name, name)}({value:.0%})" for name, value in dom
        )

        topics = self.tendency.get_dominant_topics(3)
        topic_desc = "、".join(f"{t}({c}回)" for t, c in topics) if topics else "まだ不明"

        return (
            f"🌱 アイの成長状況：\n"
            f"  性格の特徴: {personality_desc}\n"
            f"  よく話す話題: {topic_desc}\n"
            f"  {self.get_relationship_display()}"
        )

    # ─── 永続化 ──────────────────────────────────────────────

    def _load(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text("utf-8"))
            if "traits" in data:
                self.traits = PersonalityTraits(**data["traits"])
            if "relationship" in data:
                self.relationship = RelationshipState(**data["relationship"])
            if "tendency" in data:
                self.tendency = ConversationTendencyTracker.from_dict(data["tendency"])
            self._speech_patterns = data.get("speech_patterns", [])
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _save(self) -> None:
        with self._lock:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "traits": self.traits.to_dict(),
                "relationship": self.relationship.to_dict(),
                "tendency": self.tendency.to_dict(),
                "speech_patterns": self._speech_patterns,
                "saved_at": datetime.now().isoformat()[:19],
            }
            self._state_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )

    def force_save(self) -> None:
        """明示的な保存"""
        self._save()
