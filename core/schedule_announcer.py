"""
スケジュール読み上げエンジン（Sprint 3-B）
起動時・朝にカレンダー予定を読み上げる。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_ANNOUNCE_INTERVAL_HOURS = 6          # 最低この時間を空けて再通知
_STATE_FILE = "data/schedule_announced.json"


class ScheduleAnnouncer:
    """起動時・朝にカレンダー予定を読み上げる。"""

    def __init__(self, base_dir: Path, llm_fn: Callable[[str], str]) -> None:
        self._base_dir = Path(base_dir)
        self._llm_fn = llm_fn
        self._state_path = self._base_dir / _STATE_FILE
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def get_today_summary(self) -> str:
        """
        今日の予定をアイらしい言い方でまとめて返す。
        予定がなければ「今日は予定なさそうだね、ゆっくりできるね」。
        """
        try:
            from core.calendar_reader import build_calendar_hint, get_upcoming_events

            events = get_upcoming_events(days=1)
            if not events:
                return "今日は予定なさそうだよ～！ゆっくりできるね、よかった😊"

            # アイらしい紹介文を LLM で生成
            lines = [f"・{e['title']}（{e['start']}）" for e in events[:5]]
            event_text = "\n".join(lines)
            prompt = (
                "以下の今日の予定を、アイちゃんとして親しみやすく・簡潔にまとめてください（2〜3文）。\n\n"
                f"予定一覧:\n{event_text}"
            )
            try:
                return self._llm_fn(prompt)
            except Exception:
                # LLM 失敗時はシンプルな文字列を返す
                hint = build_calendar_hint(days=1)
                if hint:
                    return f"今日の予定を確認したよ！{hint}"
                return "今日は予定なさそうだよ～！ゆっくりできるね😊"

        except ImportError:
            logger.warning("[ScheduleAnnouncer] calendar_reader が見つからない")
            return "カレンダーが読み込めなかったよ。設定を確認してみてね💦"
        except Exception as e:
            logger.warning("[ScheduleAnnouncer] get_today_summary error: %s", e)
            return "今日の予定を取得できなかったよ。ごめんね💦"

    def should_announce(self) -> bool:
        """
        最後の読み上げから 6 時間以上経過していたら True。
        data/schedule_announced.json で管理。
        """
        try:
            state = self._load_state()
            last_ts = state.get("last_announced_ts")
            if last_ts is None:
                return True
            elapsed_hours = (datetime.now().timestamp() - last_ts) / 3600
            return elapsed_hours >= _ANNOUNCE_INTERVAL_HOURS
        except Exception as e:
            logger.warning("[ScheduleAnnouncer] should_announce error: %s", e)
            return True

    def mark_announced(self) -> None:
        """読み上げ済みとしてタイムスタンプを更新する。"""
        try:
            state = self._load_state()
            state["last_announced_ts"] = datetime.now().timestamp()
            self._save_state(state)
        except Exception as e:
            logger.warning("[ScheduleAnnouncer] mark_announced error: %s", e)

    # ──────────────────────────────────────────────────────────────
    # 内部ヘルパー
    # ──────────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_state(self, state: dict) -> None:
        self._state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
