"""
Tests for core.action_cycle module.

Covers CyclePhase enum, Goal frozen dataclass, GoalGenerator,
and ActionCycleEngine (PDCA lifecycle, limits, persistence, stats).
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.action_cycle import (
    ActionCycleEngine,
    CyclePhase,
    Goal,
    GoalGenerator,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CyclePhase
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCyclePhase:
    def test_values(self) -> None:
        assert CyclePhase.PLAN.value == "plan"
        assert CyclePhase.DO.value == "do"
        assert CyclePhase.CHECK.value == "check"
        assert CyclePhase.ACT.value == "act"

    def test_is_str_enum(self) -> None:
        assert isinstance(CyclePhase.PLAN, str)
        assert CyclePhase.DO == "do"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Goal (frozen dataclass)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGoal:
    def test_creation(self) -> None:
        goal = Goal(
            id="g1",
            description="test",
            category="learning",
            target_metric="m",
            target_value=10.0,
        )
        assert goal.id == "g1"
        assert goal.current_value == 0.0
        assert goal.completed is False

    def test_immutability(self) -> None:
        goal = Goal(
            id="g1",
            description="test",
            category="learning",
            target_metric="m",
            target_value=10.0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            goal.current_value = 5.0  # type: ignore[misc]

    def test_replace_creates_new_instance(self) -> None:
        original = Goal(
            id="g1",
            description="test",
            category="learning",
            target_metric="m",
            target_value=10.0,
            current_value=3.0,
        )
        updated = dataclasses.replace(original, current_value=7.0)
        assert updated.current_value == 7.0
        assert original.current_value == 3.0
        assert updated is not original


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GoalGenerator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGoalGenerator:
    def setup_method(self) -> None:
        self.gen = GoalGenerator()

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_low_quality_generates_self_goal(self, _mock_time) -> None:
        goal = self.gen.generate({"quality_avg": 0.3})
        assert goal is not None
        assert goal.category == "self"
        assert goal.target_metric == "quality_avg"
        assert goal.current_value == 0.3

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_interest_generates_learning_goal(self, _mock_time) -> None:
        goal = self.gen.generate({"interest_topics": ["cooking"], "quality_avg": 0.7})
        assert goal is not None
        assert goal.category == "learning"
        assert "cooking" in goal.description

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_default_generates_social_goal(self, _mock_time) -> None:
        goal = self.gen.generate({"quality_avg": 0.7})
        assert goal is not None
        assert goal.category == "social"
        assert goal.target_metric == "quality_avg"

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_deadline_is_one_week_out(self, _mock_time) -> None:
        goal = self.gen.generate({"quality_avg": 0.7})
        assert goal is not None
        expected_deadline = 1_000_000.0 + 7 * 86400
        assert goal.deadline_at == expected_deadline


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ActionCycleEngine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestActionCycleEngine:
    def setup_method(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.engine = ActionCycleEngine(data_dir=self.tmp_dir)

    def teardown_method(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ── plan ─────────────────────────────────────────

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_plan_creates_goal(self, _mock_time) -> None:
        goal = self.engine.plan({"quality_avg": 0.3})
        assert goal is not None
        assert len(self.engine._active_goals) == 1

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_plan_rejects_duplicate_category(self, _mock_time) -> None:
        first = self.engine.plan({"quality_avg": 0.3})
        assert first is not None
        second = self.engine.plan({"quality_avg": 0.3})
        assert second is None
        assert len(self.engine._active_goals) == 1

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_plan_max_active_goals(self, _mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        self.engine.plan({"interest_topics": ["art"], "quality_avg": 0.7})
        self.engine.plan({"quality_avg": 0.7})
        assert len(self.engine._active_goals) == 3

        extra = self.engine.plan({"quality_avg": 0.9, "interest_topics": ["math"]})
        assert extra is None
        assert len(self.engine._active_goals) == 3

    # ── record_progress ──────────────────────────────

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_record_progress_increments_matching_metric(self, _mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        self.engine.record_progress("quality_avg", delta=0.1)
        goal = self.engine._active_goals[0]
        assert goal.current_value == pytest.approx(0.4)

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_record_progress_caps_at_1_5x_target(self, _mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        target = self.engine._active_goals[0].target_value
        self.engine.record_progress("quality_avg", delta=target * 10)
        goal = self.engine._active_goals[0]
        assert goal.current_value <= target * 1.5

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_record_progress_any_metric(self, _mock_time) -> None:
        self.engine.plan({"interest_topics": ["music"], "quality_avg": 0.7})
        self.engine.record_progress("any", delta=2.0)
        goal = self.engine._active_goals[0]
        assert goal.current_value == 2.0

    # ── record_quality ───────────────────────────────

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_record_quality_ewma(self, _mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        initial = self.engine._active_goals[0].current_value
        self.engine.record_quality(1.0)
        updated = self.engine._active_goals[0].current_value
        expected = initial * 0.8 + 1.0 * 0.2
        assert updated == pytest.approx(expected)

    # ── check ────────────────────────────────────────

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_check_completes_past_deadline(self, mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        assert len(self.engine._active_goals) == 1

        mock_time.return_value = 1_000_000.0 + 8 * 86400
        results = self.engine.check()

        assert len(results) == 1
        assert len(self.engine._active_goals) == 0
        assert len(self.engine._completed_cycles) == 1

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_check_completes_high_progress(self, _mock_time) -> None:
        self.engine.plan({"interest_topics": ["science"], "quality_avg": 0.7})
        self.engine.record_progress("topic_conversations", delta=9.6)
        results = self.engine.check()

        assert len(results) == 1
        assert results[0]["progress"] >= 0.95

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_check_achievement_labels(self, mock_time) -> None:
        # quality_avg=0.3, target=0.6 → progress=0.5 → 部分達成
        self.engine.plan({"quality_avg": 0.3})
        mock_time.return_value = 1_000_000.0 + 8 * 86400
        results = self.engine.check()
        assert results[0]["achievement"] == "部分達成"

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_check_keeps_non_expired_goals(self, _mock_time) -> None:
        self.engine.plan({"interest_topics": ["art"], "quality_avg": 0.7})
        results = self.engine.check()
        assert len(results) == 0
        assert len(self.engine._active_goals) == 1

    # ── get_lessons ──────────────────────────────────

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_get_lessons_returns_reflections(self, mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        mock_time.return_value = 1_000_000.0 + 8 * 86400
        self.engine.check()

        lessons = self.engine.get_lessons()
        assert len(lessons) >= 1
        assert any("達" in l for l in lessons)

    # ── get_success_rate ─────────────────────────────

    def test_success_rate_empty(self) -> None:
        assert self.engine.get_success_rate() == 0.0

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_success_rate_after_cycles(self, mock_time) -> None:
        # Create a goal with high progress -> score >= 0.8
        self.engine.plan({"interest_topics": ["math"], "quality_avg": 0.7})
        self.engine.record_progress("topic_conversations", delta=9.6)
        self.engine.check()

        assert self.engine.get_success_rate() == pytest.approx(1.0)

        # Create a goal with low progress -> score < 0.8
        self.engine.plan({"quality_avg": 0.3})
        mock_time.return_value = 1_000_000.0 + 8 * 86400
        self.engine.check()

        # 1 success out of 2 total
        assert self.engine.get_success_rate() == pytest.approx(0.5)

    # ── get_status_text ──────────────────────────────

    def test_status_text_empty(self) -> None:
        text = self.engine.get_status_text()
        assert "目標なし" in text

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_status_text_with_goals(self, _mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        text = self.engine.get_status_text()
        assert "🎯" in text

    # ── stats ────────────────────────────────────────

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_stats_structure(self, _mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        s = self.engine.stats()
        assert s["active_goals"] == 1
        assert s["completed_cycles"] == 0
        assert isinstance(s["goals"], list)
        assert len(s["goals"]) == 1
        assert "progress" in s["goals"][0]

    # ── persistence ──────────────────────────────────

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_persistence_save_and_load(self, _mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        state_path = self.tmp_dir / "action_cycle_state.json"
        assert state_path.exists()

        data = json.loads(state_path.read_text("utf-8"))
        assert len(data["active_goals"]) == 1

        engine2 = ActionCycleEngine(data_dir=self.tmp_dir)
        assert len(engine2._active_goals) == 1
        assert engine2._active_goals[0].category == "self"

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_persistence_skips_completed_on_load(self, mock_time) -> None:
        self.engine.plan({"quality_avg": 0.3})
        mock_time.return_value = 1_000_000.0 + 8 * 86400
        self.engine.check()

        engine2 = ActionCycleEngine(data_dir=self.tmp_dir)
        assert len(engine2._active_goals) == 0

    def test_no_data_dir_skips_persistence(self) -> None:
        engine = ActionCycleEngine(data_dir=None)
        assert engine._state_path is None

    def test_load_handles_corrupt_json(self) -> None:
        state_path = self.tmp_dir / "action_cycle_state.json"
        state_path.write_text("NOT JSON", "utf-8")
        engine = ActionCycleEngine(data_dir=self.tmp_dir)
        assert len(engine._active_goals) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Full PDCA cycle integration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPDCACycle:
    def setup_method(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.engine = ActionCycleEngine(data_dir=self.tmp_dir)

    def teardown_method(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("core.action_cycle.time.time", return_value=1_000_000.0)
    def test_full_pdca_cycle(self, mock_time) -> None:
        # Plan
        goal = self.engine.plan({"interest_topics": ["history"], "quality_avg": 0.7})
        assert goal is not None
        assert goal.category == "learning"

        # Do: record progress incrementally
        for _ in range(10):
            self.engine.record_progress("topic_conversations", delta=1.0)

        # Check: high progress triggers completion
        results = self.engine.check()
        assert len(results) == 1
        assert results[0]["achievement"] in ("達成", "部分達成")
        assert len(self.engine._active_goals) == 0

        # Act: lessons learned
        lessons = self.engine.get_lessons()
        assert len(lessons) >= 1

        # Stats reflect completion
        s = self.engine.stats()
        assert s["active_goals"] == 0
        assert s["completed_cycles"] == 1
        assert s["success_rate"] > 0.0
