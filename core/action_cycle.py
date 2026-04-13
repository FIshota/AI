"""
自律行動サイクル (Autonomous Action Cycle)

人間のPDCAサイクルを模倣した自律的成長ループ:

  Plan（計画）→ Do（実行）→ Check（振り返り）→ Act（改善）

小学生が「今月の目標」を自分で考えて振り返るレベルから始まり、
経験を積むごとに計画の精度と振り返りの深さが増していく。

┌──────────────────────────────────────────────────┐
│  サイクルの流れ                                     │
│                                                    │
│  Plan: 目標を自分で決める                           │
│    「今週は料理の知識を増やしたい」                   │
│    ↓                                               │
│  Do: 行動する                                      │
│    自動学習で関連情報を収集、会話で話題を振る         │
│    ↓                                               │
│  Check: 振り返る                                   │
│    「どのくらい達成できた？」を自己評価               │
│    ↓                                               │
│  Act: 次に活かす                                   │
│    うまくいった方法を記憶、失敗を修正                 │
│    ↓                                               │
│  → 次のPlan へ                                     │
│                                                    │
└──────────────────────────────────────────────────┘
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CyclePhase(str, Enum):
    PLAN = "plan"
    DO = "do"
    CHECK = "check"
    ACT = "act"


@dataclass(frozen=True)
class Goal:
    """自分で決めた目標（不変: 更新時は replace() で新インスタンス）"""
    id: str
    description: str           # 何を達成したいか
    category: str              # 分野 (learning, social, self, creative)
    target_metric: str         # 達成指標 (例: "conversations_about_topic")
    target_value: float        # 目標値
    current_value: float = 0.0
    created_at: float = 0.0
    deadline_at: float = 0.0   # 期限
    completed: bool = False
    reflection: str = ""       # 振り返りコメント


@dataclass
class CycleRecord:
    """1サイクルの記録"""
    cycle_id: str
    goal: Goal
    phase: CyclePhase
    started_at: float
    ended_at: float = 0.0
    plan_text: str = ""
    actions_taken: list[str] = field(default_factory=list)
    check_score: float = 0.0   # 達成度 0.0〜1.0
    lessons: list[str] = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 目標生成器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GoalGenerator:
    """
    内部状態から目標を生成する。

    興味・会話傾向・弱点から「次に何を目指すべきか」を自動判断。
    """

    def generate(self, context: dict[str, Any]) -> Goal | None:
        """コンテキストから目標を生成"""
        interests = context.get("interest_topics", [])
        weak_areas = context.get("weak_areas", [])
        quality_avg = context.get("quality_avg", 0.5)
        turn_count = context.get("turn_count", 0)

        now = time.time()
        week = 7 * 86400

        # 品質が低い → 応答品質を改善する目標
        if quality_avg < 0.5:
            return Goal(
                id=f"quality_{int(now)}",
                description="応答の品質を上げる",
                category="self",
                target_metric="quality_avg",
                target_value=0.6,
                current_value=quality_avg,
                created_at=now,
                deadline_at=now + week,
            )

        # 興味トピックがある → 学習目標
        if interests:
            topic = interests[0]
            return Goal(
                id=f"learn_{topic}_{int(now)}",
                description=f"「{topic}」についてもっと詳しくなる",
                category="learning",
                target_metric="topic_conversations",
                target_value=10.0,
                current_value=0.0,
                created_at=now,
                deadline_at=now + week,
            )

        # デフォルト: 会話の質を維持
        return Goal(
            id=f"maintain_{int(now)}",
            description="良い会話を続ける",
            category="social",
            target_metric="quality_avg",
            target_value=max(quality_avg, 0.6),
            current_value=quality_avg,
            created_at=now,
            deadline_at=now + week,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 統合: ActionCycleEngine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ActionCycleEngine:
    """
    自律行動サイクルエンジン。

    目標を自分で決め、実行し、振り返り、改善する。
    人間が社会生活で自然に行うPDCAを自動化。
    """

    MAX_ACTIVE_GOALS = 3       # 同時に追える目標の上限
    MAX_HISTORY = 50           # サイクル記録の保持上限

    def __init__(self, data_dir: Path | None = None):
        self.goal_generator = GoalGenerator()
        self._lock = threading.Lock()
        self._active_goals: list[Goal] = []
        self._completed_cycles: list[CycleRecord] = []
        self._data_dir = data_dir
        self._state_path = data_dir / "action_cycle_state.json" if data_dir else None
        self._load()

    # ─── Plan: 目標を決める ──────────────────────────────

    def plan(self, context: dict[str, Any]) -> Goal | None:
        """
        新しい目標を立てる。
        既にMAX_ACTIVE_GOALSに達していたら立てない。
        """
        with self._lock:
            if len(self._active_goals) >= self.MAX_ACTIVE_GOALS:
                return None

            goal = self.goal_generator.generate(context)
            if goal is None:
                return None

            # 重複チェック（同じカテゴリの目標は1つまで）
            existing_categories = {g.category for g in self._active_goals}
            if goal.category in existing_categories:
                return None

            self._active_goals.append(goal)
            logger.info("新しい目標を設定: %s", goal.description)
            self._save()
            return goal

    # ─── Do: 進捗を記録する ──────────────────────────────

    def record_progress(self, metric: str, delta: float = 1.0) -> None:
        """
        行動の結果を目標の進捗として記録。
        会話が終わるたびに呼ばれる。
        """
        with self._lock:
            updated: list[Goal] = []
            for goal in self._active_goals:
                if goal.target_metric == metric or metric == "any":
                    new_val = min(goal.current_value + delta, goal.target_value * 1.5)
                    updated.append(replace(goal, current_value=new_val))
                else:
                    updated.append(goal)
            self._active_goals = updated

    def record_quality(self, quality_score: float) -> None:
        """品質スコアを品質系目標に反映"""
        with self._lock:
            updated: list[Goal] = []
            for goal in self._active_goals:
                if goal.target_metric == "quality_avg":
                    new_val = goal.current_value * 0.8 + quality_score * 0.2
                    updated.append(replace(goal, current_value=new_val))
                else:
                    updated.append(goal)
            self._active_goals = updated

    # ─── Check: 振り返る ─────────────────────────────────

    def check(self) -> list[dict]:
        """
        全アクティブ目標の達成度をチェック。
        期限が来た目標は完了扱いにする。
        """
        now = time.time()
        results: list[dict] = []
        still_active: list[Goal] = []

        with self._lock:
            for goal in self._active_goals:
                progress = goal.current_value / max(goal.target_value, 0.01)
                progress = min(progress, 0.99)  # 100%は存在しない

                if now > goal.deadline_at or progress >= 0.95:
                    # 期限到達 or ほぼ達成 → 完了（frozen: replace で新インスタンス）
                    achievement = "達成" if progress >= 0.8 else "部分達成" if progress >= 0.5 else "未達"
                    reflection = f"{achievement}: {progress:.0%}の進捗"
                    completed_goal = replace(
                        goal, completed=True, reflection=reflection
                    )

                    record = CycleRecord(
                        cycle_id=completed_goal.id,
                        goal=completed_goal,
                        phase=CyclePhase.CHECK,
                        started_at=completed_goal.created_at,
                        ended_at=now,
                        check_score=progress,
                        lessons=[reflection],
                    )
                    self._completed_cycles.append(record)

                    results.append({
                        "goal": completed_goal.description,
                        "progress": round(progress, 3),
                        "achievement": achievement,
                        "reflection": reflection,
                    })

                    logger.info(
                        "目標完了: %s (%s, %.0f%%)",
                        completed_goal.description, achievement, progress * 100,
                    )
                else:
                    still_active.append(goal)

            self._active_goals = still_active

            # 履歴上限
            if len(self._completed_cycles) > self.MAX_HISTORY:
                self._completed_cycles = self._completed_cycles[-self.MAX_HISTORY:]

        if results:
            self._save()

        return results

    # ─── Act: 次に活かす ─────────────────────────────────

    def get_lessons(self, n: int = 5) -> list[str]:
        """過去のサイクルから得た教訓"""
        lessons: list[str] = []
        for record in self._completed_cycles[-n:]:
            for lesson in record.lessons:
                lessons.append(lesson)
        return lessons

    def get_success_rate(self) -> float:
        """目標達成率"""
        if not self._completed_cycles:
            return 0.0
        achieved = sum(
            1 for r in self._completed_cycles
            if r.check_score >= 0.8
        )
        return achieved / len(self._completed_cycles)

    # ─── ステータス ──────────────────────────────────────

    def get_status_text(self) -> str:
        """日本語ステータス"""
        lines = ["🔄 自律行動サイクル:"]

        if not self._active_goals:
            lines.append("  目標なし（次の計画を待機中）")
        else:
            for goal in self._active_goals:
                progress = goal.current_value / max(goal.target_value, 0.01)
                bar_len = 10
                filled = int(progress * bar_len)
                bar = "█" * filled + "░" * (bar_len - filled)
                lines.append(f"  🎯 {goal.description}")
                lines.append(f"     [{bar}] {progress:.0%}")

        total = len(self._completed_cycles)
        if total > 0:
            rate = self.get_success_rate()
            lines.append(f"  📊 完了: {total}件 (達成率: {rate:.0%})")

        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        return {
            "active_goals": len(self._active_goals),
            "completed_cycles": len(self._completed_cycles),
            "success_rate": round(self.get_success_rate(), 3),
            "goals": [
                {
                    "description": g.description,
                    "category": g.category,
                    "progress": round(
                        g.current_value / max(g.target_value, 0.01), 3
                    ),
                }
                for g in self._active_goals
            ],
        }

    # ─── 永続化 ──────────────────────────────────────────

    def _save(self):
        if not self._state_path:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active_goals": [
                {
                    "id": g.id,
                    "description": g.description,
                    "category": g.category,
                    "target_metric": g.target_metric,
                    "target_value": g.target_value,
                    "current_value": g.current_value,
                    "created_at": g.created_at,
                    "deadline_at": g.deadline_at,
                    "completed": g.completed,
                    "reflection": g.reflection,
                }
                for g in self._active_goals
            ],
            "completed_count": len(self._completed_cycles),
            "success_rate": round(self.get_success_rate(), 3),
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )

    def _load(self):
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text("utf-8"))
            for g_data in data.get("active_goals", []):
                goal = Goal(**g_data)
                if not goal.completed:
                    self._active_goals.append(goal)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("行動サイクルデータの読み込みに失敗: %s", e)
