"""
Tests for core/self_will.py

Covers: DesireType enum, Desire frozen dataclass, DesireGenerator,
WillDecider, ActionExecutor, and SelfWillEngine.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.self_will import (
    ActionExecutor,
    Desire,
    DesireGenerator,
    DesireType,
    SelfWillEngine,
    WillDecider,
    WillRecord,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DesireType / Desire
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDesireType:
    def test_enum_values(self) -> None:
        assert DesireType.CURIOSITY.value == "curiosity"
        assert DesireType.CONNECTION.value == "connection"
        assert DesireType.EXPRESSION.value == "expression"
        assert DesireType.GROWTH.value == "growth"
        assert DesireType.CARE.value == "care"
        assert DesireType.PLAY.value == "play"
        assert DesireType.MAINTENANCE.value == "maintenance"

    def test_is_str_enum(self) -> None:
        assert isinstance(DesireType.CURIOSITY, str)
        assert DesireType.CARE == "care"


class TestDesire:
    def test_frozen_dataclass(self) -> None:
        desire = Desire(
            desire_type=DesireType.CURIOSITY,
            intensity=0.7,
            description="test",
            trigger="unit_test",
            action_key="learn_topic",
        )
        with pytest.raises(AttributeError):
            desire.intensity = 0.9  # type: ignore[misc]

    def test_default_params(self) -> None:
        desire = Desire(
            desire_type=DesireType.PLAY,
            intensity=0.5,
            description="play",
            trigger="test",
            action_key="play",
        )
        assert desire.params == {}

    def test_custom_params(self) -> None:
        desire = Desire(
            desire_type=DesireType.CARE,
            intensity=0.5,
            description="rest",
            trigger="late",
            action_key="suggest_rest",
            params={"hour": 23},
        )
        assert desire.params == {"hour": 23}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DesireGenerator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDesireGenerator:
    def setup_method(self) -> None:
        self.gen = DesireGenerator()

    def test_empty_context_no_deterministic_desires(self) -> None:
        """With empty context and seeded random, PLAY may or may not appear."""
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate({})
        assert len(desires) == 0

    def test_interests_generate_curiosity(self) -> None:
        ctx: dict[str, Any] = {"interest_topics": ["Python", "AI"]}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        curiosity = [d for d in desires if d.desire_type == DesireType.CURIOSITY]
        assert len(curiosity) == 1
        assert "Python" in curiosity[0].description
        assert curiosity[0].params["topic"] == "Python"

    def test_curiosity_intensity_caps_at_0_9(self) -> None:
        ctx: dict[str, Any] = {"interest_topics": ["a", "b", "c", "d", "e", "f", "g"]}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        curiosity = [d for d in desires if d.desire_type == DesireType.CURIOSITY]
        assert curiosity[0].intensity == pytest.approx(0.9)

    def test_idle_generates_connection(self) -> None:
        ctx: dict[str, Any] = {"idle_minutes": 60}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        conn = [d for d in desires if d.desire_type == DesireType.CONNECTION]
        assert len(conn) == 1
        assert conn[0].intensity > 0.3

    def test_idle_below_threshold_no_connection(self) -> None:
        ctx: dict[str, Any] = {"idle_minutes": 20}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        conn = [d for d in desires if d.desire_type == DesireType.CONNECTION]
        assert len(conn) == 0

    def test_late_hour_generates_care(self) -> None:
        for hour in [23, 0, 3, 4]:
            ctx: dict[str, Any] = {"hour": hour}
            with patch("core.self_will.random.random", return_value=1.0):
                desires = self.gen.generate(ctx)
            care = [d for d in desires if d.desire_type == DesireType.CARE]
            assert len(care) == 1, f"Expected CARE desire at hour={hour}"

    def test_normal_hour_no_care(self) -> None:
        ctx: dict[str, Any] = {"hour": 12}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        care = [d for d in desires if d.desire_type == DesireType.CARE]
        assert len(care) == 0

    def test_milestone_turn_generates_growth(self) -> None:
        ctx: dict[str, Any] = {"turn_count": 100}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        growth = [d for d in desires if d.desire_type == DesireType.GROWTH]
        assert len(growth) == 1
        assert growth[0].intensity == pytest.approx(0.6)

    def test_non_milestone_turn_no_growth(self) -> None:
        ctx: dict[str, Any] = {"turn_count": 99}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        growth = [d for d in desires if d.desire_type == DesireType.GROWTH]
        assert len(growth) == 0

    def test_unhealthy_generates_maintenance(self) -> None:
        ctx: dict[str, Any] = {"health_status": "degraded"}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        maint = [d for d in desires if d.desire_type == DesireType.MAINTENANCE]
        assert len(maint) == 1
        assert maint[0].intensity == pytest.approx(0.7)

    def test_high_joy_generates_expression(self) -> None:
        ctx: dict[str, Any] = {"emotion": {"joy": 0.9, "curiosity": 0.3}}
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.gen.generate(ctx)
        expr = [d for d in desires if d.desire_type == DesireType.EXPRESSION]
        assert len(expr) == 1
        assert expr[0].params["emotion"] == "joy"

    def test_play_triggered_by_low_random(self) -> None:
        with patch("core.self_will.random.random", return_value=0.1):
            desires = self.gen.generate({})
        play = [d for d in desires if d.desire_type == DesireType.PLAY]
        assert len(play) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WillDecider
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestWillDecider:
    def setup_method(self) -> None:
        self.decider = WillDecider()

    def test_empty_desires_returns_none(self) -> None:
        assert self.decider.decide([]) is None

    def test_care_beats_play_at_equal_intensity(self) -> None:
        care = Desire(
            desire_type=DesireType.CARE,
            intensity=0.5,
            description="care",
            trigger="t",
            action_key="suggest_rest",
        )
        play = Desire(
            desire_type=DesireType.PLAY,
            intensity=0.5,
            description="play",
            trigger="t",
            action_key="play",
        )
        result = self.decider.decide([play, care])
        assert result is care

    def test_maintenance_beats_curiosity(self) -> None:
        maint = Desire(
            desire_type=DesireType.MAINTENANCE,
            intensity=0.7,
            description="maint",
            trigger="t",
            action_key="self_maintenance",
        )
        cur = Desire(
            desire_type=DesireType.CURIOSITY,
            intensity=0.7,
            description="curious",
            trigger="t",
            action_key="learn_topic",
        )
        result = self.decider.decide([cur, maint])
        assert result is maint

    def test_high_intensity_can_override_priority(self) -> None:
        care_low = Desire(
            desire_type=DesireType.CARE,
            intensity=0.1,
            description="care",
            trigger="t",
            action_key="suggest_rest",
        )
        play_high = Desire(
            desire_type=DesireType.PLAY,
            intensity=0.95,
            description="play",
            trigger="t",
            action_key="play",
        )
        result = self.decider.decide([care_low, play_high])
        # PLAY at 0.95 intensity can beat CARE at 0.1
        # Score(care) = 0.1 * (0.4 + 0.6 * 1.0) = 0.1
        # Score(play) = 0.95 * (0.4 + 0.6 * (1 - 6/7)) ≈ 0.95 * 0.4857 ≈ 0.461
        assert result is play_high

    def test_single_desire_returned(self) -> None:
        d = Desire(
            desire_type=DesireType.GROWTH,
            intensity=0.6,
            description="grow",
            trigger="t",
            action_key="self_improve",
        )
        assert self.decider.decide([d]) is d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ActionExecutor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestActionExecutor:
    def setup_method(self) -> None:
        self.executor = ActionExecutor()

    def test_register_and_can_execute(self) -> None:
        self.executor.register("learn_topic", lambda d: "ok")
        assert self.executor.can_execute("learn_topic") is True
        assert self.executor.can_execute("unknown") is False

    def test_execute_registered_handler(self) -> None:
        handler = MagicMock(return_value="learned something")
        self.executor.register("learn_topic", handler)

        desire = Desire(
            desire_type=DesireType.CURIOSITY,
            intensity=0.7,
            description="learn",
            trigger="t",
            action_key="learn_topic",
            params={"topic": "AI"},
        )
        result = self.executor.execute(desire)

        assert result["ok"] is True
        assert result["result"] == "learned something"
        handler.assert_called_once_with(desire)

    def test_execute_unregistered_action(self) -> None:
        desire = Desire(
            desire_type=DesireType.PLAY,
            intensity=0.5,
            description="play",
            trigger="t",
            action_key="nonexistent",
        )
        result = self.executor.execute(desire)
        assert result["ok"] is False
        assert "未登録" in result["error"]

    def test_execute_handler_exception(self) -> None:
        def failing_handler(d: Desire) -> str:
            raise RuntimeError("boom")

        self.executor.register("fail_action", failing_handler)
        desire = Desire(
            desire_type=DesireType.PLAY,
            intensity=0.5,
            description="fail",
            trigger="t",
            action_key="fail_action",
        )
        result = self.executor.execute(desire)
        assert result["ok"] is False
        assert "boom" in result["error"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SelfWillEngine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSelfWillEngine:
    def setup_method(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmp_dir)
        self.engine = SelfWillEngine(data_dir=self.data_dir)

    def teardown_method(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _register_all_actions(self) -> None:
        """Register handlers for all standard action keys."""
        for key in [
            "learn_topic",
            "initiate_chat",
            "express_feeling",
            "self_improve",
            "suggest_rest",
            "play",
            "self_maintenance",
        ]:
            self.engine.executor.register(key, lambda d, k=key: f"executed_{k}")

    def test_think_returns_none_when_no_desires(self) -> None:
        with patch("core.self_will.random.random", return_value=1.0):
            result = self.engine.think({"hour": 12})
        assert result is None

    def test_think_executes_desire(self) -> None:
        self._register_all_actions()
        ctx: dict[str, Any] = {"hour": 23, "health_status": "degraded"}
        with patch("core.self_will.random.random", return_value=1.0):
            result = self.engine.think(ctx)
        assert result is not None
        assert result["result"]["ok"] is True

    def test_think_filters_low_intensity(self) -> None:
        """Desires below MIN_INTENSITY (0.3) are filtered out."""
        self._register_all_actions()
        # idle_minutes=31 produces intensity ~0.3 + (1/60)*0.3 = ~0.305
        # Just barely above threshold, should produce a desire
        ctx: dict[str, Any] = {"idle_minutes": 31}
        with patch("core.self_will.random.random", return_value=1.0):
            result = self.engine.think(ctx)
        assert result is not None

    def test_cooldown_prevents_repeated_action(self) -> None:
        self._register_all_actions()
        ctx: dict[str, Any] = {"hour": 23}

        with patch("core.self_will.random.random", return_value=1.0):
            first = self.engine.think(ctx)
        assert first is not None

        # Second call within cooldown should return None for same action
        with patch("core.self_will.random.random", return_value=1.0):
            second = self.engine.think(ctx)
        assert second is None

    def test_cooldown_expires(self) -> None:
        self._register_all_actions()
        ctx: dict[str, Any] = {"hour": 23}

        with patch("core.self_will.random.random", return_value=1.0):
            first = self.engine.think(ctx)
        assert first is not None

        action_key = first["action"]
        # Fast-forward the last action time
        self.engine._last_action_time[action_key] = time.time() - 200

        with patch("core.self_will.random.random", return_value=1.0):
            second = self.engine.think(ctx)
        assert second is not None

    def test_think_returns_none_for_unregistered_action(self) -> None:
        # Do NOT register handlers
        ctx: dict[str, Any] = {"hour": 23}
        with patch("core.self_will.random.random", return_value=1.0):
            result = self.engine.think(ctx)
        assert result is None

    def test_get_current_desires(self) -> None:
        ctx: dict[str, Any] = {
            "interest_topics": ["math"],
            "hour": 23,
        }
        with patch("core.self_will.random.random", return_value=1.0):
            desires = self.engine.get_current_desires(ctx)
        assert len(desires) >= 2
        # Sorted by intensity descending
        intensities = [d["intensity"] for d in desires]
        assert intensities == sorted(intensities, reverse=True)

    def test_pending_message_clears_after_read(self) -> None:
        self.engine._pending_message = "hello"
        assert self.engine.pending_message == "hello"
        assert self.engine.pending_message is None

    def test_pending_message_none_by_default(self) -> None:
        assert self.engine.pending_message is None

    def test_stats_empty(self) -> None:
        stats = self.engine.stats()
        assert stats["total_actions"] == 0
        assert stats["successful"] == 0
        assert stats["by_type"] == {}

    def test_stats_after_actions(self) -> None:
        self._register_all_actions()
        ctx: dict[str, Any] = {"hour": 23}
        with patch("core.self_will.random.random", return_value=1.0):
            self.engine.think(ctx)
        stats = self.engine.stats()
        assert stats["total_actions"] == 1
        assert stats["successful"] == 1

    def test_persistence_save_and_load(self) -> None:
        self._register_all_actions()
        ctx: dict[str, Any] = {"hour": 0}
        with patch("core.self_will.random.random", return_value=1.0):
            self.engine.think(ctx)

        state_path = self.data_dir / "self_will_state.json"
        assert state_path.exists()

        data = json.loads(state_path.read_text("utf-8"))
        assert "last_action_time" in data
        assert "recent_actions" in data
        assert data["total_actions"] >= 1

    def test_persistence_load_restores_cooldown(self) -> None:
        self._register_all_actions()
        ctx: dict[str, Any] = {"hour": 0}
        with patch("core.self_will.random.random", return_value=1.0):
            self.engine.think(ctx)

        # Create a new engine from the same data dir
        engine2 = SelfWillEngine(data_dir=self.data_dir)
        engine2.executor.register("suggest_rest", lambda d: "ok")

        # Cooldown should still be in effect from persisted state
        with patch("core.self_will.random.random", return_value=1.0):
            result = engine2.think(ctx)
        assert result is None

    def test_no_data_dir_no_persistence(self) -> None:
        engine = SelfWillEngine(data_dir=None)
        engine.executor.register("suggest_rest", lambda d: "ok")
        ctx: dict[str, Any] = {"hour": 23}
        with patch("core.self_will.random.random", return_value=1.0):
            result = engine.think(ctx)
        assert result is not None
        # No file should be created anywhere specific

    def test_history_cap(self) -> None:
        self._register_all_actions()
        # Manually stuff history beyond MAX_HISTORY
        for i in range(SelfWillEngine.MAX_HISTORY + 10):
            self.engine._history.append(
                WillRecord(
                    desire=Desire(
                        desire_type=DesireType.PLAY,
                        intensity=0.5,
                        description=f"play_{i}",
                        trigger="t",
                        action_key="play",
                    ),
                    decided_at=float(i),
                    executed=True,
                )
            )
        # A think call should trim history
        ctx: dict[str, Any] = {"hour": 0}
        # Reset cooldown so action fires
        self.engine._last_action_time.clear()
        with patch("core.self_will.random.random", return_value=1.0):
            self.engine.think(ctx)
        assert len(self.engine._history) <= SelfWillEngine.MAX_HISTORY

    def test_get_status_text_with_context(self) -> None:
        self._register_all_actions()
        ctx: dict[str, Any] = {"hour": 23}
        with patch("core.self_will.random.random", return_value=1.0):
            self.engine.think(ctx)
        with patch("core.self_will.random.random", return_value=1.0):
            text = self.engine.get_status_text(ctx)
        assert "自己意思エンジン" in text
        assert "累計行動" in text

    def test_get_status_text_without_context(self) -> None:
        text = self.engine.get_status_text()
        assert "自己意思エンジン" in text
        assert "累計行動: 0回" in text

    def test_corrupt_state_file_handled(self) -> None:
        state_path = self.data_dir / "self_will_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("not valid json", "utf-8")
        # Should not raise
        engine = SelfWillEngine(data_dir=self.data_dir)
        assert engine._last_action_time == {}
