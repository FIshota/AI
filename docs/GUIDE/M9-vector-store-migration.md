# M9: faiss-cpu → sqlite-vec 移行検証レポート

**作成日**: 2026-04-21
**ステータス**: Go / No-Go 判定レポート（実装未着手）
**判定**: **🟡 Conditional Go（Phase 1 リリース後、sqlite-vec v0.2 GA 到達を待って着手）**

---

## 1. 目的 (Why)

faiss-cpu は現状の意味検索 (semantic search) の中核依存だが、以下のリスクがある：

1. **Intel Mac 継続サポートの不確実性**: faiss-cpu のビルドは複雑で、Python バージョン更新時に wheel 提供が遅れるケースが過去にあった（特に arm64 対応は当初遅かった）。ai-chan は Intel Mac 対応を謳っているため、将来 wheel が提供されないと詰む。
2. **インストールサイズ**: faiss は 50–500MB と大きい。ai-chan は「家族 AI」として配布容易性を重視している。
3. **依存の重さ**: `import faiss` は numpy/scipy 風の heavy load があり、コールドスタート時間に影響。

**一方で**、ai-chan の実使用パターン（単一ユーザー、数百〜数千件の memory、`IndexFlatIP` のみ利用 = 厳密検索のみ、ANN 不使用）は sqlite-vec のスイートスポットに完全一致する。

## 2. 現状調査

### 2.1 FAISS の使用箇所

| ファイル | 行 | 用途 |
|---|---|---|
| `core/semantic_search.py` | 25, 126, 149–150, 156, 170, 174, 180, 200 | 本体実装（Tier 2 オプション） |
| `requirements.txt` | 16 | `faiss-cpu>=1.9.0` 宣言 |
| `requirements.lock` | 609, 1592, 1615 | pin=1.13.2 |
| `.github/workflows/ci.yml` | 60 | **CI ではスキップ**（重いため） |
| `ui/settings_window.py` | 485 | UI の install 案内テキスト |
| `docs/LICENSES.md` | 35 | MIT ライセンス表記 |
| `docs/GUIDE/02-expert-reviews.md` | 140, 168, 178 | 既に「sqlite-vec 移行」候補と記載 |

### 2.2 API 表面積（移行対象）

`core/semantic_search.py` の `SemanticSearchEngine` クラスで faiss API を使っているのは **実質 6 箇所のみ**：

| 現行 (faiss) | 用途 |
|---|---|
| `faiss.read_index(path)` | 起動時のインデックス読み込み |
| `faiss.IndexFlatIP(dim)` | 新規インデックス作成（内積 = cosine） |
| `faiss.normalize_L2(embeddings)` | L2 正規化（in-place） |
| `index.add(embeddings)` | ベクトル追加 |
| `faiss.write_index(index, path)` | 保存 |
| `index.search(q_emb, k)` | KNN 検索 → `(scores, indices)` |

**全て厳密検索**（IVF/HNSW/PQ などの ANN は未使用）。

### 2.3 データスケール

- 単一ユーザー（家族 AI）
- memory 件数は現実的には 数千件（長期運用でも 1 万件未満想定）
- 次元: sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` = **384 次元**
- embedding 永続化: `semantic_index.bin` + `semantic_map.json`（data_dir 配下）
- Tier 2 は **try/except import で optional**、failback に TF-IDF Tier 1 あり

## 3. sqlite-vec との比較

### 3.1 メタ情報

| 項目 | faiss-cpu | sqlite-vec |
|---|---|---|
| 現行バージョン | 1.13.2（2026-04 時点 stable） | 0.1.9（**pre-v1**, 2026-03-31） |
| ライセンス | MIT | MIT / Apache 2.0 dual |
| 言語 | C++ | **pure C（依存なし）** |
| wheel (macOS x86_64) | ○（但し遅れがち） | ○（131 KB） |
| wheel (macOS arm64) | ○ | ○（165 KB） |
| wheel (Linux x86_64) | ○ | ○ |
| wheel (Linux arm64) | ○ | ○ |
| wheel (Windows) | ○ | ○（293 KB） |
| **インストールサイズ** | **50–500 MB** | **131–293 KB** |
| Python バージョン追従 | 遅延あり | Py3 全般 |
| SQLite 拡張機能 | ― | **loadable extension**（`enable_load_extension=True` が必要） |

### 3.2 API マッピング

| 操作 | faiss | sqlite-vec（virtual table `vec0`） |
|---|---|---|
| インデックス作成 | `IndexFlatIP(dim)` | `CREATE VIRTUAL TABLE vec USING vec0(embedding float[384])` |
| 追加 | `index.add(emb)` | `INSERT INTO vec(rowid, embedding) VALUES (?, ?)` |
| 検索 | `index.search(q, k)` | `SELECT rowid, distance FROM vec WHERE embedding MATCH ? ORDER BY distance LIMIT k` |
| L2 正規化 | `faiss.normalize_L2()` | 自前（numpy または sqlite-vec 側の cosine 距離型指定） |
| 永続化 | `read_index` / `write_index` | **自動**（SQLite ファイル内に常駐） |
| 型 | float32 | float32 / int8 / binary（量子化選択可） |

**注目点**: sqlite-vec は永続化が自動（`semantic_index.bin` と `semantic_map.json` の 2 ファイル運用が 1 DB に統合できる）。既存の `memory.db` に同居させれば管理も楽になる。

### 3.3 パフォーマンス（SIFT1M ベンチ、k=20）

| 指標 | faiss | sqlite-vec | 判定 |
|---|---|---|---|
| build 時間（100 万件） | 126 ms | 1 ms | **sqlite-vec 勝ち** |
| query 時間 | 10 ms | 17 ms | faiss 70% 速い（絶対値は誤差） |
| write 時間（増分） | 47,640 ms | 788 ms | **sqlite-vec 60 倍高速** |

**ai-chan のスケール（数千件）で 10 ms vs 17 ms は実質同等**。むしろ `add_memory()` が頻繁に呼ばれる ai-chan では write 性能の優位が効く。

出典: [sitepoint.com – Local-First RAG: Vector Search in SQLite](https://www.sitepoint.com/local-first-rag-vector-search-in-sqlite-with-hamming-distance/)

## 4. リスクと懸念

### 🔴 ブロッキングリスク
- **`sqlite-vec` は pre-v1（0.1.9）**: breaking change の可能性あり。v1.0 GA 未達成。  
  → **緩和策**: pin を `sqlite-vec==0.1.9` に strict 固定し、アップデート時は手動検証必須。

### 🟡 中リスク
- **`enable_load_extension`**: Python の `sqlite3` モジュールは、ビルド時に `--enable-loadable-sqlite-extensions` で有効化が必要。
  - macOS homebrew の python: ✅ 有効
  - 公式 python.org 配布: ❌ **無効**（大きな互換性問題）
  - pyenv: インストール時オプション依存
  - → **緩和策**: `apsw` (Another Python SQLite Wrapper) 経由で load すれば回避可能、ただし依存追加。
- **既存インデックスからの migration**: 既存ユーザーの `semantic_index.bin` を捨てて再構築させる必要あり。初回起動時の embedding 再計算に時間がかかる（数千件 × 数百 ms = 数分〜十数分）。

### 🟢 低リスク
- API 表面積が 6 個と小さく、置換工数が軽い
- Tier 1（TF-IDF）フォールバックがあるので、Tier 2 が壊れても致命的ではない
- CI ではそもそもスキップしているため CI 影響はゼロ

## 5. 移行工数見積

| Phase | 内容 | 見積 |
|---|---|---|
| 1. 抽象化 | `core/semantic_search.py` に `VectorStore` Protocol を導入、faiss 実装を `FaissVectorStore` に隔離 | 4h |
| 2. sqlite-vec 実装 | `SQLiteVecVectorStore` を追加、settings で切替可能に | 8h |
| 3. migration スクリプト | 既存 `semantic_index.bin` → sqlite-vec 再構築（embedding 再計算） | 4h |
| 4. テスト | `tests/test_semantic_search.py` に両バックエンド並行テスト追加 | 4h |
| 5. ドキュメント/UI | settings_window, LICENSES, expert-reviews 更新 | 2h |
| 6. 段階ロールアウト | default=faiss, opt-in=sqlite-vec → 1 リリース観察 → default 切替 | （期間）2 週 |

**合計工数**: 約 **22 時間**（1 週間の余裕を持ったペース）  
action-matrix.md の「M9: 30h / 1w」見積と整合。

## 6. 判定: 🟡 Conditional Go

### Go とする根拠
1. ai-chan の使用スケール（単一ユーザー、数千件、厳密検索）は sqlite-vec のスイートスポット
2. インストールサイズ 100–2000 倍削減（50MB → 165KB）は配布性で明確な勝ち
3. write 性能で 60 倍優位、read 性能は実用上同等
4. API 表面積が狭く、`VectorStore` 抽象化で安全に段階移行できる
5. docs/GUIDE/02-expert-reviews.md で既に移行候補として記載済み（技術方針と整合）

### Conditional（条件付き）の理由
1. **sqlite-vec v0.2 GA（または実質的な stable）到達を待つ**: 現行 pre-v1 は本番投入に慎重を要する。2026 年内の GA 到達を予想。
2. **`enable_load_extension` 非対応環境への対応方針を先に決める**: `apsw` 依存追加 vs 公式 python.org ユーザー切捨て vs homebrew 推奨ガイド追記 — 判断が必要。
3. **Phase 1 リリース（本ハードニングラウンド終了）後に着手**: 現在進行中の M1–M12 を完了し、944 passed ベースラインが安定してから。

### No-Go ではない理由
以下のどれかが真なら No-Go だが、いずれも該当しない：
- ANN（IVF/HNSW）必須 → **NG: 未使用**
- 100 万件以上のベクトル → **NG: 数千件規模**
- 共有知識ベース（マルチユーザー） → **NG: 単一ユーザー家族 AI**
- 1ms 以下のレイテンシ要件 → **NG: 会話レスポンス全体で数百 ms 許容**

## 7. 次のアクション

1. ✅ **本レポートを docs/GUIDE/M9-vector-store-migration.md に保存**（完了）
2. ⏸ **待機**: sqlite-vec v0.2 GA（または 6 か月安定運用の確認）
3. ⏸ **Phase 1 完了後、M9-impl として別 issue 化**:
   - sub-task: `enable_load_extension` 検出ユーティリティ追加
   - sub-task: `VectorStore` Protocol 抽象化（先行着手可能、依存なし）
   - sub-task: `SQLiteVecVectorStore` 実装
   - sub-task: migration CLI (`scripts/migrate_faiss_to_sqlite_vec.py`)

**先行着手可能（リスクゼロの準備作業）**: `VectorStore` Protocol の抽象化は今すぐやっても既存動作に影響しないため、M9 判定の見返り待ちの間に進めてもよい。ただし本ハードニングラウンドの範囲外。

## 参考資料

- [sqlite-vec GitHub (asg017/sqlite-vec)](https://github.com/asg017/sqlite-vec)
- [sqlite-vec PyPI](https://pypi.org/project/sqlite-vec/)
- [Alex Garcia – sqlite-vec v0.1.0 introduction](https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html)
- [Local-First RAG: Vector Search in SQLite with Hamming Distance (SitePoint)](https://www.sitepoint.com/local-first-rag-vector-search-in-sqlite-with-hamming-distance/)
- [Best Vector Databases in 2026 (Firecrawl)](https://www.firecrawl.dev/blog/best-vector-databases)
- `docs/GUIDE/02-expert-reviews.md` §ST3 – 既存の方針文書
- `docs/GUIDE/03-action-matrix.md` M9 行
