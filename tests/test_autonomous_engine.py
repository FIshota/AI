"""
AutonomousEngine のテスト。

決定論的に検証するため、内部スレッドは起動せず `tick(now)` を直接呼ぶ。

検証項目:
  - hourly ジョブは毎時1回だけ走る（同じ時間に複数回 tick しても1回）
  - daily ジョブは指定時刻ウィンドウ内で1回だけ走る
  - weekly ジョブは指定曜日・時刻で1回だけ走る
  - every_6h ジョブは 0/6/12/18 時ウィンドウで1回ずつ
  - ジョブが例外を吐いても他ジョブに影響せず、health.jsonl に ok=False で記録
  - autonomous_fired.json が再起動後も状態を保持
  - read_recent_health は新しい順に返す
  - register_job は同名上書き
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.autonomous_engine import AutonomousEngine, Job, JobResult


# ─── フィクスチャ ──────────────────────────────────────────────


@pytest.fixture
def engine(tmp_path: Path) -> AutonomousEngine:
    return AutonomousEngine(tmp_path)


def _counter_fn():
    """呼ばれた回数をカウントする callable を返す。"""
    state = {"n": 0}

    def fn():
        state["n"] += 1
        return {"n": state["n"], "summary": f"count={state['n']}"}

    fn.state = state  # type: ignore[attr-defined]
    return fn


# ─── hourly ────────────────────────────────────────────────────


@pytest.mark.unit
def test_hourly_runs_once_per_hour(engine: AutonomousEngine) -> None:
    fn = _counter_fn()
    engine.register_job(Job("h", "hourly", fn))

    t = datetime(2026, 4, 8, 10, 0, 0)
    engine.tick(t)
    engine.tick(t + timedelta(minutes=5))  # 同じ時間内はスキップ
    engine.tick(t + timedelta(minutes=9))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]

    # 次の時間に入ると再度発火
    engine.tick(t + timedelta(hours=1, minutes=2))
    assert fn.state["n"] == 2  # type: ignore[attr-defined]


@pytest.mark.unit
def test_hourly_window_is_first_10_minutes(engine: AutonomousEngine) -> None:
    fn = _counter_fn()
    engine.register_job(Job("h", "hourly", fn))

    # 11 分は対象外
    engine.tick(datetime(2026, 4, 8, 10, 11, 0))
    assert fn.state["n"] == 0  # type: ignore[attr-defined]

    # 0 分は対象内
    engine.tick(datetime(2026, 4, 8, 10, 0, 0))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]


# ─── every_6h ──────────────────────────────────────────────────


@pytest.mark.unit
def test_every_6h_fires_at_0_6_12_18(engine: AutonomousEngine) -> None:
    fn = _counter_fn()
    engine.register_job(Job("s", "every_6h", fn))

    # 3時は対象外
    engine.tick(datetime(2026, 4, 8, 3, 0, 0))
    assert fn.state["n"] == 0  # type: ignore[attr-defined]

    # 6時は対象
    engine.tick(datetime(2026, 4, 8, 6, 0, 0))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]

    # 6時台内では重複実行なし
    engine.tick(datetime(2026, 4, 8, 6, 9, 0))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]

    # 12時で再発火
    engine.tick(datetime(2026, 4, 8, 12, 0, 0))
    assert fn.state["n"] == 2  # type: ignore[attr-defined]


# ─── daily ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_daily_runs_once_per_day_in_window(engine: AutonomousEngine) -> None:
    fn = _counter_fn()
    engine.register_job(Job("d", "daily", fn, hour=2, minute=0))

    # 02:03 ウィンドウ内
    engine.tick(datetime(2026, 4, 8, 2, 3, 0))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]

    # 同じ日、別時刻は走らない
    engine.tick(datetime(2026, 4, 8, 2, 4, 0))
    engine.tick(datetime(2026, 4, 8, 10, 0, 0))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]

    # 翌日 02:00 は発火
    engine.tick(datetime(2026, 4, 9, 2, 0, 0))
    assert fn.state["n"] == 2  # type: ignore[attr-defined]


# ─── weekly ────────────────────────────────────────────────────


@pytest.mark.unit
def test_weekly_runs_on_configured_weekday(engine: AutonomousEngine) -> None:
    fn = _counter_fn()
    # 日曜 02:30
    engine.register_job(Job("w", "weekly", fn, hour=2, minute=30, weekday=6))

    # 2026-04-05 は日曜
    assert datetime(2026, 4, 5).weekday() == 6
    engine.tick(datetime(2026, 4, 5, 2, 30, 0))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]

    # 月曜は走らない
    engine.tick(datetime(2026, 4, 6, 2, 30, 0))
    assert fn.state["n"] == 1  # type: ignore[attr-defined]

    # 翌週日曜に再発火
    engine.tick(datetime(2026, 4, 12, 2, 30, 0))
    assert fn.state["n"] == 2  # type: ignore[attr-defined]


# ─── 例外隔離 ──────────────────────────────────────────────────


@pytest.mark.unit
def test_exception_in_one_job_does_not_break_others(engine: AutonomousEngine) -> None:
    good = _counter_fn()

    def bad():
        raise RuntimeError("boom")

    engine.register_job(Job("bad", "hourly", bad))
    engine.register_job(Job("good", "hourly", good))

    results = engine.tick(datetime(2026, 4, 8, 10, 0, 0))

    # 両方実行される
    names = {r.name: r for r in results}
    assert "bad" in names and "good" in names
    assert names["bad"].ok is False
    assert "boom" in names["bad"].message
    assert names["good"].ok is True
    assert good.state["n"] == 1  # type: ignore[attr-defined]


@pytest.mark.unit
def test_health_log_written_on_tick(engine: AutonomousEngine, tmp_path: Path) -> None:
    fn = _counter_fn()
    engine.register_job(Job("h", "hourly", fn))
    engine.tick(datetime(2026, 4, 8, 10, 0, 0))

    log = tmp_path / "data" / "health.jsonl"
    assert log.exists()
    lines = [l for l in log.read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["name"] == "h"
    assert row["ok"] is True
    assert row["cadence"] == "hourly"


# ─── 再起動耐性 ────────────────────────────────────────────────


@pytest.mark.unit
def test_fired_state_persists_across_instances(tmp_path: Path) -> None:
    fn_a = _counter_fn()
    engine_a = AutonomousEngine(tmp_path)
    engine_a.register_job(Job("h", "hourly", fn_a))
    engine_a.tick(datetime(2026, 4, 8, 10, 0, 0))
    assert fn_a.state["n"] == 1  # type: ignore[attr-defined]

    # 別インスタンス = 再起動相当
    fn_b = _counter_fn()
    engine_b = AutonomousEngine(tmp_path)
    engine_b.register_job(Job("h", "hourly", fn_b))
    engine_b.tick(datetime(2026, 4, 8, 10, 5, 0))  # 同じ時間
    assert fn_b.state["n"] == 0  # type: ignore[attr-defined]


# ─── ジョブ登録 ────────────────────────────────────────────────


@pytest.mark.unit
def test_register_job_overwrites_same_name(engine: AutonomousEngine) -> None:
    fn_old = _counter_fn()
    fn_new = _counter_fn()
    engine.register_job(Job("j", "hourly", fn_old))
    engine.register_job(Job("j", "hourly", fn_new))

    assert len(engine.list_jobs()) == 1
    engine.tick(datetime(2026, 4, 8, 10, 0, 0))
    assert fn_old.state["n"] == 0  # type: ignore[attr-defined]
    assert fn_new.state["n"] == 1  # type: ignore[attr-defined]


@pytest.mark.unit
def test_read_recent_health_returns_newest_first(engine: AutonomousEngine) -> None:
    engine.register_job(Job("h", "hourly", lambda: "ok"))
    engine.tick(datetime(2026, 4, 8, 10, 0, 0))
    engine.tick(datetime(2026, 4, 8, 11, 0, 0))
    engine.tick(datetime(2026, 4, 8, 12, 0, 0))

    recent = engine.read_recent_health(limit=5)
    assert len(recent) == 3
    # 新しい順
    times = [r["started_at"] for r in recent]
    assert times == sorted(times, reverse=True)
