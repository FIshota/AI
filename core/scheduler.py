"""
K. 日課・リマインダーシステム
時刻ベースの定期イベントを管理します。
"""
from __future__ import annotations
import json
import logging
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# メンテナンスタスクレジストリ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class _MaintenanceTask:
    """定期メンテナンスタスクの定義。"""

    def __init__(
        self,
        name: str,
        interval_hours: float,
        callback: Callable[[], Any],
        last_run: Optional[str] = None,
    ) -> None:
        self.name: str = name
        self.interval_hours: float = interval_hours
        self.callback: Callable[[], Any] = callback
        self.last_run: Optional[str] = last_run


class MaintenanceScheduler:
    """定期メンテナンスタスクを管理するスケジューラ。

    register_maintenance_tasks() で標準タスクを一括登録し、
    run_due_tasks() で実行タイミングに達したタスクを実行する。
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir: Path = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: Dict[str, _MaintenanceTask] = {}
        self._state_path: Path = self._data_dir / "maintenance_state.json"
        self._lock: threading.Lock = threading.Lock()
        self._load_state()

    def _load_state(self) -> None:
        """前回実行時刻をファイルから復元する。"""
        if not self._state_path.exists():
            return
        try:
            data: Dict[str, Any] = json.loads(
                self._state_path.read_text("utf-8")
            )
            for name, last_run in data.items():
                if name in self._tasks:
                    self._tasks[name].last_run = last_run
        except (json.JSONDecodeError, KeyError):
            pass

    def _save_state(self) -> None:
        """各タスクの最終実行時刻を保存する。"""
        state: Dict[str, Optional[str]] = {
            name: task.last_run for name, task in self._tasks.items()
        }
        self._state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), "utf-8"
        )

    def register(
        self,
        name: str,
        interval_hours: float,
        callback: Callable[[], Any],
    ) -> None:
        """メンテナンスタスクを登録する。

        Args:
            name: タスク識別名。
            interval_hours: 実行間隔（時間）。
            callback: 引数なしのコールバック関数。
        """
        with self._lock:
            task: _MaintenanceTask = _MaintenanceTask(
                name=name,
                interval_hours=interval_hours,
                callback=callback,
            )
            self._tasks[name] = task
            # 既存の last_run を復元
            self._load_state()
            logger.info("メンテナンスタスク登録: %s (%.1f時間間隔)", name, interval_hours)

    def run_due_tasks(self) -> List[Dict[str, Any]]:
        """実行タイミングに達したタスクをすべて実行する。

        Returns:
            [{"name": str, "status": "ok" | "error", "detail": str}, ...]
        """
        now: datetime = datetime.utcnow()
        results: List[Dict[str, Any]] = []

        with self._lock:
            for name, task in self._tasks.items():
                is_due: bool = False
                if task.last_run is None:
                    is_due = True
                else:
                    try:
                        last: datetime = datetime.fromisoformat(task.last_run)
                        elapsed_hours: float = (now - last).total_seconds() / 3600
                        if elapsed_hours >= task.interval_hours:
                            is_due = True
                    except (ValueError, TypeError):
                        is_due = True

                if not is_due:
                    continue

                try:
                    task.callback()
                    task.last_run = now.isoformat()
                    results.append({
                        "name": name,
                        "status": "ok",
                        "detail": f"実行完了 ({now.isoformat()})",
                    })
                    logger.info("メンテナンスタスク実行: %s", name)
                except Exception as exc:
                    results.append({
                        "name": name,
                        "status": "error",
                        "detail": str(exc),
                    })
                    logger.warning("メンテナンスタスクエラー: %s - %s", name, exc)

            self._save_state()

        return results

    @property
    def task_names(self) -> List[str]:
        """登録済みタスク名の一覧を返す。"""
        return list(self._tasks.keys())


def register_maintenance_tasks(
    scheduler: MaintenanceScheduler,
    quality_benchmark_fn: Optional[Callable[[], Any]] = None,
    sqlite_vacuum_fn: Optional[Callable[[], Any]] = None,
    integrity_check_fn: Optional[Callable[[], Any]] = None,
) -> None:
    """標準メンテナンスタスクを一括登録する。

    Args:
        scheduler: MaintenanceScheduler インスタンス。
        quality_benchmark_fn: #51 日次品質チェック用コールバック。
        sqlite_vacuum_fn: #62 週次 SQLite VACUUM 用コールバック。
        integrity_check_fn: #98 6時間ごとの整合性チェック用コールバック。
    """
    # #51: 日次品質チェック (24時間ごと)
    if quality_benchmark_fn is not None:
        scheduler.register(
            name="daily_quality_check",
            interval_hours=24.0,
            callback=quality_benchmark_fn,
        )

    # #62: 週次 SQLite VACUUM (168時間 = 7日ごと)
    if sqlite_vacuum_fn is not None:
        scheduler.register(
            name="weekly_sqlite_vacuum",
            interval_hours=168.0,
            callback=sqlite_vacuum_fn,
        )

    # #98: 6時間ごとの整合性チェック
    if integrity_check_fn is not None:
        scheduler.register(
            name="integrity_check_6h",
            interval_hours=6.0,
            callback=integrity_check_fn,
        )
