"""
三層記憶管理システム

短期記憶 (Short-term): 現在の会話コンテキスト（RAM上）
中期記憶 (Mid-term):   最近の重要な出来事・学習内容（DB保存）
長期記憶 (Long-term):  圧縮された過去の経験・コア知識（DB保存・暗号化）

保護領域: アイのコア人格・重要な思い出は絶対に削除しない
"""
from __future__ import annotations
import sqlite3
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional
from utils.crypto import load_or_create_key, encrypt_text, decrypt_text


@dataclass
class Memory:
    content: str
    memory_type: str          # "short", "mid", "long"
    importance: float         # 0.0 ~ 1.0
    emotional_weight: float   # 0.0 ~ 1.0  感情的重要度
    tags: list[str]
    created_at: str
    accessed_at: str
    access_count: int = 0
    is_protected: bool = False   # True = 通常の forget() で削除されない
    is_core: bool = False        # True = 絶対記憶 (forget でも削除されない)
    core_id: Optional[str] = None  # personality/memories.yaml のキー (重複投入防止)
    id: Optional[int] = None


class MemoryManager:
    """
    アイの三層記憶管理システム
    """

    # 新規DB用スキーマ。インデックス作成はマイグレーション後に行う。
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS memories (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        content       TEXT NOT NULL,
        memory_type   TEXT NOT NULL,
        importance    REAL NOT NULL DEFAULT 0.5,
        emotional_weight REAL NOT NULL DEFAULT 0.5,
        tags          TEXT NOT NULL DEFAULT '[]',
        created_at    TEXT NOT NULL,
        accessed_at   TEXT NOT NULL,
        access_count  INTEGER NOT NULL DEFAULT 0,
        is_protected  INTEGER NOT NULL DEFAULT 0,
        is_core       INTEGER NOT NULL DEFAULT 0,
        core_id       TEXT
    );
    CREATE TABLE IF NOT EXISTS user_profile (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """

    def __init__(self, db_path: str | Path, key_file: str | Path, encrypt: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.encrypt = encrypt
        self.key = load_or_create_key(key_file) if encrypt else None

        # 短期記憶（RAM）
        self._short_term: list[Memory] = []
        self.short_term_max = 20

        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(self.SCHEMA)
            # WAL モードで同時読み書き時のロック競合を軽減
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=5000;")
            except Exception:
                pass
            # 既存DBへのマイグレーション: is_core / core_id カラムが無ければ追加
            self._migrate_add_core_columns(conn)

    def _migrate_add_core_columns(self, conn: sqlite3.Connection) -> None:
        """is_core / core_id カラムが存在しない旧DBに対して安全に追加。"""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
        if "is_core" not in existing:
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN is_core INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError as e:
                print(f"[Memory] ALTER ADD is_core 失敗: {e}", flush=True)
        if "core_id" not in existing:
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN core_id TEXT")
            except sqlite3.OperationalError as e:
                print(f"[Memory] ALTER ADD core_id 失敗: {e}", flush=True)
        # 既存DBにもユニーク部分インデックスを保証
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_core_id "
                "ON memories (core_id) WHERE core_id IS NOT NULL"
            )
        except sqlite3.OperationalError as e:
            print(f"[Memory] core_id インデックス作成失敗: {e}", flush=True)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def _enc(self, text: str) -> str:
        if self.encrypt and self.key:
            return encrypt_text(text, self.key)
        return text

    _decrypt_warning_shown = False

    def _dec(self, text: str) -> str:
        if self.encrypt and self.key:
            try:
                return decrypt_text(text, self.key)
            except Exception as e:
                if not MemoryManager._decrypt_warning_shown:
                    print(f"[Memory] 復号化失敗 (鍵ローテーション？): {e}", flush=True)
                    MemoryManager._decrypt_warning_shown = True
                return text  # 未暗号化データへの後方互換
        return text

    # ─── 短期記憶 ────────────────────────────────────────────────

    def add_short_term(self, content: str, importance: float = 0.5,
                       emotional_weight: float = 0.5, tags: list[str] | None = None) -> Memory:
        """現在の会話に短期記憶を追加します"""
        now = datetime.now().isoformat()
        mem = Memory(
            content=content,
            memory_type="short",
            importance=importance,
            emotional_weight=emotional_weight,
            tags=tags or [],
            created_at=now,
            accessed_at=now,
        )
        self._short_term.append(mem)

        # 超過した場合、重要度の低いものを中期記憶へ昇格または破棄
        if len(self._short_term) > self.short_term_max:
            self._promote_or_discard_short_term()

        return mem

    def _promote_or_discard_short_term(self):
        """重要度スコアに基づき短期記憶を中期記憶へ昇格させます"""
        threshold = 0.4
        promoted = []
        kept = []
        discarded = []

        for mem in self._short_term[:-10]:  # 直近10件は常に保持
            score = mem.importance * 0.6 + mem.emotional_weight * 0.4
            if score >= threshold or mem.is_protected:
                promoted.append(mem)
            else:
                discarded.append(mem)

        for mem in promoted:
            mem.memory_type = "mid"
            self._save_to_db(mem)

        self._short_term = self._short_term[-10:]

    # ─── 中期・長期記憶（DB） ─────────────────────────────────────

    def add_mid_term(self, content: str, importance: float = 0.5,
                     emotional_weight: float = 0.5, tags: list[str] | None = None,
                     is_protected: bool = False) -> Memory:
        """中期記憶を追加します（DB保存・暗号化）"""
        now = datetime.now().isoformat()
        mem = Memory(
            content=content,
            memory_type="mid",
            importance=importance,
            emotional_weight=emotional_weight,
            tags=tags or [],
            created_at=now,
            accessed_at=now,
            is_protected=is_protected,
        )
        self._save_to_db(mem)
        return mem

    def remember(self, content: str, is_important: bool = False) -> Memory:
        """
        「これを覚えて」コマンド用。
        is_important=True の場合は保護領域に格納します。
        """
        importance = 0.9 if is_important else 0.7
        return self.add_mid_term(
            content=content,
            importance=importance,
            emotional_weight=0.6,
            tags=["explicit_memory"],
            is_protected=is_important,
        )

    def forget(self, query: str) -> int:
        """
        「これを忘れて」コマンド用。
        保護領域 (is_protected=1) およびコア記憶 (is_core=1) は削除できません。
        戻り値: 削除件数
        """
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT id, content FROM memories WHERE is_protected = 0 AND is_core = 0"
            )
            rows = cur.fetchall()
            deleted = 0
            for row_id, enc_content in rows:
                content = self._dec(enc_content)
                if query.lower() in content.lower():
                    conn.execute("DELETE FROM memories WHERE id = ?", (row_id,))
                    deleted += 1
            return deleted

    # ─── 長期記憶 (絶対忘れない) ─────────────────────────────────

    def add_long_term(
        self,
        content: str,
        is_core: bool = True,
        core_id: str | None = None,
        importance: float = 1.0,
        emotional_weight: float = 0.7,
        tags: list[str] | None = None,
    ) -> Memory:
        """
        長期記憶を追加します（DB保存・暗号化・絶対削除不可）。

        is_core=True (デフォルト) の場合、forget() / 通常の削除APIから
        完全に保護されます。personality/memories.yaml の起動時投入で
        使用されます。

        core_id を渡すと「同じキーの再投入を防ぐ」upsert 動作になります。
        """
        if core_id is not None:
            existing = self._get_by_core_id(core_id)
            if existing is not None:
                return existing

        now = datetime.now().isoformat()
        mem = Memory(
            content=content,
            memory_type="long",
            importance=importance,
            emotional_weight=emotional_weight,
            tags=tags or [],
            created_at=now,
            accessed_at=now,
            is_protected=True,  # 二重保護
            is_core=is_core,
            core_id=core_id,
        )
        self._save_to_db(mem)
        return mem

    def _get_by_core_id(self, core_id: str) -> Memory | None:
        """core_id をキーに既存のコア記憶を取得（重複投入防止）。"""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM memories WHERE core_id = ? LIMIT 1",
                (core_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_memory(row, self._dec(row[1]))

    def bootstrap_core_memories(self, entries) -> dict:
        """
        personality/memories.yaml の core_memories を一括で長期記憶に投入。

        entries: Iterable[CoreMemoryEntry] (utils.personality_loader)
        戻り値: {"inserted": N, "skipped": N}
        """
        inserted = 0
        skipped = 0
        for e in entries:
            try:
                core_id = getattr(e, "id", None)
                content = getattr(e, "content", None)
                if not core_id or not content:
                    continue
                tags = list(getattr(e, "tags", ()) or [])
                importance = float(getattr(e, "importance", 1.0))
                before = self._get_by_core_id(core_id)
                self.add_long_term(
                    content=content,
                    is_core=True,
                    core_id=core_id,
                    importance=importance,
                    emotional_weight=0.7,
                    tags=tags,
                )
                if before is None:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as exc:
                print(f"[Memory] core_memory bootstrap 失敗 ({getattr(e, 'id', '?')}): {exc}", flush=True)
        return {"inserted": inserted, "skipped": skipped}

    def get_core_memories(self) -> list[Memory]:
        """全てのコア記憶を取得（personality/memories.yaml 起源）。"""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM memories WHERE is_core = 1 ORDER BY importance DESC"
            )
            return [self._row_to_memory(r, self._dec(r[1])) for r in cur.fetchall()]

    def _save_to_db(self, mem: Memory) -> int:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO memories
                   (content, memory_type, importance, emotional_weight,
                    tags, created_at, accessed_at, access_count, is_protected,
                    is_core, core_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self._enc(mem.content),
                    mem.memory_type,
                    mem.importance,
                    mem.emotional_weight,
                    json.dumps(mem.tags, ensure_ascii=False),
                    mem.created_at,
                    now,
                    mem.access_count,
                    int(mem.is_protected),
                    int(mem.is_core),
                    mem.core_id,
                ),
            )
            mem.id = cur.lastrowid
        return mem.id

    # ─── 検索・取得 ──────────────────────────────────────────────

    def search(self, query: str, limit: int = 5) -> list[Memory]:
        """キーワードで記憶を検索します（短期＋DB）"""
        results = []

        # 短期記憶を検索
        for mem in reversed(self._short_term):
            if query.lower() in mem.content.lower():
                results.append(mem)

        # DB検索
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM memories ORDER BY importance DESC, accessed_at DESC LIMIT 100"
            )
            rows = cur.fetchall()
            for row in rows:
                content = self._dec(row[1])
                if query.lower() in content.lower():
                    results.append(self._row_to_memory(row, content))
                if len(results) >= limit:
                    break

        return results[:limit]

    def search_by_keywords(self, query: str, limit: int = 5) -> list[Memory]:
        """
        クエリをキーワード分割し、SQL の LIKE で効率的に検索します。
        Sprint 2.0: 全件フェッチせず DB 側でフィルタリング。
        """
        results: list[Memory] = []

        # 短期記憶を検索
        q_lower = query.lower()
        for mem in reversed(self._short_term):
            if q_lower in mem.content.lower():
                results.append(mem)

        # クエリを分かち書き（助詞を除く2文字以上のキーワード）
        keywords = [w for w in q_lower.replace("　", " ").split() if len(w) >= 2]
        if not keywords:
            keywords = [q_lower]

        # SQL LIKE で絞り込み（暗号化時はフォールバック）
        if self.encrypt:
            # 暗号化時は復号しないと LIKE が使えないので従来ロジック
            return self.search(query, limit=limit)

        with self._conn() as conn:
            # 各キーワードを OR 条件で検索
            where_clauses = " OR ".join(["content LIKE ?"] * len(keywords))
            params = [f"%{kw}%" for kw in keywords]
            sql = (
                f"SELECT * FROM memories WHERE ({where_clauses}) "
                f"ORDER BY importance DESC, accessed_at DESC LIMIT ?"
            )
            params.append(limit * 2)  # 余裕を持って取得
            cur = conn.execute(sql, params)
            for row in cur.fetchall():
                content = self._dec(row[1])
                results.append(self._row_to_memory(row, content))
                if len(results) >= limit:
                    break

        return results[:limit]

    def get_recent(self, limit: int = 10, memory_type: str | None = None) -> list[Memory]:
        """最近の記憶を取得します"""
        results = list(reversed(self._short_term[-limit:]))

        if memory_type is None or memory_type != "short":
            where = "WHERE memory_type = ?" if memory_type else ""
            params = (memory_type,) if memory_type else ()
            with self._conn() as conn:
                cur = conn.execute(
                    f"SELECT * FROM memories {where} ORDER BY accessed_at DESC LIMIT ?",
                    (*params, limit),
                )
                for row in cur.fetchall():
                    content = self._dec(row[1])
                    results.append(self._row_to_memory(row, content))

        return results[:limit]

    def get_important(self, threshold: float = 0.7) -> list[Memory]:
        """重要度の高い記憶を取得します"""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM memories WHERE importance >= ? ORDER BY importance DESC",
                (threshold,),
            )
            return [self._row_to_memory(r, self._dec(r[1])) for r in cur.fetchall()]

    def get_short_term_context(self) -> list[Memory]:
        """現在の短期記憶コンテキストを返します"""
        return list(self._short_term)

    def _row_to_memory(self, row: tuple, decrypted_content: str) -> Memory:
        # row indices: 0=id, 1=content, 2=memory_type, 3=importance,
        # 4=emotional_weight, 5=tags, 6=created_at, 7=accessed_at,
        # 8=access_count, 9=is_protected, 10=is_core (新), 11=core_id (新)
        is_core = bool(row[10]) if len(row) > 10 else False
        core_id = row[11] if len(row) > 11 else None
        return Memory(
            id=row[0],
            content=decrypted_content,
            memory_type=row[2],
            importance=row[3],
            emotional_weight=row[4],
            tags=json.loads(row[5]),
            created_at=row[6],
            accessed_at=row[7],
            access_count=row[8],
            is_protected=bool(row[9]),
            is_core=is_core,
            core_id=core_id,
        )

    # ─── ユーザープロファイル ──────────────────────────────────────

    def set_user_profile(self, key: str, value: str):
        """ユーザー情報を保存します（例: 名前、誕生日、好き嫌い）"""
        enc_value = self._enc(value)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_profile (key, value) VALUES (?, ?)",
                (key, enc_value),
            )

    def get_user_profile(self, key: str) -> str | None:
        with self._conn() as conn:
            cur = conn.execute("SELECT value FROM user_profile WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                return self._dec(row[0])
        return None

    def get_all_user_profile(self) -> dict:
        with self._conn() as conn:
            cur = conn.execute("SELECT key, value FROM user_profile")
            return {k: self._dec(v) for k, v in cur.fetchall()}

    # ─── 統計 ────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            protected = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE is_protected = 1"
            ).fetchone()[0]
            core = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE is_core = 1"
            ).fetchone()[0]
            by_type = {}
            for row in conn.execute(
                "SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type"
            ).fetchall():
                by_type[row[0]] = row[1]
        return {
            "short_term_count": len(self._short_term),
            "db_total": total,
            "protected": protected,
            "core": core,
            "by_type": by_type,
        }
