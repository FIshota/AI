"""
Sprint 3.0: B) 知識拡張 + C) 生活アシスタント + D) UI/UX のテスト
"""
from __future__ import annotations

import json
import pytest
from datetime import date, timedelta
from pathlib import Path


# ── RAG Engine ───────────────────────────────────────────

class TestRAGEngine:
    def test_add_text_document(self, tmp_path: Path):
        from core.rag_engine import RAGEngine
        (tmp_path / "data").mkdir()
        rag = RAGEngine(tmp_path)

        doc = tmp_path / "test.txt"
        doc.write_text("アイはデスクトップペットです。感情エンジンを持っています。", encoding="utf-8")
        result = rag.add_document(doc)
        assert result["status"] == "indexed"
        assert result["chunks"] >= 1

    def test_search_returns_relevant(self, tmp_path: Path):
        from core.rag_engine import RAGEngine
        (tmp_path / "data").mkdir()
        rag = RAGEngine(tmp_path)

        doc = tmp_path / "ai.txt"
        doc.write_text("アイはPythonで作られたAIペットです。Phi-3モデルを使って会話します。", encoding="utf-8")
        rag.add_document(doc)

        results = rag.search("Python")
        assert len(results) >= 1
        assert "Python" in results[0]["text"]

    def test_duplicate_detection(self, tmp_path: Path):
        from core.rag_engine import RAGEngine
        (tmp_path / "data").mkdir()
        rag = RAGEngine(tmp_path)

        doc = tmp_path / "test.txt"
        doc.write_text("テストドキュメントの内容です。これは重複検出のテスト用です。", encoding="utf-8")
        rag.add_document(doc)
        result2 = rag.add_document(doc)
        assert result2["status"] == "already_indexed"

    def test_list_and_remove(self, tmp_path: Path):
        from core.rag_engine import RAGEngine
        (tmp_path / "data").mkdir()
        rag = RAGEngine(tmp_path)

        doc = tmp_path / "test.txt"
        doc.write_text("テストドキュメントの内容です。リストと削除のテスト用。", encoding="utf-8")
        result = rag.add_document(doc)
        assert len(rag.list_documents()) == 1

        rag.remove_document(result["doc_id"])
        assert len(rag.list_documents()) == 0

    def test_search_for_context(self, tmp_path: Path):
        from core.rag_engine import RAGEngine
        (tmp_path / "data").mkdir()
        rag = RAGEngine(tmp_path)

        doc = tmp_path / "info.txt"
        doc.write_text("東京タワーの高さは333メートルです。" * 5, encoding="utf-8")
        rag.add_document(doc)

        ctx = rag.search_for_context("東京タワー")
        assert "参考資料" in ctx


# ── Memory Summarizer ────────────────────────────────────

class TestMemorySummarizer:
    def test_should_summarize(self, tmp_path: Path):
        from core.memory_summarizer import MemorySummarizer
        (tmp_path / "data").mkdir()
        ms = MemorySummarizer(tmp_path)

        short_history = [{"role": "user", "content": "hi"}] * 10
        assert ms.should_summarize(short_history) is False

        long_history = [{"role": "user", "content": "hi"}] * 20
        assert ms.should_summarize(long_history) is True

    def test_rule_based_summarize(self, tmp_path: Path):
        from core.memory_summarizer import MemorySummarizer
        (tmp_path / "data").mkdir()
        ms = MemorySummarizer(tmp_path)

        history = []
        for i in range(20):
            history.append({"role": "user", "content": f"質問{i}？"})
            history.append({"role": "assistant", "content": f"回答{i}"})

        result = ms.summarize_and_trim(history)
        # 最新8メッセージが残るはず
        assert len(result) == 8

    def test_recent_summary(self, tmp_path: Path):
        from core.memory_summarizer import MemorySummarizer
        (tmp_path / "data").mkdir()
        ms = MemorySummarizer(tmp_path)

        history = [{"role": "user", "content": f"msg{i}"} for i in range(20)]
        ms.summarize_and_trim(history)
        summary = ms.get_recent_summary()
        assert len(summary) > 0


# ── Task Manager ─────────────────────────────────────────

class TestTaskManager:
    def test_add_from_text(self, tmp_path: Path):
        from core.task_manager import TaskManager
        (tmp_path / "data").mkdir()
        tm = TaskManager(tmp_path)

        task = tm.add_from_text("明日までにレポートを書く")
        assert task.title
        assert task.id == 1

    def test_add_with_due_date(self, tmp_path: Path):
        from core.task_manager import TaskManager
        (tmp_path / "data").mkdir()
        tm = TaskManager(tmp_path)

        task = tm.add_from_text("明日までにプレゼン準備")
        expected = (date.today() + timedelta(days=1)).isoformat()
        assert task.due_date == expected

    def test_complete_task(self, tmp_path: Path):
        from core.task_manager import TaskManager
        (tmp_path / "data").mkdir()
        tm = TaskManager(tmp_path)

        task = tm.add("テストタスク")
        assert tm.complete(task.id) is True
        pending = tm.list_pending()
        assert len(pending) == 0

    def test_priority_detection(self, tmp_path: Path):
        from core.task_manager import TaskManager
        (tmp_path / "data").mkdir()
        tm = TaskManager(tmp_path)

        urgent = tm.add_from_text("至急レポート提出")
        assert urgent.priority == "urgent"

        low = tm.add_from_text("いつかやる掃除")
        assert low.priority == "low"

    def test_format_task_list(self, tmp_path: Path):
        from core.task_manager import TaskManager
        (tmp_path / "data").mkdir()
        tm = TaskManager(tmp_path)

        tm.add("タスクA")
        tm.add("タスクB")
        output = tm.format_task_list()
        assert "タスクA" in output
        assert "タスクB" in output

    def test_persistence(self, tmp_path: Path):
        from core.task_manager import TaskManager
        (tmp_path / "data").mkdir()
        tm1 = TaskManager(tmp_path)
        tm1.add("永続化テスト")

        tm2 = TaskManager(tmp_path)
        assert len(tm2.list_pending()) == 1


# ── Habit Tracker ────────────────────────────────────────

class TestHabitTracker:
    def test_add_and_record(self, tmp_path: Path):
        from core.habit_tracker import HabitTracker
        (tmp_path / "data").mkdir()
        ht = HabitTracker(tmp_path)

        ht.add_habit("運動", emoji="🏃")
        ht.record("運動")
        assert ht.get_streak("運動") == 1

    def test_today_status(self, tmp_path: Path):
        from core.habit_tracker import HabitTracker
        (tmp_path / "data").mkdir()
        ht = HabitTracker(tmp_path)

        ht.add_habit("読書")
        status = ht.get_today_status()
        assert "読書" in status
        assert "⬜" in status  # まだ記録してない

        ht.record("読書")
        status = ht.get_today_status()
        assert "✅" in status

    def test_weekly_report(self, tmp_path: Path):
        from core.habit_tracker import HabitTracker
        (tmp_path / "data").mkdir()
        ht = HabitTracker(tmp_path)

        ht.add_habit("勉強")
        ht.record("勉強")
        report = ht.get_weekly_report()
        assert "勉強" in report

    def test_remove_habit(self, tmp_path: Path):
        from core.habit_tracker import HabitTracker
        (tmp_path / "data").mkdir()
        ht = HabitTracker(tmp_path)

        ht.add_habit("テスト")
        assert ht.remove_habit("テスト") is True
        assert "テスト" not in ht.list_habits()


# ── Expression Engine ────────────────────────────────────

class TestExpressionEngine:
    def test_classify_emotion(self):
        from core.expression_engine import classify_emotion
        assert classify_emotion({"happiness": 0.9, "energy": 0.8}) == "excited"
        assert classify_emotion({"happiness": 0.7, "energy": 0.5}) == "happy"
        assert classify_emotion({"happiness": 0.2, "energy": 0.2}) == "sad"
        assert classify_emotion({"anxiety": 0.8}) == "anxious"
        assert classify_emotion({"energy": 0.1}) == "tired"

    def test_apply_emotion_returns_image(self, tmp_path: Path):
        from core.expression_engine import ExpressionEngine
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not available")

        (tmp_path / "assets" / "expressions").mkdir(parents=True)
        engine = ExpressionEngine(tmp_path)

        base = Image.new("RGBA", (100, 100), (255, 200, 200, 255))
        result = engine.apply_emotion(base, {"happiness": 0.9, "energy": 0.8})
        assert result.size == (100, 100)

    def test_emotion_emoji(self, tmp_path: Path):
        from core.expression_engine import ExpressionEngine
        (tmp_path / "assets" / "expressions").mkdir(parents=True)
        engine = ExpressionEngine(tmp_path)
        # デフォルトは neutral
        assert engine.get_emotion_emoji() == "🙂"
