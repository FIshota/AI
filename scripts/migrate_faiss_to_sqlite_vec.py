#!/usr/bin/env python3
"""M9 Phase 2: FAISS → sqlite-vec ワンショット移行スクリプト。

既存の ``semantic_index.bin`` + ``semantic_map.json`` を読み込み、
``semantic_vec.db`` (vec0 virtual table + id_map) に複製する。

使い方:
    python3 scripts/migrate_faiss_to_sqlite_vec.py --data-dir data/
    python3 scripts/migrate_faiss_to_sqlite_vec.py --data-dir data/ --dry-run
    python3 scripts/migrate_faiss_to_sqlite_vec.py --data-dir data/ --verify

前提条件:
    - Python が ``--enable-loadable-sqlite-extensions`` 付きでビルドされていること
    - ``pip install sqlite-vec`` 済み
    - 既存の FAISS index (``semantic_index.bin``) が ``data-dir`` 下にあること

安全性:
    - 既存の FAISS ファイルは削除しない（rollback 可能）
    - ``semantic_vec.db`` が既に存在する場合はデフォルトで abort（``--force`` で上書き）
    - ``--verify`` で移行後に count / 任意クエリを両 backend で比較
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root を sys.path に追加（スクリプト直接実行のため）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_faiss_index(data_dir: Path):
    """FAISS index + id_map を読み込み、(ids, embeddings, dim) を返す。"""
    import faiss  # type: ignore[import-not-found]
    import numpy as np

    index_path = data_dir / "semantic_index.bin"
    map_path = data_dir / "semantic_map.json"
    if not index_path.exists() or not map_path.exists():
        raise FileNotFoundError(
            f"FAISS index not found under {data_dir} "
            f"({index_path.name} and/or {map_path.name} missing)"
        )

    index = faiss.read_index(str(index_path))
    id_map = json.loads(map_path.read_text("utf-8"))
    n = int(index.ntotal)
    dim = int(index.d)
    if n != len(id_map):
        raise ValueError(
            f"FAISS ntotal={n} but id_map has {len(id_map)} entries — "
            f"refusing to migrate a corrupted index"
        )
    embs = np.zeros((n, dim), dtype="float32")
    for i in range(n):
        embs[i] = index.reconstruct(i)
    return id_map, embs, dim


def _verify(data_dir: Path, sample_k: int = 5) -> bool:
    """Verify FAISS と sqlite-vec が同一の top-1 を返すかサンプリングチェック。"""
    from core.vector_store import FaissVectorStore, SQLiteVecVectorStore
    import numpy as np

    faiss_store = FaissVectorStore(data_dir=data_dir)
    faiss_store.load()
    if faiss_store.count() == 0:
        print("[verify] FAISS index is empty — nothing to verify", flush=True)
        return True

    try:
        sv_store = SQLiteVecVectorStore(
            data_dir=data_dir, dim=faiss_store._index.d  # type: ignore[union-attr]
        )
    except Exception as exc:
        print(f"[verify] sqlite-vec unavailable: {exc}", flush=True)
        return False
    sv_store.load()
    if sv_store.count() != faiss_store.count():
        print(
            f"[verify] ✗ count mismatch: faiss={faiss_store.count()} "
            f"sqlite-vec={sv_store.count()}",
            flush=True,
        )
        return False

    # サンプル top-1 が一致するかチェック
    n = faiss_store.count()
    sample_indices = np.linspace(0, n - 1, min(sample_k, n), dtype=int)
    mismatches = 0
    for i in sample_indices:
        q = faiss_store._index.reconstruct(int(i)).reshape(1, -1)  # type: ignore[union-attr]
        f_ids, _ = faiss_store.search(q, k=1)
        s_ids, _ = sv_store.search(q, k=1)
        if not f_ids or not s_ids or f_ids[0] != s_ids[0]:
            print(
                f"[verify] ! sample {i}: faiss={f_ids} sqlite-vec={s_ids}",
                flush=True,
            )
            mismatches += 1
    sv_store.close()
    if mismatches == 0:
        print(f"[verify] ✓ {len(sample_indices)} samples all matched", flush=True)
        return True
    print(f"[verify] ✗ {mismatches}/{len(sample_indices)} mismatches", flush=True)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, required=True, help="semantic_index.bin を含むディレクトリ")
    ap.add_argument("--dry-run", action="store_true", help="読み込みのみ、書き込まない")
    ap.add_argument("--force", action="store_true", help="既存の semantic_vec.db を上書き")
    ap.add_argument("--verify", action="store_true", help="移行後にサンプル比較")
    args = ap.parse_args()

    data_dir: Path = args.data_dir
    if not data_dir.exists():
        print(f"[migrate] data-dir が存在しません: {data_dir}", flush=True)
        return 2

    # Phase 1: env probe
    from utils.sqlite_vec_support import check_sqlite_vec_support

    report = check_sqlite_vec_support()
    if not report.usable:
        print(
            "[migrate] sqlite-vec が利用できません:\n"
            f"  error: {report.error}\n"
            f"  hints: {report.hints}",
            flush=True,
        )
        return 3

    print(f"[migrate] sqlite-vec OK (sqlite={report.sqlite_version}, vec={report.sqlite_vec_version})", flush=True)

    # Phase 2: FAISS 読み込み
    try:
        ids, embs, dim = _load_faiss_index(data_dir)
    except Exception as exc:
        print(f"[migrate] FAISS 読み込み失敗: {exc}", flush=True)
        return 4
    print(f"[migrate] FAISS index を読み込み: n={len(ids)} dim={dim}", flush=True)

    if args.dry_run:
        print("[migrate] --dry-run 指定のため、ここで終了します", flush=True)
        return 0

    # Phase 3: sqlite-vec 書き込み
    from core.vector_store import SQLiteVecUnavailable, SQLiteVecVectorStore

    db_path = data_dir / "semantic_vec.db"
    if db_path.exists() and not args.force:
        print(
            f"[migrate] {db_path} が既に存在します。--force を付けて再実行してください。",
            flush=True,
        )
        return 5
    if db_path.exists() and args.force:
        db_path.unlink()
        print(f"[migrate] 既存の {db_path.name} を削除しました", flush=True)

    try:
        store = SQLiteVecVectorStore(data_dir=data_dir, dim=dim)
    except SQLiteVecUnavailable as exc:
        print(f"[migrate] SQLiteVecVectorStore 構築失敗: {exc}", flush=True)
        return 6

    store.load()
    store.rebuild(db_ids=ids, embeddings=embs)
    store.save()
    store.close()
    print(f"[migrate] ✓ {db_path} へ {len(ids)} 件を書き込みました", flush=True)

    # Phase 4: verify
    if args.verify:
        ok = _verify(data_dir)
        if not ok:
            print("[migrate] verify 失敗 — ロールバック推奨", flush=True)
            return 7

    print("[migrate] 完了。settings.json の semantic_search.backend を 'sqlite-vec' に変更してください。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
