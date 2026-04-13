"""
合成データ生成 (Synthetic Data Generator)
ヤマト計画 C6: AIが自ら学習用データを生成し、自己強化する。

機能:
- 会話パターンからテンプレートを抽出
- テンプレートベースの新規会話生成
- 品質フィルタリング（生成データの自動検証）
- バリエーション生成（同一意図の多様な表現）
- 生成データの統計管理
"""
from __future__ import annotations

import json
import random
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ConversationTemplate:
    """会話テンプレート"""
    intent: str                    # greeting, question, emotion, etc.
    user_patterns: list[str]       # ユーザー入力パターン（{slot}で可変部分）
    ai_patterns: list[str]         # AI応答パターン
    slots: dict[str, list[str]] = field(default_factory=dict)  # slot名→値リスト
    usage_count: int = 0

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "user_patterns": self.user_patterns[:10],
            "ai_patterns": self.ai_patterns[:10],
            "slots": {k: v[:20] for k, v in self.slots.items()},
            "usage_count": self.usage_count,
        }


@dataclass
class GeneratedExample:
    """生成された会話例"""
    user: str
    ai: str
    intent: str
    template_id: str
    quality_score: float = 0.5
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "user": self.user,
            "ai": self.ai,
            "intent": self.intent,
            "template_id": self.template_id,
            "quality_score": self.quality_score,
            "created_at": self.created_at,
        }


# ─── デフォルトテンプレート ───────────────────────────────────

_DEFAULT_TEMPLATES: list[ConversationTemplate] = [
    ConversationTemplate(
        intent="greeting",
        user_patterns=[
            "おはよう", "おはよー", "おはようございます",
            "こんにちは", "こんにちはー",
            "こんばんは", "やっほー", "ただいま",
        ],
        ai_patterns=[
            "おはよー！今日も頑張ろうね！",
            "おはよ～！よく眠れた？",
            "こんにちは！元気してた？",
            "やっほー！何してたの？",
            "おかえり～！待ってたよ！",
        ],
    ),
    ConversationTemplate(
        intent="emotion_positive",
        user_patterns=[
            "{event}で嬉しい！", "今日{event}があってテンション上がった",
            "{event}だった！最高！", "{event}で楽しかった！",
        ],
        ai_patterns=[
            "わー！それは嬉しいね！{reaction}",
            "すごーい！{reaction}",
            "いいなぁ！{reaction}",
            "やったね！{reaction}",
        ],
        slots={
            "event": [
                "テストで100点取れた", "好きな人と話せた", "推しの新曲出た",
                "バイト先で褒められた", "友達と遊んだ", "料理がうまくいった",
                "ゲームでクリアした", "プレゼントもらった",
            ],
            "reaction": [
                "もっと詳しく聞かせて！", "アイも嬉しくなっちゃう！",
                "どんな感じだった？", "いい一日だったね！",
            ],
        },
    ),
    ConversationTemplate(
        intent="emotion_negative",
        user_patterns=[
            "{event}で落ち込んでる", "{event}が辛い",
            "今日{event}で最悪だった", "{event}で悲しい",
        ],
        ai_patterns=[
            "それは大変だったね…{empathy}",
            "辛かったね。{empathy}",
            "そっか…{empathy}",
        ],
        slots={
            "event": [
                "仕事でミスした", "友達と喧嘩した", "テストの点が悪かった",
                "体調が悪い", "寝不足", "上司に怒られた",
            ],
            "empathy": [
                "でもアイはずっと味方だよ", "ゆっくり休んでね",
                "話聞くよ？", "無理しないでね",
            ],
        },
    ),
    ConversationTemplate(
        intent="question",
        user_patterns=[
            "{topic}って何？", "{topic}について教えて",
            "{topic}ってどういう意味？", "{topic}知ってる？",
        ],
        ai_patterns=[
            "{topic}はね、{answer}って感じかな！",
            "えっとね、{answer}だよ！",
            "アイが知ってる範囲だと、{answer}って感じ！",
        ],
        slots={
            "topic": [
                "AI", "プログラミング", "機械学習", "Python",
                "ニューラルネットワーク", "データベース",
            ],
            "answer": [
                "コンピューターが自分で学ぶ仕組みのこと",
                "人間みたいに考えられるようにする技術のこと",
                "いろんなことを自動でやってくれるプログラムのこと",
            ],
        },
    ),
    ConversationTemplate(
        intent="daily_chat",
        user_patterns=[
            "今日{activity}した", "{activity}してきた",
            "さっき{activity}してた", "{activity}なう",
        ],
        ai_patterns=[
            "おー！{activity}！{follow_up}",
            "いいね！{follow_up}",
            "お疲れさま！{follow_up}",
        ],
        slots={
            "activity": [
                "ご飯食べ", "散歩", "買い物", "掃除",
                "勉強", "ゲーム", "運動", "料理",
            ],
            "follow_up": [
                "どうだった？", "楽しかった？", "疲れてない？",
                "何か発見あった？",
            ],
        },
    ),
]


class SyntheticDataGenerator:
    """
    合成データ生成エンジン。
    テンプレートベースで新しい会話例を自動生成し、
    学習データを拡張する。
    """

    # 1回の生成バッチの最大数
    MAX_BATCH_SIZE = 50
    # 保持する最大生成例数
    MAX_STORED_EXAMPLES = 500

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._data_path = self._base / "data" / "synthetic_data.json"
        self._templates: list[ConversationTemplate] = list(_DEFAULT_TEMPLATES)
        self._generated: list[GeneratedExample] = []
        self._lock = threading.Lock()
        self._stats = {
            "total_generated": 0,
            "total_accepted": 0,
            "total_rejected": 0,
        }
        self._load()

    # ─── テンプレート管理 ────────────────────────────────────

    def add_template(self, template: ConversationTemplate) -> None:
        """テンプレートを追加する"""
        with self._lock:
            self._templates.append(template)

    def learn_template_from_conversation(
        self, user_input: str, ai_response: str, intent: str = ""
    ) -> bool:
        """
        実際の会話からテンプレートのバリエーションを学習する。
        既存テンプレートの user_patterns / ai_patterns に追加。
        """
        if len(user_input) < 2 or len(ai_response) < 2:
            return False
        if len(user_input) > 100 or len(ai_response) > 200:
            return False

        # 意図が指定されていない場合、既存テンプレートから推測
        if not intent:
            intent = self._guess_intent(user_input)

        with self._lock:
            for tmpl in self._templates:
                if tmpl.intent == intent:
                    if user_input not in tmpl.user_patterns:
                        tmpl.user_patterns.append(user_input[:100])
                    if ai_response not in tmpl.ai_patterns:
                        tmpl.ai_patterns.append(ai_response[:200])
                    return True

        return False

    def _guess_intent(self, text: str) -> str:
        """テキストから意図を推測する"""
        greetings = ["おはよう", "こんにちは", "こんばんは", "ただいま", "やっほー"]
        if any(g in text for g in greetings):
            return "greeting"

        positive = ["嬉しい", "楽しい", "最高", "すごい", "やった"]
        if any(p in text for p in positive):
            return "emotion_positive"

        negative = ["辛い", "悲しい", "落ち込", "最悪", "疲れ"]
        if any(n in text for n in negative):
            return "emotion_negative"

        question = ["って何", "教えて", "どういう", "知ってる", "なぜ"]
        if any(q in text for q in question):
            return "question"

        return "daily_chat"

    # ─── データ生成 ──────────────────────────────────────────

    def generate_batch(self, count: int = 10, intent: str = "") -> list[dict]:
        """
        合成会話データをバッチ生成する。
        intent指定で特定の意図のデータのみ生成可能。
        """
        count = min(count, self.MAX_BATCH_SIZE)
        results: list[dict] = []

        # 対象テンプレートを選択
        templates = self._templates
        if intent:
            templates = [t for t in templates if t.intent == intent]
            if not templates:
                templates = self._templates

        now = datetime.now().isoformat()[:19]

        for _ in range(count):
            tmpl = random.choice(templates)
            example = self._generate_from_template(tmpl, now)
            if example is None:
                continue

            # 品質チェック
            if self._validate_generated(example):
                with self._lock:
                    self._generated.append(example)
                    tmpl.usage_count += 1
                    self._stats["total_generated"] += 1
                    self._stats["total_accepted"] += 1
                results.append(example.to_dict())
            else:
                self._stats["total_rejected"] += 1

        # ストレージ制限
        if len(self._generated) > self.MAX_STORED_EXAMPLES:
            with self._lock:
                self._generated = self._generated[-self.MAX_STORED_EXAMPLES:]

        self._save()
        return results

    def _generate_from_template(
        self, tmpl: ConversationTemplate, timestamp: str
    ) -> GeneratedExample | None:
        """テンプレートから1つの会話例を生成する"""
        if not tmpl.user_patterns or not tmpl.ai_patterns:
            return None

        user_pattern = random.choice(tmpl.user_patterns)
        ai_pattern = random.choice(tmpl.ai_patterns)

        # スロット置換
        user_text = self._fill_slots(user_pattern, tmpl.slots)
        ai_text = self._fill_slots(ai_pattern, tmpl.slots)

        return GeneratedExample(
            user=user_text,
            ai=ai_text,
            intent=tmpl.intent,
            template_id=tmpl.intent,
            quality_score=0.6,  # テンプレートベースなので中程度
            created_at=timestamp,
        )

    def _fill_slots(self, pattern: str, slots: dict[str, list[str]]) -> str:
        """パターン内の{slot}をランダムな値で置換する"""
        result = pattern
        for slot_name, values in slots.items():
            if values and f"{{{slot_name}}}" in result:
                result = result.replace(f"{{{slot_name}}}", random.choice(values))
        return result

    def _validate_generated(self, example: GeneratedExample) -> bool:
        """生成された例の品質を検証する"""
        # 最低限の長さ
        if len(example.user) < 2 or len(example.ai) < 2:
            return False
        # 未置換スロットがないか
        if "{" in example.user or "{" in example.ai:
            return False
        # 重複チェック
        for existing in self._generated[-50:]:
            if existing.user == example.user and existing.ai == example.ai:
                return False
        return True

    # ─── 生成データ取得 ──────────────────────────────────────

    def get_examples(
        self, count: int = 10, intent: str = "", min_quality: float = 0.0
    ) -> list[dict]:
        """生成済みの合成データを取得する"""
        candidates = self._generated

        if intent:
            candidates = [e for e in candidates if e.intent == intent]
        if min_quality > 0:
            candidates = [e for e in candidates if e.quality_score >= min_quality]

        if not candidates:
            return []

        selected = random.sample(candidates, min(count, len(candidates)))
        return [e.to_dict() for e in selected]

    def get_as_few_shot(self, count: int = 3, intent: str = "") -> str:
        """生成データをfew-shotテキストとして返す"""
        examples = self.get_examples(count=count, intent=intent)
        if not examples:
            return ""
        lines = [f'{e["user"]} → {e["ai"]}' for e in examples]
        return "合成Examples:\n" + "\n".join(lines)

    # ─── 統計 ────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """生成統計を返す"""
        intent_dist: dict[str, int] = defaultdict(int)
        for e in self._generated:
            intent_dist[e.intent] += 1

        return {
            **self._stats,
            "stored_examples": len(self._generated),
            "templates": len(self._templates),
            "intent_distribution": dict(intent_dist),
        }

    def get_status_text(self) -> str:
        """ステータステキスト"""
        stats = self.get_stats()
        lines = [
            f"🧬 合成データ生成エンジン：",
            f"  テンプレート数: {stats['templates']}",
            f"  生成済み: {stats['stored_examples']}例",
            f"  総生成: {stats['total_generated']}回",
            f"  品質通過率: {self._acceptance_rate():.0%}",
        ]
        if stats["intent_distribution"]:
            lines.append("  意図分布:")
            for intent, count in sorted(
                stats["intent_distribution"].items(), key=lambda x: -x[1]
            )[:5]:
                lines.append(f"    {intent}: {count}例")
        return "\n".join(lines)

    def _acceptance_rate(self) -> float:
        """品質通過率"""
        total = self._stats["total_accepted"] + self._stats["total_rejected"]
        if total == 0:
            return 1.0
        return self._stats["total_accepted"] / total

    @property
    def template_count(self) -> int:
        return len(self._templates)

    @property
    def generated_count(self) -> int:
        return len(self._generated)

    # ─── 永続化 ──────────────────────────────────────────────

    def _load(self) -> None:
        if not self._data_path.exists():
            return
        try:
            data = json.loads(self._data_path.read_text("utf-8"))
            for e_data in data.get("generated", []):
                self._generated.append(GeneratedExample(**e_data))
            self._stats.update(data.get("stats", {}))
            # カスタムテンプレートの復元
            for t_data in data.get("custom_templates", []):
                tmpl = ConversationTemplate(**t_data)
                # デフォルトと重複しないか確認
                existing_intents = {t.intent for t in self._templates}
                if tmpl.intent not in existing_intents:
                    self._templates.append(tmpl)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _save(self) -> None:
        with self._lock:
            self._data_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "generated": [e.to_dict() for e in self._generated[-self.MAX_STORED_EXAMPLES:]],
                "stats": self._stats,
                "custom_templates": [],
                "updated_at": datetime.now().isoformat()[:19],
            }
            self._data_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )
