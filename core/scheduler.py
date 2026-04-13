"""
K. 日課・リマインダーシステム
時刻ベースの定期イベントを管理します。
"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Optional


DEFAULT_SCHEDULES = [
    {
        "id": "morning",
        "name": "朝の声かけ",
        "hour_start": 7,
        "hour_end": 9,
        "enabled": True,
        "prompt": "朝だよ。ユーザーに自然に朝の一言を話しかけて。一文だけ。",
    },
    {
        "id": "afternoon",
        "name": "午後の声かけ",
        "hour_start": 13,
        "hour_end": 15,
        "enabled": True,
        "prompt": "午後だよ。ユーザーに自然に一言声をかけて。一文だけ。",
    },
    {
        "id": "evening",
        "name": "夕方の声かけ",
        "hour_start": 18,
        "hour_end": 20,
        "enabled": True,
        "prompt": "夕方だよ。今日どうだったか一言話しかけて。一文だけ。",
    },
    {
        "id": "night",
        "name": "おやすみ",
        "hour_start": 22,
        "hour_end": 24,
        "enabled": True,
        "prompt": "夜遅いね。自然におやすみの一言を言って。一文だけ。",
    },
]


class ScheduleManager:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.schedules_file = self.data_dir / "schedules.json"
        self.fired_file     = self.data_dir / "schedule_fired.json"
        self.schedules      = self._load_schedules()
        self._fired_today: set[str] = self._load_fired()
        self._lock = threading.Lock()

    def _load_schedules(self) -> list[dict]:
        if self.schedules_file.exists():
            try:
                return json.loads(self.schedules_file.read_text("utf-8"))
            except Exception:
                pass
        # 初回：デフォルトを書き込み
        self.schedules_file.write_text(
            json.dumps(DEFAULT_SCHEDULES, ensure_ascii=False, indent=2), "utf-8"
        )
        return [dict(s) for s in DEFAULT_SCHEDULES]

    def _load_fired(self) -> set[str]:
        if self.fired_file.exists():
            try:
                data = json.loads(self.fired_file.read_text("utf-8"))
                if data.get("date") == date.today().isoformat():
                    return set(data.get("ids", []))
            except Exception:
                pass
        return set()

    def _save_fired(self):
        self.fired_file.write_text(
            json.dumps({"date": date.today().isoformat(),
                        "ids": list(self._fired_today)},
                       ensure_ascii=False),
            "utf-8",
        )

    def check(self) -> Optional[dict]:
        """現在時刻に該当する未発火のスケジュールを返す（1日1回のみ）"""
        with self._lock:
            today = date.today().isoformat()
            # 日付が変わったらリセット
            if self.fired_file.exists():
                try:
                    data = json.loads(self.fired_file.read_text("utf-8"))
                    if data.get("date") != today:
                        self._fired_today = set()
                except Exception:
                    pass

            hour = datetime.now().hour
            for sched in self.schedules:
                if not sched.get("enabled", True):
                    continue
                sid = sched["id"]
                if sid in self._fired_today:
                    continue
                h_start = sched["hour_start"]
                h_end   = sched["hour_end"]
                if h_start <= hour < h_end:
                    self._fired_today.add(sid)
                    self._save_fired()
                    return sched
            return None
