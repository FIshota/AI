"""M9 Phase 2: migration script の FAISS 読み込みロジック単体テスト。

sqlite-vec 不要（`_load_faiss_index` のみ検証）。実移行は env 依存のため
`scripts/migrate_faiss_to_sqlite_vec.py` のエンドツーエンド実行は手動。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

pytest.importorskip("faiss", reason="faiss-cpu not installed")
pytest.importorskip("numpy", reason="numpy not installed")

# scripts/ を import path に追加してモジュールをロード
import importlib.util

_SCRIPT = _ROOT / "scripts" / "migrate_faiss_to_sqlite_vec.py"
_spec = importlib.util.spec_from_file_location("migrate_faiss_to_sqlite_vec", _SCRIPT)
migrate_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(migrate_mod)  # type: ignore[union-attr]

from core.vector_store import FaissVectorStore  # noqa: E402


def _random_embeddings(n: int, dim: int):
    import numpy as np
    rng = np.random.default_rng(7)
    emb = rng.standard_normal((n, dim)).astype("float32")
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return emb / norms


class TestLoadFaissIndex:
    def test_round_trip_from_real_faiss_store(self, tmp_path):
        """FaissVectorStore で保存した index を migration script が正しく読めるか。"""
        store = FaissVectorStore(data_dir=tmp_path, dim=16)
        embs = _random_embeddings(8, dim=16)
        ids_in = [10, 11, 12, 13, 14, 15, 16, 17]
        store.rebuild(db_ids=ids_in, embeddings=embs)
        store.save()

        ids_out, embs_out, dim = migrate_mod._load_faiss_index(tmp_path)
        assert ids_out == ids_in
        assert dim == 16
        assert embs_out.shape == (8, 16)
        # 再構築されたベクトルは正規化済み（faiss IP index なので元と同一）
        import numpy as np
        assert np.allclose(embs_out, embs, atol=1e-5)

    def test_missing_files_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            migrate_mod._load_faiss_index(tmp_path)

    def test_corrupted_id_map_raises(self, tmp_path):
        store = FaissVectorStore(data_dir=tmp_path, dim=8)
        embs = _random_embeddings(3, dim=8)
        store.rebuild(db_ids=[1, 2, 3], embeddings=embs)
        store.save()
        # id_map を意図的に短くする
        (tmp_path / "semantic_map.json").write_text(json.dumps([1, 2]), "utf-8")
        with pytest.raises(ValueError, match="refusing to migrate"):
            migrate_mod._load_faiss_index(tmp_path)
