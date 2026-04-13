"""
習慣トラッカー (Habit Tracker)
Sprint 3.0-C: 日々の習慣を記録し、週次でフィードバックする。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal


@dataclass
class HabitRecord:
    """1つの習慣記録"""
    habit_name: str
    date: str          # YYYY-MM-DD
    done: bool = True
    note: str = ""


@dataclass
class Habit:
    """習慣の定義"""
    name: str
    emoji: str = "✅"
    target_days: int = 7       # 週あたりの目標日数
    created_at: str = ""
    records: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class HabitTracker:
    """
    日々の習慣を記録・追跡する。

    使い方:
      tracker.add_habit("運動", emoji="🏃")
      tracker.record("運動")
      tracker.get_weekly_report()
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._path = self._base / "data" / "habits.json"
        self._habits: dict[str, Habit] = self._load()

    # ─── public ──────────────────────────────────────────────

    def add_habit(self, name: str, emoji: str = "✅", target_days: int = 7) -> Habit:
        """習慣を追加する"""
        habit = Habit(
            name=name,
            emoji=emoji,
            target_days=target_days,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._habits[name] = habit
        self._save()
        return habit

    def record(self, habit_name: str, done: bool = True, note: str = "") -> bool:
        """今日の習慣を記録する"""
        if habit_name not in self._habits:
            return False
        today = date.today().isoformat()
        # 既に記録があれば上書き
        records = self._habits[habit_name].records
        for r in records:
            if r.get("date") == today:
                r["done"] = done
                r["note"] = note
                self._save()
                return True
        records.append({"date": today, "done": done, "note": note})
        # 直近90日分のみ保持
        if len(records) > 90:
            records[:] = records[-90:]
        self._save()
        return True

    def remove_habit(self, name: str) -> bool:
        """習慣を削除する"""
        if name in self._habits:
            del self._habits[name]
            self._save()
            return True
        return False

    def list_habits(self) -> list[str]:
        """登録済み習慣名一覧"""
        return list(self._habits.keys())

    def get_today_status(self) -> str:
        """今日の記録状況を返す"""
        today = date.today().isoformat()
        lines: list[str] = ["📝 今日の習慣："]
        for name, habit in self._habits.items():
            done_today = any(
                r.get("date") == today and r.get("done")
                for r in habit.records
            )
            mark = "✅" if done_today else "⬜"
            lines.append(f"  {habit.emoji} {mark} {name}")
        if not self._habits:
            return "まだ習慣が登録されていないよ。「習慣を追加: 運動」で追加できるよ！"
        return "\n".join(lines)

    def get_streak(self, habit_name: str) -> int:
        """連続記録日数を返す"""
        if habit_name not in self._habits:
            return 0
        records = self._habits[habit_name].records
        done_dates = sorted(
            [r["date"] for r in records if r.get("done")],
            reverse=True,
        )
        if not done_dates:
            return 0
        streak = 0
        check_date = date.today()
        for d_str in done_dates:
            d = date.fromisoformat(d_str)
            if d == check_date:
                streak += 1
                check_date -= timedelta(days=1)
            elif d < check_date:
                break
        return streak

    def get_weekly_report(self) -> str:
        """週次レポートを生成する"""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_dates = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]

        lines: list[str] = ["📊 今週の習慣レポート："]
        for name, habit in self._habits.items():
            done_count = sum(
                1 for r in habit.records
                if r.get("date") in week_dates and r.get("done")
            )
            target = habit.target_days
            pct = round(done_count / max(target, 1) * 100)
            bar = "█" * done_count + "░" * (7 - done_count)
            streak = self.get_streak(name)

            lines.append(f"\n  {habit.emoji} {name}")
            lines.append(f"    {bar} {done_count}/{target}日 ({pct}%)")
            if streak > 0:
                lines.append(f"    🔥 {streak}日連続！")

        if not self._habits:
            return "まだ習慣が登録されていないよ。"

        # 総合評価
        total_habits = len(self._habits)
        good_count = sum(
            1 for h in self._habits.values()
            if sum(1 for r in h.records
                   if r.get("date") in week_dates and r.get("done")) >= h.target_days * 0.7
        )
        if good_count == total_habits:
            lines.append("\n🎉 すべての習慣が目標達成！すごいね！")
        elif good_count > 0:
            lines.append(f"\n💪 {good_count}/{total_habits}個の習慣が目標に近いよ！")
        else:
            lines.append("\n😊 来週こそ一緒に頑張ろうね！")

        return "\n".join(lines)

    # ─── private ─────────────────────────────────────────────

    def _load(self) -> dict[str, Habit]:
        if not self._path.exists():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result: dict[str, Habit] = {}
            for name, h in data.items():
                result[name] = Habit(
                    name=h.get("name", name),
                    emoji=h.get("emoji", "✅"),
                    target_days=h.get("target_days", 7),
                    created_at=h.get("created_at", ""),
                    records=h.get("records", []),
                )
            return result
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {n: h.to_dict() for n, h in self._habits.items()},
                f, ensure_ascii=False, indent=2,
            )
