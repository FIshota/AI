"""
MemoryManager の長期記憶 API テスト。

検証項目:
  - add_long_term は is_core=True で保存される
  - core_id を指定すると重複投入を防ぐ (upsert)
  - forget() は is_core レコードを削除しない
  - bootstrap_core_memories は CoreMemoryEntry のリストから一括投入できる
  - 既存DBに対するマイグレーション (ALTER TABLE ADD COLUMN) が動作する
  - 既存の add_mid_term / add_short_term など public API は壊れていない
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.memory import MemoryManager
from utils.personality_loader import CoreMemoryEntry


# ─── フィクスチャ ──────────────────────────────────────────────


@pytest.fixture
def manager(tmp_path: Path) -> MemoryManager:
    db = tmp_path / "memories.db"
    key = tmp_path / ".key"
    return MemoryManager(db_path=db, key_file=key, encrypt=True)


# ─── 長期記憶 (add_long_term) ──────────────────────────────────


@pytest.mark.unit
def test_add_long_term_marks_is_core(manager: MemoryManager) -> None:
    mem = manager.add_long_term("私はユーザーを大切に思っている", core_id="commit-1")

    assert mem.is_core is True
    assert mem.is_protected is True  # 二重保護
    assert mem.memory_type == "long"
    assert mem.core_id == "commit-1"


@pytest.mark.unit
def test_core_id_prevents_duplicate(manager: MemoryManager) -> None:
    first = manager.add_long_term("変わらない約束", core_id="commit-2")
    second = manager.add_long_term("別の文言（無視されるはず）", core_id="commit-2")

    # 同じ core_id は upsert: 既存を返し新規挿入しない
    assert first.id == second.id
    assert second.content == "変わらない約束"  # 上書きされていない
    cores = manager.get_core_memories()
    assert sum(1 for m in cores if m.core_id == "commit-2") == 1


@pytest.mark.unit
def test_forget_does_not_remove_core_memory(manager: MemoryManager) -> None:
    manager.add_long_term("絶対に忘れないコア記憶です", core_id="commit-3")
    manager.add_mid_term("ただの中期記憶です", importance=0.5)

    deleted = manager.forget("記憶")

    # 中期記憶は消えてもコア記憶は残る
    cores = manager.get_core_memories()
    assert any("絶対に忘れない" in m.content for m in cores)
    # 削除件数は0以上（中期は消える）
    assert deleted >= 0
    # コア記憶を直接 forget しようとしても消えない
    deleted2 = manager.forget("絶対に忘れない")
    assert deleted2 == 0


@pytest.mark.unit
def test_bootstrap_core_memories_from_yaml_entries(manager: MemoryManager) -> None:
    entries = [
        CoreMemoryEntry(
            id="bootstrap-1",
            content="一つ目の絶対記憶",
            tags=("self", "test"),
            importance=1.0,
        ),
        CoreMemoryEntry(
            id="bootstrap-2",
            content="二つ目の絶対記憶",
            tags=("user",),
            importance=0.9,
        ),
    ]

    result = manager.bootstrap_core_memories(entries)
    assert result["inserted"] == 2
    assert result["skipped"] == 0

    # 2回目の bootstrap は全部 skipped
    result2 = manager.bootstrap_core_memories(entries)
    assert result2["inserted"] == 0
    assert result2["skipped"] == 2

    cores = manager.get_core_memories()
    contents = {m.content for m in cores}
    assert "一つ目の絶対記憶" in contents
    assert "二つ目の絶対記憶" in contents


@pytest.mark.unit
def test_stats_reports_core_count(manager: MemoryManager) -> None:
    manager.add_long_term("コアA", core_id="A")
    manager.add_long_term("コアB", core_id="B")
    manager.add_mid_term("ふつうの記憶")

    stats = manager.stats()
    assert stats["core"] == 2
    assert stats["protected"] >= 2
    assert stats["db_total"] >= 3


# ─── 既存APIが壊れていないことの確認 ──────────────────────────


@pytest.mark.unit
def test_short_term_api_still_works(manager: MemoryManager) -> None:
    mem = manager.add_short_term("こんにちは", importance=0.5)
    assert mem.memory_type == "short"
    assert manager.get_short_term_context()[-1].content == "こんにちは"


@pytest.mark.unit
def test_mid_term_api_still_works(manager: MemoryManager) -> None:
    mem = manager.add_mid_term("中期記憶テスト", importance=0.6)
    assert mem.memory_type == "mid"
    found = manager.search("中期記憶")
    assert any("中期記憶" in m.content for m in found)


@pytest.mark.unit
def test_remember_explicit_command_still_works(manager: MemoryManager) -> None:
    mem = manager.remember("これは大事な情報", is_important=True)
    assert mem.is_protected is True
    # 「explicit_memory」タグが付与される
    assert "explicit_memory" in mem.tags


# ─── マイグレーション（旧スキーマ → 新スキーマ） ──────────────


@pytest.mark.unit
def test_migration_adds_core_columns_to_old_db(tmp_path: Path) -> None:
    """旧スキーマのDBを開いた時、is_core / core_id カラムが自動追加されること。"""
    db_path = tmp_path / "old_memories.db"

    # 旧スキーマで作成（is_core / core_id なし）
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE memories (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            content       TEXT NOT NULL,
            memory_type   TEXT NOT NULL,
            importance    REAL NOT NULL DEFAULT 0.5,
            emotional_weight REAL NOT NULL DEFAULT 0.5,
            tags          TEXT NOT NULL DEFAULT '[]',
            created_at    TEXT NOT NULL,
            accessed_at   TEXT NOT NULL,
            access_count  INTEGER NOT NULL DEFAULT 0,
            is_protected  INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE user_profile (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    conn.execute(
        "INSERT INTO memories (content, memory_type, created_at, accessed_at) "
        "VALUES (?, ?, ?, ?)",
        ("旧データ", "mid", "2026-04-01T00:00:00", "2026-04-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    # MemoryManager で開く → ALTER TABLE が走る
    mgr = MemoryManager(db_path=db_path, key_file=tmp_path / ".key", encrypt=False)

    # 新カラムが存在し、旧データも残っている
    with sqlite3.connect(db_path) as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(memories)").fetchall()}
        assert "is_core" in cols
        assert "core_id" in cols
        rows = c.execute("SELECT content FROM memories").fetchall()
        assert any("旧データ" in r[0] for r in rows)

    # 移行後にコア記憶を追加できる
    mgr.add_long_term("移行後コア", core_id="post-migrate-1")
    cores = mgr.get_core_memories()
    assert any("移行後コア" in m.content for m in cores)
