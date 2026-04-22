"""M9 Phase 1: VectorStore Protocol + FaissVectorStore + sqlite-vec probe tests.

Goals:
  - Protocol surface is stable (FaissVectorStore conforms at runtime)
  - FaissVectorStore round-trip works (rebuild → search → add → save → reload)
  - sqlite-vec probe returns a well-formed report in any environment
  - Factory (make_vector_store) falls back to FAISS when sqlite-vec is unusable
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

pytest.importorskip("faiss", reason="faiss-cpu not installed")
pytest.importorskip("numpy", reason="numpy not installed")

from core.vector_store import (  # noqa: E402
    FaissVectorStore,
    SQLiteVecUnavailable,
    SQLiteVecVectorStore,
    VectorStore,
    make_vector_store,
)
from utils.sqlite_vec_support import check_sqlite_vec_support  # noqa: E402


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────


def _random_embeddings(n: int, dim: int = 8):
    import numpy as np
    rng = np.random.default_rng(42)
    emb = rng.standard_normal((n, dim)).astype("float32")
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return emb / norms


# ────────────────────────────────────────────────────────────
# Protocol conformance
# ────────────────────────────────────────────────────────────


class TestProtocolConformance:
    def test_faiss_is_vector_store(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        assert isinstance(store, VectorStore)
        assert store.backend_name == "faiss"

    def test_required_methods_exist(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        for name in ("load", "rebuild", "add", "search", "count", "save", "close"):
            assert callable(getattr(store, name)), f"missing method: {name}"


# ────────────────────────────────────────────────────────────
# FaissVectorStore round-trip
# ────────────────────────────────────────────────────────────


class TestFaissVectorStore:
    def test_empty_count_zero(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        assert store.count() == 0

    def test_search_empty_returns_empty(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        q = _random_embeddings(1, dim=8)
        ids, scores = store.search(q, k=5)
        assert ids == [] and scores == []

    def test_rebuild_then_search(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        embs = _random_embeddings(10, dim=8)
        db_ids = list(range(100, 110))
        store.rebuild(db_ids=db_ids, embeddings=embs)
        assert store.count() == 10

        # Querying with an indexed vector should return that vector's id first
        q = embs[3:4]
        ids, scores = store.search(q, k=3)
        assert ids[0] == 103
        # Inner product of normalized identical vector ≈ 1.0
        assert scores[0] == pytest.approx(1.0, abs=1e-4)

    def test_add_incremental(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        embs = _random_embeddings(3, dim=8)
        for i, emb in enumerate(embs):
            store.add(db_id=200 + i, embedding=emb.reshape(1, -1))
        assert store.count() == 3
        ids, _ = store.search(embs[1:2], k=1)
        assert ids[0] == 201

    def test_save_and_reload(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        embs = _random_embeddings(5, dim=8)
        store.rebuild(db_ids=[10, 11, 12, 13, 14], embeddings=embs)
        store.save()

        # New instance loads the same state
        store2 = FaissVectorStore(data_dir=tmp_path, dim=8)
        store2.load()
        assert store2.count() == 5
        ids, _ = store2.search(embs[2:3], k=1)
        assert ids[0] == 12

    def test_load_missing_files_is_safe(self, tmp_path):
        empty_dir = tmp_path / "no-index"
        empty_dir.mkdir()
        store = FaissVectorStore(data_dir=empty_dir, dim=8)
        store.load()  # must not raise
        assert store.count() == 0


# ────────────────────────────────────────────────────────────
# sqlite-vec support probe (always runnable)
# ────────────────────────────────────────────────────────────


class TestSQLiteVecSupportProbe:
    def test_probe_returns_report(self):
        r = check_sqlite_vec_support()
        assert isinstance(r.usable, bool)
        assert isinstance(r.has_enable_load_extension, bool)
        assert isinstance(r.sqlite_vec_installed, bool)
        assert isinstance(r.sqlite_version, str) and r.sqlite_version
        assert isinstance(r.hints, tuple)

    def test_probe_consistency(self):
        r = check_sqlite_vec_support()
        # usable ↔ both conditions
        assert r.usable == (r.has_enable_load_extension and r.sqlite_vec_installed)


class TestSQLiteVecVectorStore:
    """Only meaningful when the environment actually supports sqlite-vec."""

    def test_construction_raises_when_unsupported(self, tmp_path):
        report = check_sqlite_vec_support()
        if report.usable:
            pytest.skip("sqlite-vec is actually supported here")
        with pytest.raises(SQLiteVecUnavailable):
            SQLiteVecVectorStore(data_dir=tmp_path, dim=8)

    def test_round_trip_when_supported(self, tmp_path):
        report = check_sqlite_vec_support()
        if not report.usable:
            pytest.skip(f"sqlite-vec unavailable: {report.error}")

        store = SQLiteVecVectorStore(data_dir=tmp_path, dim=8)
        embs = _random_embeddings(4, dim=8)
        store.rebuild(db_ids=[1, 2, 3, 4], embeddings=embs)
        assert store.count() == 4
        ids, _ = store.search(embs[2:3], k=1)
        assert ids[0] == 3
        store.close()


# ────────────────────────────────────────────────────────────
# Factory fallback
# ────────────────────────────────────────────────────────────


class TestMakeVectorStore:
    def test_default_is_faiss(self, tmp_path):
        store = make_vector_store(backend="faiss", data_dir=tmp_path, dim=8)
        assert store.backend_name == "faiss"

    def test_unknown_falls_to_faiss(self, tmp_path):
        store = make_vector_store(backend="bogus", data_dir=tmp_path, dim=8)
        assert store.backend_name == "faiss"

    def test_sqlite_vec_falls_back_when_unsupported(self, tmp_path):
        report = check_sqlite_vec_support()
        store = make_vector_store(backend="sqlite-vec", data_dir=tmp_path, dim=8)
        if not report.usable:
            # Must fall back to faiss without raising
            assert store.backend_name == "faiss"
        else:
            assert store.backend_name == "sqlite-vec"
            store.close()
