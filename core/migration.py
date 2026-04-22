"""
データベースマイグレーション管理

SQL マイグレーションを順序付きで適用し、適用済みを追跡する。
マイグレーション SQL はこのファイル内に埋め込まれている（別ファイル不要）。
"""
from __future__ import annotations
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 埋め込みマイグレーション定義 ──────────────────────────────────
# (名前, SQL) のタプルリスト。名前でソートされるため 001〜 の接頭辞を使う。
_EMBEDDED_MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_fts5_table_and_triggers",
        """
        -- FTS5 仮想テーブル（対応していない場合はスキップ）
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
        USING fts5(content, memory_type, tags, content=memories, content_rowid=id);

        -- INSERT トリガー
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content, memory_type, tags)
            VALUES (new.id, new.content, new.memory_type, new.tags);
        END;

        -- DELETE トリガー
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, memory_type, tags)
            VALUES ('delete', old.id, old.content, old.memory_type, old.tags);
        END;

        -- UPDATE トリガー
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, memory_type, tags)
            VALUES ('delete', old.id, old.content, old.memory_type, old.tags);
            INSERT INTO memories_fts(rowid, content, memory_type, tags)
            VALUES (new.id, new.content, new.memory_type, new.tags);
        END;
        """,
    ),
    (
        "002_memory_versions_table",
        """
        CREATE TABLE IF NOT EXISTS memory_versions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id       INTEGER NOT NULL,
            old_content     TEXT NOT NULL,
            old_importance  REAL,
            old_emotion_tag TEXT,
            changed_at      TEXT NOT NULL,
            FOREIGN KEY (memory_id) REFERENCES memories(id)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_versions_mid
            ON memory_versions(memory_id);
        """,
    ),
    (
        "003_emotion_tag_column",
        """
        -- emotion_tag カラムを安全に追加（既存の場合はスキップ）
        ALTER TABLE memories ADD COLUMN emotion_tag TEXT;
        """,
    ),
    (
        "004_security_level_column",
        """
        -- security_level カラムを安全に追加（既存の場合はスキップ）
        ALTER TABLE memories ADD COLUMN security_level TEXT DEFAULT 'public';
        """,
    ),
]


class MigrationManager:
    """
    SQLite データベースマイグレーション管理。
    適用済みマイグレーションを schema_migrations テーブルで追跡し、
    未適用のものだけを順番に実行する。
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.migrations_dir = Path(__file__).parent.parent / "data" / "migrations"
        # M5: スレッドローカル接続プール (memory.py と統一)
        self._thread_local = threading.local()
        self._ensure_migrations_dir()
        self._ensure_tracking_table()

    def _ensure_migrations_dir(self) -> None:
        """data/migrations/ ディレクトリが存在しなければ作成"""
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        """スレッドローカルキャッシュされた sqlite3 接続を返す (M5).

        memory.py と同一のパターン — 各スレッドが自分専用の接続を再利用する。
        """
        conn: sqlite3.Connection | None = getattr(self._thread_local, "conn", None)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
                self._thread_local.conn = None
        new_conn = sqlite3.connect(self.db_path, timeout=10.0)
        self._thread_local.conn = new_conn
        return new_conn

    def _ensure_tracking_table(self) -> None:
        """マイグレーション追跡テーブルを作成"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name       TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)

    def _get_applied(self) -> set[str]:
        """適用済みマイグレーション名の集合を返す"""
        with self._conn() as conn:
            cur = conn.execute("SELECT name FROM schema_migrations")
            return {row[0] for row in cur.fetchall()}

    def _apply(self, name: str, sql: str) -> None:
        """単一マイグレーションを適用し、追跡テーブルに記録する"""
        now = datetime.now().isoformat()
        with self._conn() as conn:
            try:
                # FTS5 マイグレーションは個別ステートメントで実行
                # (executescript は仮想テーブル作成でエラーになる場合がある)
                for statement in self._split_statements(sql):
                    statement = statement.strip()
                    if not statement:
                        continue
                    try:
                        conn.execute(statement)
                    except sqlite3.OperationalError as e:
                        error_msg = str(e).lower()
                        # "duplicate column" や "already exists" は無視（冪等性）
                        if "duplicate" in error_msg or "already exists" in error_msg:
                            logger.info(
                                "[Migration] %s: スキップ (既に存在): %s", name, e
                            )
                            continue
                        # FTS5 非対応の場合もスキップ
                        if "fts5" in error_msg or "no such module" in error_msg:
                            logger.info(
                                "[Migration] %s: FTS5 非対応のためスキップ: %s", name, e
                            )
                            continue
                        raise

                conn.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (name, now),
                )
                logger.info("[Migration] 適用完了: %s", name)
            except Exception as exc:
                logger.error("[Migration] 適用失敗 %s: %s", name, exc)
                raise

    @staticmethod
    def _split_statements(sql: str) -> list[str]:
        """SQL テキストをセミコロンで分割する（コメント行は保持）"""
        statements: list[str] = []
        current: list[str] = []
        for line in sql.split("\n"):
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            current.append(line)
            if stripped.endswith(";"):
                statements.append("\n".join(current))
                current = []
        # 末尾にセミコロンなしの残りがあれば追加
        remainder = "\n".join(current).strip()
        if remainder:
            statements.append(remainder)
        return statements

    def run_pending(self) -> list[str]:
        """
        未適用のマイグレーションを順番に実行する。
        戻り値: 今回適用したマイグレーション名のリスト
        """
        applied = self._get_applied()
        pending = [
            (name, sql)
            for name, sql in _EMBEDDED_MIGRATIONS
            if name not in applied
        ]
        # 名前順でソート（001_, 002_, ... の順序保証）
        pending.sort(key=lambda x: x[0])

        applied_now: list[str] = []
        for name, sql in pending:
            try:
                self._apply(name, sql)
                applied_now.append(name)
            except Exception as exc:
                logger.error(
                    "[Migration] %s で停止: %s (以降のマイグレーションはスキップ)",
                    name, exc,
                )
                break

        if applied_now:
            logger.info(
                "[Migration] %d 件のマイグレーションを適用: %s",
                len(applied_now), ", ".join(applied_now),
            )
        else:
            logger.debug("[Migration] 適用すべきマイグレーションはありません")

        return applied_now

    def get_status(self) -> dict:
        """マイグレーション状況の要約を返す"""
        applied = self._get_applied()
        all_names = [name for name, _ in _EMBEDDED_MIGRATIONS]
        pending = [n for n in all_names if n not in applied]
        return {
            "total": len(all_names),
            "applied": sorted(applied),
            "pending": pending,
        }
