"""
記念日・誕生日管理システム
登録した日付に自動で特別な声かけをします。
"""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from datetime import date
from typing import Optional


DEFAULT_ANNIVERSARIES: list[dict] = []


class AnniversaryManager:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / "anniversaries.json"
        self.items: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if self.file.exists():
            try:
                return json.loads(self.file.read_text("utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        self.file.write_text(
            json.dumps(self.items, ensure_ascii=False, indent=2), "utf-8"
        )

    def add(self, label: str, month: int, day: int,
            is_birthday: bool = False) -> dict:
        """記念日を追加します"""
        # 既に同じ名前があれば更新
        for item in self.items:
            if item["label"] == label:
                item.update({"month": month, "day": day,
                              "is_birthday": is_birthday})
                self._save()
                return item
        entry = {
            "id": str(uuid.uuid4())[:8],
            "label": label,
            "month": month,
            "day": day,
            "is_birthday": is_birthday,
            "yearly": True,
        }
        self.items.append(entry)
        self._save()
        return entry

    def remove(self, label_or_id: str) -> bool:
        before = len(self.items)
        self.items = [
            x for x in self.items
            if x["id"] != label_or_id and x["label"] != label_or_id
        ]
        if len(self.items) < before:
            self._save()
            return True
        return False

    def check_today(self) -> list[dict]:
        """今日が記念日のものを全て返す"""
        today = date.today()
        result = []
        for item in self.items:
            m, d = item["month"], item["day"]
            # 2/29 はうるう年以外は 3/1 扱い
            try:
                if date(today.year, m, d) == today:
                    result.append(item)
            except ValueError:
                if today.month == 3 and today.day == 1 and m == 2 and d == 29:
                    result.append(item)
        return result

    def list_all(self) -> list[dict]:
        return list(self.items)

    def build_prompt(self, items: list[dict]) -> str:
        """記念日用の LLM プロンプトを生成"""
        if not items:
            return ""
        descs = []
        for item in items:
            if item.get("is_birthday"):
                descs.append(f"今日は{item['label']}だよ。お誕生日をお祝いする一言を言って。")
            else:
                descs.append(f"今日は{item['label']}だよ。記念日を祝う自然な一言を言って。")
        return " ".join(descs)
