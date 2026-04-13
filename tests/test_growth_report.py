"""
GrowthReporter のテスト。

決定論的に検証するため LLM はダミー化し、
AiChan 本体は使わず、必要な属性だけ持つスタブで注入する。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.growth_report import GrowthReporter, DailySnapshot, WeeklySnapshot


# ─── スタブ ────────────────────────────────────────────────


class _StubDiary:
    def __init__(self, entries: dict[str, dict]) -> None:
        self._entries = entries

    def get_entry(self, date_str: str) -> dict | None:
        return self._entries.get(date_str)


class _StubEmotionHistory:
    def __init__(self, dailies: list[dict]) -> None:
        self._dailies = dailies

    def get_daily_averages(self, days: int = 14) -> list[dict]:
        return list(self._dailies[-days:])


class _StubInterestMap:
    def __init__(self, interests: dict[str, dict]) -> None:
        self._interests = interests

    def get_top(self, n: int = 15) -> list[dict]:
        items = [{"keyword": k, **v} for k, v in self._interests.items()]
        items.sort(key=lambda x: x.get("count", 0), reverse=True)
        return items[:n]

    def get_by_category(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for k, v in self._interests.items():
            cat = v.get("category", "その他")
            out.setdefault(cat, []).append({"keyword": k, "count": v.get("count", 0)})
        return out


class _StubMemory:
    def stats(self) -> dict:
        return {"short": 2, "mid": 5, "long": 1, "core": 3, "db_total": 11}


class _StubLearning:
    def stats(self) -> dict:
        return {"total_examples": 42}


class _StubLLM:
    def __init__(self, *, enabled: bool = False, response: str = "") -> None:
        self.enabled = enabled
        self.response = response

    def is_loaded(self) -> bool:
        return self.enabled

    def generate_chat(self, messages, max_tokens=None, **kwargs) -> str:
        return self.response


def _build_stub_ai(
    base_dir: Path,
    *,
    diary_entries: dict[str, dict] | None = None,
    emotion_dailies: list[dict] | None = None,
    interests: dict[str, dict] | None = None,
    llm_response: str = "",
    llm_enabled: bool = False,
) -> SimpleNamespace:
    ai = SimpleNamespace()
    ai.base_dir = base_dir
    ai.diary = _StubDiary(diary_entries or {})
    ai.emotion_history = _StubEmotionHistory(emotion_dailies or [])
    ai.interest_map = _StubInterestMap(interests or {})
    ai.memory = _StubMemory()
    ai.learning = _StubLearning()
    ai.llm = _StubLLM(enabled=llm_enabled, response=llm_response)
    ai.llm_loaded = llm_enabled
    return ai


# ─── daily ────────────────────────────────────────────────


@pytest.mark.unit
def test_collect_daily_with_entry(tmp_path: Path) -> None:
    today = date(2026, 4, 8)
    ai = _build_stub_ai(
        tmp_path,
        diary_entries={
            "2026-04-08": {
                "date": "2026-04-08",
                "summary": "今日はよく話した日だったよ。",
                "exchange_count": 7,
                "highlights": ["初めての成長レポートを作ったよ"],
            }
        },
        emotion_dailies=[
            {"date": "2026-04-08", "happiness": 0.8, "curiosity": 0.7,
             "affection": 0.9, "energy": 0.6, "anxiety": 0.2},
        ],
        interests={"AI": {"count": 10, "category": "技術・IT"}},
    )
    reporter = GrowthReporter(ai)
    snap = reporter.collect_daily(today)
    assert isinstance(snap, DailySnapshot)
    assert snap.date == "2026-04-08"
    assert snap.exchange_count == 7
    assert "成長レポート" in snap.highlights[0]
    assert snap.emotion_avg["happiness"] == pytest.approx(0.8)
    assert "AI" in snap.top_interests
    assert snap.memory_stats["core"] == 3
    assert snap.learning_examples == 42


@pytest.mark.unit
def test_collect_daily_without_entry(tmp_path: Path) -> None:
    ai = _build_stub_ai(tmp_path)
    snap = GrowthReporter(ai).collect_daily(date(2026, 4, 8))
    assert snap.exchange_count == 0
    assert "記録がない" in snap.diary_summary


@pytest.mark.unit
def test_generate_daily_writes_markdown(tmp_path: Path) -> None:
    ai = _build_stub_ai(
        tmp_path,
        diary_entries={
            "2026-04-08": {
                "date": "2026-04-08",
                "summary": "いろいろ話した日",
                "exchange_count": 5,
                "highlights": ["楽しかったこと"],
            }
        },
    )
    reporter = GrowthReporter(ai)
    path = reporter.generate_daily(date(2026, 4, 8))
    assert path.exists()
    text = path.read_text("utf-8")
    assert "2026-04-08" in text
    assert "今日の会話" in text
    assert "5" in text  # exchange_count
    # LLM 無効なのでフォールバック文が必ず入る
    assert "今日の私から一言" in text
    assert path.parent.name == "daily"


@pytest.mark.unit
def test_generate_daily_uses_llm_comment_when_available(tmp_path: Path) -> None:
    ai = _build_stub_ai(
        tmp_path,
        diary_entries={
            "2026-04-08": {
                "date": "2026-04-08",
                "summary": "静かな1日",
                "exchange_count": 3,
                "highlights": [],
            }
        },
        llm_enabled=True,
        llm_response="今日も一緒にいられて嬉しかったよ💕",
    )
    reporter = GrowthReporter(ai)
    path = reporter.generate_daily(date(2026, 4, 8))
    text = path.read_text("utf-8")
    assert "一緒にいられて" in text


@pytest.mark.unit
def test_generate_daily_truncates_overlong_llm_output(tmp_path: Path) -> None:
    long_text = "あ" * 800
    ai = _build_stub_ai(
        tmp_path,
        diary_entries={
            "2026-04-08": {
                "date": "2026-04-08",
                "summary": "s",
                "exchange_count": 1,
                "highlights": [],
            }
        },
        llm_enabled=True,
        llm_response=long_text,
    )
    path = GrowthReporter(ai).generate_daily(date(2026, 4, 8))
    text = path.read_text("utf-8")
    # 少なくとも 800 字丸ごとは入らない（切り詰められている）
    assert long_text not in text
    assert "…" in text


# ─── weekly ────────────────────────────────────────────────


@pytest.mark.unit
def test_collect_weekly_aggregates_exchanges(tmp_path: Path) -> None:
    # 2026-04-06 (Mon) 〜 2026-04-12 (Sun) = ISO week 15
    diary_entries = {
        "2026-04-06": {"exchange_count": 3},
        "2026-04-07": {"exchange_count": 5},
        "2026-04-08": {"exchange_count": 0},
        "2026-04-09": {"exchange_count": 2},
    }
    ai = _build_stub_ai(tmp_path, diary_entries=diary_entries)
    reporter = GrowthReporter(ai)
    snap = reporter.collect_weekly(2026, 15)
    assert isinstance(snap, WeeklySnapshot)
    assert snap.start_date == "2026-04-06"
    assert snap.end_date == "2026-04-12"
    assert snap.total_exchanges == 10
    assert snap.active_days == 3  # 3/5/2 がアクティブ（0 は除外）


@pytest.mark.unit
def test_generate_weekly_writes_markdown(tmp_path: Path) -> None:
    ai = _build_stub_ai(
        tmp_path,
        diary_entries={"2026-04-06": {"exchange_count": 4}},
        emotion_dailies=[
            {"date": "2026-04-06", "happiness": 0.7, "curiosity": 0.6,
             "affection": 0.8, "energy": 0.5, "anxiety": 0.3},
        ],
        interests={
            "AI": {"count": 10, "category": "技術・IT", "last_seen": "2026-04-06"},
            "新しいこと": {"count": 1, "category": "趣味・娯楽", "last_seen": "2026-04-06"},
        },
    )
    reporter = GrowthReporter(ai)
    path = reporter.generate_weekly(2026, 15)
    assert path.exists()
    text = path.read_text("utf-8")
    assert "週間成長記録" in text
    assert "2026-04-06" in text
    assert "AI" in text
    # 出現回数 <= 3 & 今週に last_seen = 新しい興味
    assert "新しいこと" in text
    assert path.parent.name == "weekly"


# ─── ジョブ用ラッパー ────────────────────────────────────


@pytest.mark.unit
def test_daily_job_returns_dict_for_autonomous(tmp_path: Path) -> None:
    ai = _build_stub_ai(
        tmp_path,
        diary_entries={date.today().isoformat(): {"exchange_count": 1}},
    )
    result = GrowthReporter(ai).daily_job()
    assert "summary" in result
    assert "path" in result
    assert Path(result["path"]).exists()


@pytest.mark.unit
def test_weekly_job_returns_dict_for_autonomous(tmp_path: Path) -> None:
    ai = _build_stub_ai(tmp_path)
    result = GrowthReporter(ai).weekly_job()
    assert "summary" in result
    assert Path(result["path"]).exists()


# ─── フォールバック検証 ────────────────────────────────


@pytest.mark.unit
def test_fallback_comment_when_no_conversation(tmp_path: Path) -> None:
    ai = _build_stub_ai(tmp_path)
    reporter = GrowthReporter(ai)
    snap = reporter.collect_daily(date(2026, 4, 8))
    msg = reporter._fallback_daily_comment(snap)
    assert isinstance(msg, str) and len(msg) > 0
