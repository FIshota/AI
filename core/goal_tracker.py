"""
ユーザー目標トラッキング
会話からゴール・意欲的な発言を検出して記録し、進捗を管理します
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import datetime


# 目標を示す表現パターン
GOAL_PATTERNS = [
    re.compile(r'(.{3,25}?)(?:したい|しようと思|を目指|が目標|をやりたい|をやろう)'),
    re.compile(r'目標は(.{3,25}?)(?:だ|だよ|です|。|$)'),
    re.compile(r'(.{3,25}?)(?:を始めようと|に挑戦|を頑張る|を続ける)'),
    re.compile(r'(.{3,25}?)(?:できるようになりたい|上手くなりたい|克服したい)'),
]

# 進捗を示す表現
PROGRESS_POSITIVE = ['できた', '達成', 'クリア', '成功', '終わった', 'やり遂げ', 'やった']
PROGRESS_NEGATIVE = ['できなかった', '失敗', 'やめた', 'あきらめ', '挫折']


class GoalTracker:
    def __init__(self, data_dir: Path):
        self._path = Path(data_dir) / "goals.json"
        self._goals: list[dict] = []
        self._next_id = 1
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text("utf-8"))
                self._goals = data
                if self._goals:
                    self._next_id = max(g["id"] for g in self._goals) + 1
            except Exception:
                self._goals = []

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._goals, ensure_ascii=False, indent=2), "utf-8"
        )

    def detect_and_add(self, text: str) -> str | None:
        """会話テキストからゴールを検出して追加。新規追加した場合はゴールテキストを返す"""
        for pattern in GOAL_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            goal_text = m.group(1).strip()
            # 短すぎ・記号のみ・数字のみはスキップ
            if len(goal_text) < 3:
                continue
            if not re.search(r'[\u3040-\u9FFF]', goal_text):
                continue
            # 重複チェック（既存のゴールと80%以上被っていたらスキップ）
            for g in self._goals:
                if g["status"] == "active" and (
                    goal_text in g["text"] or g["text"] in goal_text
                ):
                    return None
            self._add_goal(goal_text)
            return goal_text
        return None

    def _add_goal(self, text: str):
        goal = {
            "id": self._next_id,
            "text": text,
            "status": "active",
            "progress_notes": [],
            "created_at": datetime.now().isoformat()[:16],
            "updated_at": datetime.now().isoformat()[:16],
        }
        self._goals.append(goal)
        self._next_id += 1
        self._save()

    def add_manual(self, text: str):
        """手動でゴールを追加"""
        self._add_goal(text)

    def complete_goal(self, goal_id: int):
        for g in self._goals:
            if g["id"] == goal_id:
                g["status"] = "done"
                g["updated_at"] = datetime.now().isoformat()[:16]
        self._save()

    def delete_goal(self, goal_id: int):
        self._goals = [g for g in self._goals if g["id"] != goal_id]
        self._save()

    def add_progress_note(self, goal_id: int, note: str):
        for g in self._goals:
            if g["id"] == goal_id:
                g["progress_notes"].append({
                    "note": note,
                    "ts": datetime.now().isoformat()[:16],
                })
                g["updated_at"] = datetime.now().isoformat()[:16]
        self._save()

    def detect_progress(self, text: str) -> dict | None:
        """進捗発言を検出してアクティブなゴールと照合"""
        active = self.get_active()
        if not active:
            return None
        for goal in active:
            if any(w in text for w in goal["text"].split()):
                if any(w in text for w in PROGRESS_POSITIVE):
                    return {"goal": goal, "direction": "positive"}
                if any(w in text for w in PROGRESS_NEGATIVE):
                    return {"goal": goal, "direction": "negative"}
        return None

    def list_goals(self, status: str | None = None) -> list[dict]:
        if status:
            return [g for g in self._goals if g["status"] == status]
        return list(self._goals)

    def get_active(self) -> list[dict]:
        return self.list_goals("active")

    def get_reminder_text(self) -> str | None:
        """ランダムに目標リマインダー文を返す"""
        import random
        active = self.get_active()
        if not active:
            return None
        goal = random.choice(active[:5])
        return goal["text"]

    def stats(self) -> dict:
        active = len(self.get_active())
        done = len(self.list_goals("done"))
        return {"active": active, "done": done, "total": len(self._goals)}
