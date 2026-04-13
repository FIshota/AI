"""
タスクマネージャー (Task Manager)
Sprint 3.0-C: 自然言語でタスク・リマインダーを管理する。

「明日までにレポート」→ タスク登録 + リマインダー自動設定
「タスク一覧」→ 進捗表示
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Literal


TaskStatus = Literal["pending", "in_progress", "done", "cancelled"]
TaskPriority = Literal["low", "medium", "high", "urgent"]


@dataclass
class Task:
    """1つのタスク"""
    id: int
    title: str
    status: TaskStatus = "pending"
    priority: TaskPriority = "medium"
    due_date: str = ""          # ISO形式 YYYY-MM-DD
    reminder_time: str = ""     # HH:MM
    created_at: str = ""
    completed_at: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Task":
        return Task(**{k: v for k, v in d.items() if k in Task.__dataclass_fields__})


# 自然言語からタスクを抽出するパターン
_DUE_PATTERNS = [
    (re.compile(r'今日(まで)?に'), lambda: date.today()),
    (re.compile(r'明日(まで)?に'), lambda: date.today() + timedelta(days=1)),
    (re.compile(r'明後日(まで)?に'), lambda: date.today() + timedelta(days=2)),
    (re.compile(r'来週(まで)?に'), lambda: date.today() + timedelta(days=7)),
    (re.compile(r'(\d{1,2})月(\d{1,2})日(まで)?に?'),
     lambda m: date(date.today().year, int(m.group(1)), int(m.group(2)))),
    (re.compile(r'(\d+)日(後|以内)(まで)?に?'),
     lambda m: date.today() + timedelta(days=int(m.group(1)))),
]

_PRIORITY_KEYWORDS = {
    "urgent": ["至急", "急ぎ", "すぐ", "緊急", "ASAP"],
    "high": ["重要", "大事", "優先", "必ず"],
    "low": ["いつか", "暇なとき", "余裕があれば", "できれば"],
}


class TaskManager:
    """
    自然言語でタスクを管理する。

    使い方:
      tm.add_from_text("明日までにレポートを書く")
      tm.list_pending()
      tm.complete(task_id)
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._path = self._base / "data" / "tasks.json"
        self._lock = threading.Lock()
        self._tasks: list[Task] = self._load()
        self._next_id = max((t.id for t in self._tasks), default=0) + 1

    # ─── public ──────────────────────────────────────────────

    def add_from_text(self, text: str) -> Task:
        """自然言語からタスクを作成して追加する"""
        title = self._extract_title(text)
        due = self._extract_due_date(text)
        priority = self._extract_priority(text)

        task = Task(
            id=self._next_id,
            title=title,
            priority=priority,
            due_date=due.isoformat() if due else "",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        # 期限が明日以降なら当日朝9時にリマインダー
        if due and due > date.today():
            task.reminder_time = "09:00"

        with self._lock:
            self._tasks.append(task)
            self._next_id += 1
            self._save()
        return task

    def add(self, title: str, due_date: str = "", priority: TaskPriority = "medium") -> Task:
        """明示的にタスクを追加する"""
        task = Task(
            id=self._next_id,
            title=title,
            due_date=due_date,
            priority=priority,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._tasks.append(task)
            self._next_id += 1
            self._save()
        return task

    def complete(self, task_id: int) -> bool:
        """タスクを完了にする"""
        with self._lock:
            for t in self._tasks:
                if t.id == task_id:
                    t.status = "done"
                    t.completed_at = datetime.now(timezone.utc).isoformat()
                    self._save()
                    return True
        return False

    def cancel(self, task_id: int) -> bool:
        """タスクをキャンセルする"""
        with self._lock:
            for t in self._tasks:
                if t.id == task_id:
                    t.status = "cancelled"
                    self._save()
                    return True
        return False

    def list_pending(self) -> list[Task]:
        """未完了タスクを期限順で返す"""
        pending = [t for t in self._tasks if t.status in ("pending", "in_progress")]
        return sorted(pending, key=lambda t: (t.due_date or "9999-12-31", t.id))

    def list_all(self, limit: int = 20) -> list[Task]:
        """全タスクを返す"""
        return self._tasks[-limit:]

    def get_due_today(self) -> list[Task]:
        """今日が期限のタスク"""
        today = date.today().isoformat()
        return [t for t in self._tasks
                if t.status in ("pending", "in_progress") and t.due_date == today]

    def get_overdue(self) -> list[Task]:
        """期限切れタスク"""
        today = date.today().isoformat()
        return [t for t in self._tasks
                if t.status in ("pending", "in_progress")
                and t.due_date and t.due_date < today]

    def get_reminders_now(self) -> list[Task]:
        """現在リマインダーを出すべきタスク"""
        now_time = datetime.now().strftime("%H:%M")
        today = date.today().isoformat()
        results: list[Task] = []
        for t in self._tasks:
            if t.status not in ("pending", "in_progress"):
                continue
            if t.reminder_time and t.due_date:
                # 期限当日の指定時刻
                if t.due_date == today and t.reminder_time == now_time:
                    results.append(t)
        return results

    def format_task_list(self, tasks: list[Task] | None = None) -> str:
        """タスクリストを日本語で整形する"""
        if tasks is None:
            tasks = self.list_pending()
        if not tasks:
            return "タスクはないよ！今日もゆっくりしてね😊"

        priority_emoji = {
            "urgent": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }

        lines: list[str] = ["📋 タスク一覧："]
        for t in tasks:
            emoji = priority_emoji.get(t.priority, "🟡")
            due = f" (期限: {t.due_date})" if t.due_date else ""
            status = "✅" if t.status == "done" else f"#{t.id}"
            lines.append(f"  {emoji} {status} {t.title}{due}")

        overdue = self.get_overdue()
        if overdue:
            lines.append(f"\n⚠️ 期限切れ: {len(overdue)}件あるよ！")

        return "\n".join(lines)

    # ─── ジョブ登録用 ────────────────────────────────────────

    def hourly_check(self) -> dict:
        """毎時チェック: リマインダーと期限切れを返す"""
        reminders = self.get_reminders_now()
        overdue = self.get_overdue()
        return {
            "action": "task_check",
            "reminders": len(reminders),
            "overdue": len(overdue),
        }

    # ─── private ─────────────────────────────────────────────

    def _extract_title(self, text: str) -> str:
        """テキストからタスクのタイトルを抽出する"""
        # 日付表現を除去
        title = text
        for pattern, _ in _DUE_PATTERNS:
            title = pattern.sub("", title)
        # 優先度キーワードを除去
        for keywords in _PRIORITY_KEYWORDS.values():
            for kw in keywords:
                title = title.replace(kw, "")
        # 前後の助詞・記号を整理
        title = re.sub(r'^[をにでのはが、。！？\s]+', '', title)
        title = re.sub(r'[をにでのはが、。！？\s]+$', '', title)
        return title.strip() or text.strip()[:50]

    def _extract_due_date(self, text: str) -> date | None:
        """テキストから期限を抽出する"""
        for pattern, resolver in _DUE_PATTERNS:
            m = pattern.search(text)
            if m:
                try:
                    if callable(resolver) and hasattr(resolver, "__code__"):
                        # lambda にマッチオブジェクトを渡すかどうか
                        params = resolver.__code__.co_varnames
                        if params and params[0] != "self":
                            return resolver(m) if len(params) > 0 and "m" in str(resolver.__code__.co_consts) else resolver()
                        return resolver()
                    return resolver()
                except (ValueError, TypeError):
                    continue
        return None

    def _extract_priority(self, text: str) -> TaskPriority:
        """テキストから優先度を推定する"""
        for priority, keywords in _PRIORITY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return priority  # type: ignore
        return "medium"

    def _load(self) -> list[Task]:
        if not self._path.exists():
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [Task.from_dict(d) for d in data]
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                [t.to_dict() for t in self._tasks],
                f, ensure_ascii=False, indent=2,
            )
