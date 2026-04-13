"""
話題追跡システム
過去の会話の「未解決トピック」を追跡し、自然なタイミングで話題を振ります。
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import datetime

OPEN_TOPIC_PATTERNS = [
    (r'(明日|今度|今週|来週|そのうち|いつか).{0,20}(する|やる|行く|見る|食べる|買う)', '予定'),
    (r'(がんばる|頑張る|挑戦する|やってみる)', '挑戦'),
    (r'(悩んで|困って|どうしよう|わからない)', '悩み'),
    (r'(楽しみ|楽しみにして)', '楽しみ'),
]


class TopicTracker:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.topics_file = self.data_dir / "open_topics.json"
        self.topics: list[dict] = self._load()

    def _load(self) -> list:
        if self.topics_file.exists():
            try:
                return json.loads(self.topics_file.read_text("utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        self.topics_file.write_text(
            json.dumps(self.topics, ensure_ascii=False, indent=2), "utf-8"
        )

    def extract_topics(self, user_input: str, turn: int):
        for pattern, topic_type in OPEN_TOPIC_PATTERNS:
            if re.search(pattern, user_input):
                topic = {
                    "text": user_input[:60],
                    "type": topic_type,
                    "turn": turn,
                    "created_at": datetime.now().isoformat(),
                    "followed_up": False,
                }
                if not any(t["text"] == topic["text"] for t in self.topics):
                    self.topics.append(topic)
                    self._save()

    def get_followup_topic(self, current_turn: int, min_gap: int = 5) -> dict | None:
        candidates = [
            t for t in self.topics
            if not t["followed_up"] and (current_turn - t["turn"]) >= min_gap
        ]
        return candidates[0] if candidates else None

    def mark_followed_up(self, topic: dict):
        for t in self.topics:
            if t["text"] == topic["text"]:
                t["followed_up"] = True
        self._save()

    def build_followup_hint(self, topic: dict) -> str:
        type_hints = {
            "予定": f"前に「{topic['text'][:20]}」って言ってたけど、どうなった？",
            "挑戦": "前に頑張るって言ってたこと、うまくいった？",
            "悩み": "前に悩んでたこと、解決した？",
            "楽しみ": "前に楽しみにしてたこと、どうだった？",
        }
        return type_hints.get(topic["type"], "前に話してたこと、どうなったか気になってて")
