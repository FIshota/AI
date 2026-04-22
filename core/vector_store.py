"""M9 Phase 1: VectorStore Protocol abstraction.

Provides a backend-agnostic interface for the vector search used by
``core.semantic_search.SemanticSearchEngine``. Before this module, FAISS
calls were inlined into the engine; now engine → VectorStore interface →
(FaissVectorStore | SQLiteVecVectorStore).

Design goals
------------
1. **Identity refactor**: ``FaissVectorStore`` preserves the exact FAISS
   behavior that existed before (``IndexFlatIP`` + ``normalize_L2``).
2. **Opt-in sqlite-vec**: ``SQLiteVecVectorStore`` is a fully working impl
   but is **only constructible** when both ``sqlite_vec`` is installed AND
   ``sqlite3.Connection.enable_load_extension`` works. Detection is via
   ``utils.sqlite_vec_support.check_sqlite_vec_support``.
3. **Single pickle-compatible persistence** per backend — callers need not
   know which file layout is used.

The engine chooses the backend based on ``settings["semantic_search"]
["backend"]`` (``"faiss"`` default, ``"sqlite-vec"`` opt-in).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Protocol
# ──────────────────────────────────────────────────────────────


@runtime_checkable
class VectorStore(Protocol):
    """Minimal interface needed by ``SemanticSearchEngine``.

    All vectors are float32 numpy arrays, already normalized if cosine
    similarity is desired (callers must normalize before passing).
    ``search`` returns ``(db_ids, scores)`` where scores are higher=better
    (inner product convention).
    """

    backend_name: str

    def load(self) -> None:
        """Read persisted state from disk (no-op if none)."""

    def rebuild(self, db_ids: Sequence[int], embeddings) -> None:
        """Replace the entire index with ``(db_ids, embeddings)``."""

    def add(self, db_id: int, embedding) -> None:
        """Append a single (id, embedding) pair."""

    def search(self, query_embedding, k: int) -> tuple[list[int], list[float]]:
        """Return top-k ``(db_ids, scores)``."""
        ...

    def count(self) -> int:
        """Number of vectors currently indexed."""
        ...

    def save(self) -> None:
        """Flush to disk."""
        ...

    def close(self) -> None:
        """Release any resources (connections, memory-mapped files)."""
        ...


# ──────────────────────────────────────────────────────────────
# FAISS backend (identity refactor of the previous inline code)
# ──────────────────────────────────────────────────────────────


class FaissVectorStore:
    """Pre-existing FAISS-backed vector store, extracted verbatim.

    Files used (under ``data_dir``):
        - ``semantic_index.bin``   — FAISS IndexFlatIP binary
        - ``semantic_map.json``    — JSON list mapping FAISS row → DB id

    This class exists to preserve the on-disk format of existing
    installations. Do NOT change the file names without a migration.
    """

    backend_name = "faiss"

    def __init__(self, data_dir: Path, dim: int = 384):
        self.data_dir = Path(data_dir)
        self._index_path = self.data_dir / "semantic_index.bin"
        self._map_path = self.data_dir / "semantic_map.json"
        self._dim = int(dim)
        if self._dim <= 0:
            raise ValueError(f"dim must be > 0, got {self._dim}")
        self._index = None  # lazy: FAISS index
        self._id_map: list[int] = []
        self._lock = threading.RLock()

    # ───── lazy FAISS import ─────
    def _faiss(self):
        import faiss  # type: ignore[import-not-found]
        return faiss

    # ───── Protocol impl ─────
    def load(self) -> None:
        with self._lock:
            if not self._index_path.exists() or not self._map_path.exists():
                return
            try:
                faiss = self._faiss()
                self._index = faiss.read_index(str(self._index_path))
                self._id_map = json.loads(self._map_path.read_text("utf-8"))
            except Exception as exc:
                logger.warning("[FaissVectorStore] load failed: %s — starting empty", exc)
                self._index = None
                self._id_map = []

    def rebuild(self, db_ids: Sequence[int], embeddings) -> None:
        faiss = self._faiss()
        import numpy as np

        embeddings = embeddings.astype(np.float32)
        dim = int(embeddings.shape[1])
        index = faiss.IndexFlatIP(dim)
        faiss.normalize_L2(embeddings)
        index.add(embeddings)

        with self._lock:
            self._index = index
            self._id_map = list(db_ids)
            self._dim = dim

    def add(self, db_id: int, embedding) -> None:
        faiss = self._faiss()
        import numpy as np

        embedding = embedding.astype(np.float32)
        faiss.normalize_L2(embedding)
        with self._lock:
            if self._index is None:
                self._index = faiss.IndexFlatIP(int(embedding.shape[1]))
            self._index.add(embedding)
            self._id_map.append(int(db_id))

    def search(self, query_embedding, k: int) -> tuple[list[int], list[float]]:
        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return [], []
            faiss = self._faiss()
            import numpy as np

            q = query_embedding.astype(np.float32)
            faiss.normalize_L2(q)
            k = min(max(1, int(k)), self._index.ntotal)
            scores, indices = self._index.search(q, k)
            ids_out: list[int] = []
            scores_out: list[float] = []
            for idx, sc in zip(indices[0], scores[0]):
                if idx < 0 or idx >= len(self._id_map):
                    continue
                ids_out.append(self._id_map[idx])
                scores_out.append(float(sc))
            return ids_out, scores_out

    def count(self) -> int:
        with self._lock:
            if self._index is None:
                return 0
            return int(self._index.ntotal)

    def save(self) -> None:
        with self._lock:
            if self._index is None:
                return
            faiss = self._faiss()
            faiss.write_index(self._index, str(self._index_path))
            self._map_path.write_text(
                json.dumps(self._id_map, ensure_ascii=False), "utf-8"
            )

    def close(self) -> None:
        with self._lock:
            # FAISS has no explicit close
            self._index = None


# ──────────────────────────────────────────────────────────────
# sqlite-vec backend (opt-in, future default)
# ──────────────────────────────────────────────────────────────


class SQLiteVecUnavailable(RuntimeError):
    """Raised when SQLiteVecVectorStore cannot be constructed in this env."""


class SQLiteVecVectorStore:
    """sqlite-vec backed vector store using vec0 virtual table.

    Availability is probed at construction via
    ``utils.sqlite_vec_support.check_sqlite_vec_support``. If either
    ``sqlite_vec`` is missing or the stdlib ``sqlite3`` build has no
    loadable-extension support, construction raises
    ``SQLiteVecUnavailable`` — callers should catch and fall back to
    ``FaissVectorStore``.

    Files used (under ``data_dir``):
        - ``semantic_vec.db``   — SQLite DB with `vec_items` virtual table

    The id mapping is stored as a regular table alongside the virtual
    table, so there is a single source of truth per backend.
    """

    backend_name = "sqlite-vec"

    def __init__(self, data_dir: Path, dim: int = 384):
        from utils.sqlite_vec_support import check_sqlite_vec_support

        report = check_sqlite_vec_support()
        if not report.usable:
            raise SQLiteVecUnavailable(
                f"sqlite-vec backend not available: {report.error or 'unknown'}"
            )

        self.data_dir = Path(data_dir)
        self._db_path = self.data_dir / "semantic_vec.db"
        self._dim = int(dim)
        if self._dim <= 0:
            raise ValueError(f"dim must be > 0, got {self._dim}")
        self._conn = None  # sqlite3.Connection
        self._report = report
        self._lock = threading.RLock()

    # ───── internal ─────
    def _connect(self):
        import sqlite3
        import sqlite_vec  # type: ignore[import-not-found]

        self.data_dir.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + self._lock lets us share the connection
        # across threads without raising ProgrammingError.
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        # Schema (idempotent):
        #   vec_items: vec0 virtual table (float32, cosine distance)
        #   id_map:    mapping row -> db_id (rowid correspondence)
        # Note: dim is interpolated into DDL because SQLite parameterized
        # queries cannot bind schema identifiers. `self._dim` is validated
        # to be a positive int in __init__, so this is safe. nosec B608
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0("
            f"embedding float[{int(self._dim)}] distance_metric=cosine)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS id_map ("
            "rowid INTEGER PRIMARY KEY, db_id INTEGER NOT NULL)"
        )
        conn.commit()
        return conn

    # ───── Protocol impl ─────
    def _require_conn(self):
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def load(self) -> None:
        with self._lock:
            self._require_conn()

    def rebuild(self, db_ids: Sequence[int], embeddings) -> None:
        import numpy as np

        embeddings = embeddings.astype(np.float32)
        with self._lock:
            conn = self._require_conn()
            conn.execute("DELETE FROM vec_items")
            conn.execute("DELETE FROM id_map")
            for i, (db_id, emb) in enumerate(zip(db_ids, embeddings), start=1):
                conn.execute(
                    "INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)",
                    (i, emb.tobytes()),
                )
                conn.execute(
                    "INSERT INTO id_map(rowid, db_id) VALUES (?, ?)",
                    (i, int(db_id)),
                )
            conn.commit()

    def add(self, db_id: int, embedding) -> None:
        import numpy as np

        embedding = embedding.astype(np.float32)
        if embedding.ndim == 2:
            embedding = embedding[0]
        with self._lock:
            conn = self._require_conn()
            # Let SQLite auto-assign rowid (atomic, no TOCTOU) and reuse
            # lastrowid for the id_map side. vec0 virtual table accepts
            # INSERT without explicit rowid.
            cur = conn.execute(
                "INSERT INTO vec_items(embedding) VALUES (?)",
                (embedding.tobytes(),),
            )
            new_rowid = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO id_map(rowid, db_id) VALUES (?, ?)",
                (new_rowid, int(db_id)),
            )
            conn.commit()

    def search(self, query_embedding, k: int) -> tuple[list[int], list[float]]:
        import numpy as np

        q = query_embedding.astype(np.float32)
        if q.ndim == 2:
            q = q[0]
        with self._lock:
            conn = self._require_conn()
            k = max(1, int(k))
            rows = conn.execute(
                "SELECT id_map.db_id, vec_items.distance "
                "FROM vec_items JOIN id_map ON id_map.rowid = vec_items.rowid "
                "WHERE vec_items.embedding MATCH ? ORDER BY vec_items.distance "
                "LIMIT ?",
                (q.tobytes(), k),
            ).fetchall()
            ids = [int(r[0]) for r in rows]
            # cosine *distance* → similarity (for compatibility with FAISS IP)
            scores = [1.0 - float(r[1]) for r in rows]
            return ids, scores

    def count(self) -> int:
        with self._lock:
            if self._conn is None:
                return 0
            row = self._conn.execute("SELECT COUNT(*) FROM vec_items").fetchone()
            return int(row[0]) if row else 0

    def save(self) -> None:
        with self._lock:
            # WAL + autocommit on each INSERT; no batched flush needed.
            if self._conn is not None:
                self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None


# ──────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────


def make_vector_store(
    backend: str, data_dir: Path, dim: int = 384
) -> VectorStore:
    """Construct the requested backend, falling back to FAISS on failure.

    ``backend`` values:
        - ``"faiss"`` (default)
        - ``"sqlite-vec"`` (opt-in; falls back to FAISS with warning if env
          does not support it)
    """
    backend = (backend or "faiss").lower()
    if backend == "sqlite-vec":
        try:
            return SQLiteVecVectorStore(data_dir=data_dir, dim=dim)
        except SQLiteVecUnavailable as exc:
            logger.warning(
                "[M9] sqlite-vec unavailable (%s) — falling back to faiss",
                exc,
            )
            return FaissVectorStore(data_dir=data_dir, dim=dim)
    return FaissVectorStore(data_dir=data_dir, dim=dim)
