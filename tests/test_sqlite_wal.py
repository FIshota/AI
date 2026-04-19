"""
SQLite WAL モード並行アクセステスト

10 スレッドによる同時読み書きを行い、WAL モードの SQLite が
デッドロックやデータ破損なしに動作するか検証する。
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import List

import pytest

# テスト用の DB セットアップ


def _create_test_db(db_path: str) -> None:
    """テスト用のデータベースを WAL モードで作成する。"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('total', 0)")
    conn.commit()
    conn.close()


def _writer_thread(
    db_path: str,
    thread_id: int,
    n_writes: int,
    errors: List[str],
) -> None:
    """書き込みスレッド: n_writes 回 INSERT する。"""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        for i in range(n_writes):
            content = f"Thread-{thread_id} Message-{i}"
            try:
                conn.execute(
                    "INSERT INTO messages (thread_id, content) VALUES (?, ?)",
                    (thread_id, content),
                )
                conn.execute(
                    "UPDATE counters SET value = value + 1 WHERE name = 'total'"
                )
                conn.commit()
            except sqlite3.OperationalError as exc:
                # busy retry
                if "locked" in str(exc).lower():
                    time.sleep(0.01)
                    try:
                        conn.execute(
                            "INSERT INTO messages (thread_id, content) VALUES (?, ?)",
                            (thread_id, content),
                        )
                        conn.commit()
                    except Exception as retry_exc:
                        errors.append(
                            f"Writer {thread_id} retry failed: {retry_exc}"
                        )
                else:
                    errors.append(f"Writer {thread_id}: {exc}")
        conn.close()
    except Exception as exc:
        errors.append(f"Writer {thread_id} fatal: {exc}")


def _reader_thread(
    db_path: str,
    thread_id: int,
    n_reads: int,
    errors: List[str],
    results: List[int],
) -> None:
    """読み取りスレッド: n_reads 回 SELECT する。"""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        for _ in range(n_reads):
            try:
                cursor = conn.execute("SELECT COUNT(*) FROM messages")
                count = cursor.fetchone()[0]
                results.append(count)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    errors.append(f"Reader {thread_id}: {exc}")
            time.sleep(0.001)
        conn.close()
    except Exception as exc:
        errors.append(f"Reader {thread_id} fatal: {exc}")


# ── テスト ──────────────────────────────────────────────


def test_concurrent_readwrite_10_threads() -> None:
    """10 スレッドで同時に読み書きしてもエラーが発生しないこと。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_wal.db")
        _create_test_db(db_path)

        n_writers = 5
        n_readers = 5
        writes_per_thread = 20
        reads_per_thread = 30

        errors: List[str] = []
        read_results: List[int] = []
        threads: List[threading.Thread] = []

        # ライタースレッド
        for i in range(n_writers):
            t = threading.Thread(
                target=_writer_thread,
                args=(db_path, i, writes_per_thread, errors),
            )
            threads.append(t)

        # リーダースレッド
        for i in range(n_readers):
            t = threading.Thread(
                target=_reader_thread,
                args=(db_path, i + n_writers, reads_per_thread, errors, read_results),
            )
            threads.append(t)

        # 全スレッド開始
        for t in threads:
            t.start()

        # 全スレッド完了待ち (タイムアウト 30 秒)
        for t in threads:
            t.join(timeout=30)

        # エラーがないこと
        assert not errors, f"並行アクセスエラー: {errors}"

        # 書き込み総数を検証
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM messages")
        total = cursor.fetchone()[0]
        conn.close()

        expected = n_writers * writes_per_thread
        assert total == expected, (
            f"書き込み数不一致: {total} (期待: {expected})"
        )


def test_wal_mode_persists() -> None:
    """WAL モードが再接続後も維持されていること。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_wal_persist.db")
        _create_test_db(db_path)

        # 再接続してジャーナルモードを確認
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()

        assert mode.lower() == "wal", f"ジャーナルモード: {mode} (WAL 期待)"


def test_counter_consistency() -> None:
    """カウンター更新が並行書き込みでも一貫性を保つこと。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_counter.db")
        _create_test_db(db_path)

        n_threads = 10
        increments_per_thread = 50
        errors: List[str] = []
        threads: List[threading.Thread] = []

        def _increment(thread_id: int) -> None:
            try:
                conn = sqlite3.connect(db_path, timeout=10)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                for _ in range(increments_per_thread):
                    try:
                        conn.execute(
                            "UPDATE counters SET value = value + 1 WHERE name = 'total'"
                        )
                        conn.commit()
                    except sqlite3.OperationalError:
                        time.sleep(0.01)
                        try:
                            conn.execute(
                                "UPDATE counters SET value = value + 1 WHERE name = 'total'"
                            )
                            conn.commit()
                        except Exception as exc:
                            errors.append(f"Thread {thread_id}: {exc}")
                conn.close()
            except Exception as exc:
                errors.append(f"Thread {thread_id} fatal: {exc}")

        for i in range(n_threads):
            t = threading.Thread(target=_increment, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"カウンターエラー: {errors}"

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT value FROM counters WHERE name = 'total'")
        value = cursor.fetchone()[0]
        conn.close()

        expected = n_threads * increments_per_thread
        assert value == expected, (
            f"カウンター不一致: {value} (期待: {expected})"
        )
