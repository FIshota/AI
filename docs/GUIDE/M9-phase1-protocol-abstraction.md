# M9 Phase 1 — VectorStore Protocol 抽象化

**日付**: 2026-04-21
**スコープ**: faiss-cpu → sqlite-vec 移行のための抽象化レイヤを先行実装。既存動作を完全保持したまま、バックエンドをランタイム切替可能にする。
**判定**: ✅ Phase 1 完了（14 tests passed / 1 skipped / 986 regression tests passed）

## 背景

`core/semantic_search.py` には FAISS (`IndexFlatIP` + `normalize_L2` + `faiss.read_index`/`write_index`) の呼び出しが直接インラインされており、
バックエンド切替は不可能だった。M9 の最終ゴール（sqlite-vec 採用による「1 プロセス / 1 DB」化）には
まず抽象化が必要。sqlite-vec v0.2 GA を待つ間、リスクゼロで実施可能なのがこの Phase 1。

## 実装範囲

| レイヤ | 新設/変更 | 役割 |
|---|---|---|
| `core/vector_store.py` | 新設 (~310 行) | `VectorStore` Protocol + `FaissVectorStore` (identity refactor) + `SQLiteVecVectorStore` (opt-in) + `make_vector_store()` factory |
| `utils/sqlite_vec_support.py` | 新設 (~100 行) | 環境プローブ: `enable_load_extension` の有無・`sqlite_vec` パッケージ有無・SQLite バージョン・hints を返す pure function |
| `core/semantic_search.py` | refactor | FAISS 直呼びを廃止し `VectorStore` 経由に統一。L2 正規化は numpy 側へ移設。`backend_name` プロパティ追加 |
| `core/ai_chan.py` | 配線 | `settings.semantic_search.backend` を `SemanticSearchEngine(backend=...)` に渡す |
| `config/settings.json.example` | +3 行 | `"semantic_search": {"enabled": true, "backend": "faiss"}` (default は既存挙動を保持) |
| `tests/test_vector_store.py` | 新設 (~190 行) | Protocol 準拠 / FAISS 往復 / sqlite-vec probe / factory fallback を網羅 |

## アーキテクチャ

```
                     ┌─────────────────────────┐
                     │ SemanticSearchEngine     │
                     │  (model + index bridge)  │
                     └───────────┬──────────────┘
                                 │ VectorStore Protocol
                                 │ (load / rebuild / add /
                                 │  search / count / save / close)
                                 ▼
                   ┌──────────────────────────┐
                   │ make_vector_store(backend)│
                   └──┬───────────────────────┘
                      │
      ┌───────────────┴────────────────┐
      │                                │
      ▼                                ▼
FaissVectorStore            SQLiteVecVectorStore
  semantic_index.bin          semantic_vec.db
  semantic_map.json           (vec_items + id_map)
  (既存ファイル継続)          (opt-in, 未採用時は
                               SQLiteVecUnavailable)
```

## 互換性保証

- **ファイルフォーマット**: `FaissVectorStore` は `semantic_index.bin` + `semantic_map.json` の名称・内容ともに変更なし（既存ユーザのインデックスはそのまま使える）。
- **default backend = "faiss"**: 設定未指定ユーザの挙動は 100% 従来通り。
- **Graceful fallback**: `backend="sqlite-vec"` 指定でも env が非対応（`enable_load_extension=False` など）なら warning ログを出して FAISS にフォールバック。
- **検索結果の同値性**: FAISS IP 類似度と sqlite-vec cosine 距離は `1.0 - distance` 変換で揃え、スコア方向 (高=近) を統一。

## 環境プローブ (`check_sqlite_vec_support`)

返すレポート:
- `usable`: bool — 両条件 AND
- `has_enable_load_extension`: bool — `sqlite3.Connection.enable_load_extension` が呼べるか
- `sqlite_vec_installed`: bool — `import sqlite_vec` 成功
- `sqlite_version`: str
- `sqlite_vec_version`: str | None
- `error`: str | None
- `hints`: tuple[str, ...] — "python.org バイナリは `--enable-loadable-sqlite-extensions` 無効。pyenv + `PYTHON_CONFIGURE_OPTS` で再ビルド推奨" など

**ローカル Intel Mac (Py3.9, python.org)**: `enable_load_extension` が `False` のため sqlite-vec 不可 → factory fallback 経路で faiss 継続。期待通り。

## Opt-in 手順

1. Python を `--enable-loadable-sqlite-extensions` 付きでビルド（pyenv 推奨）
2. `pip install sqlite-vec`
3. `config/settings.json` の `semantic_search.backend` を `"sqlite-vec"` に変更
4. 次回起動で自動的に `semantic_vec.db` が作られ、既存 `semantic_index.bin` は残置（migrate は Phase 2 で提供予定）

## テスト結果

```
tests/test_vector_store.py
  TestProtocolConformance           2 passed
  TestFaissVectorStore              5 passed
  TestSQLiteVecSupportProbe         2 passed
  TestSQLiteVecVectorStore          1 passed, 1 skipped (env 非対応)
  TestMakeVectorStore               3 passed
  → 14 passed, 1 skipped

Full regression:
  986 passed, 3 skipped, 0 failed (28s)
```

## 既知の未対応 (Phase 2 / Phase 3 へ)

- **Migration**: ✅ Phase 2 で `scripts/migrate_faiss_to_sqlite_vec.py` 追加（`--dry-run` / `--force` / `--verify` オプション。sqlite-vec env プローブ → FAISS 読み込み → vec0 書き込み → サンプル比較 verify）。既存 FAISS ファイルは削除しないのでロールバック可能。
- **UI**: ✅ Phase 2 で `settings_window.py` に backend OptionMenu（faiss / sqlite-vec）を追加。
- **Benchmark**: 1 万件規模で FAISS vs sqlite-vec の search レイテンシ計測と判定レポート（sqlite-vec 実行環境が必要）。
- **sqlite-vec v0.2 GA 追従**: API 安定化後に default backend を切替検討。

## Phase 2 成果物まとめ (2026-04-21)

| 種別 | ファイル | 内容 |
|---|---|---|
| script | `scripts/migrate_faiss_to_sqlite_vec.py` | FAISS → sqlite-vec ワンショット移行 + verify |
| test | `tests/test_migrate_faiss_to_sqlite_vec.py` | FAISS 読み込みロジック 3 tests |
| ui | `ui/settings_window.py` | backend OptionMenu + load/save wiring |

**Regression**: 989 passed / 3 skipped / 0 failed（28s）

## 参考

- [02-risk-matrix.md] M9 行
- [03-action-matrix.md] M9 行（Phase 1 完了状態を反映）
- `core/vector_store.py` docstring — 設計意図と file-format invariant
