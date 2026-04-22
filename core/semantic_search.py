"""
セマンティック記憶検索エンジン（機能⑧）
二段階アーキテクチャ:

Tier 1 (常時有効): TF-IDF 風スコアリング（純粋 Python、追加インストール不要）
Tier 2 (オプション): sentence-transformers + VectorStore ベクトル検索
  インストール: pip install sentence-transformers faiss-cpu

**M9 Phase 1 (2026-04-21)**: VectorStore Protocol 抽象化を導入。
既存動作は完全に保持（default backend=faiss）。`settings.semantic_search.backend`
を `"sqlite-vec"` に変更すると sqlite-vec にルーティング（実験的）。
"""
from __future__ import annotations
import json
import logging
import math
import re
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.memory import MemoryManager
    from core.vector_store import VectorStore

# Tier 2 オプション依存
try:
    from sentence_transformers import SentenceTransformer
    import faiss  # noqa: F401 — availability probe
    import numpy as np
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False


# ────────────────────────────────────────────────────────────────
# Tier 1: TF-IDF 風キーワードスコアリング（スタンドアローン）
# ────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """簡易トークン化（日本語は1文字 bigram、英語は単語分割）"""
    tokens = []
    # 英数字の単語
    for w in re.findall(r'[a-zA-Z0-9]{2,}', text.lower()):
        tokens.append(w)
    # 日本語 bigram
    jp_chars = re.findall(r'[\u3040-\u9FFF]', text)
    for i in range(len(jp_chars) - 1):
        tokens.append(jp_chars[i] + jp_chars[i + 1])
    # 単文字漢字もフォールバックとして追加
    tokens.extend(jp_chars)
    return tokens


def tfidf_score(query: str, doc: str) -> float:
    """クエリとドキュメントの TF-IDF 風類似度（0.0 〜 1.0）"""
    q_tokens = set(_tokenize(query))
    d_tokens = _tokenize(doc)
    if not q_tokens or not d_tokens:
        return 0.0
    d_freq = {}
    for t in d_tokens:
        d_freq[t] = d_freq.get(t, 0) + 1
    score = sum(d_freq.get(t, 0) for t in q_tokens)
    return min(score / (len(d_tokens) + 1), 1.0)


def keyword_search(query: str, memories: list, limit: int = 5) -> list:
    """
    Tier 1: TF-IDF スコアでメモリリストをソートして返す。
    memories: MemoryManager から取得した Memory オブジェクトのリスト
    """
    scored = []
    for mem in memories:
        score = tfidf_score(query, mem.content)
        if score > 0:
            scored.append((score, mem))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]]


# ────────────────────────────────────────────────────────────────
# Tier 2: ベクトル検索エンジン（sentence-transformers + VectorStore）
# ────────────────────────────────────────────────────────────────

# 軽量な多言語モデル（日本語対応、~100MB）
_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class SemanticSearchEngine:
    """
    sentence-transformers + VectorStore による高精度ベクトル検索。
    利用可能な場合のみ有効化。未インストールでも安全に動作（Tier 1 にフォールバック）。

    M9 Phase 1: backend 切替可能 (``backend="faiss"`` or ``"sqlite-vec"``)。
    """

    def __init__(
        self,
        data_dir: Path,
        model_name: str = _DEFAULT_MODEL,
        backend: str = "faiss",
    ):
        self.data_dir = Path(data_dir)
        self._model_name = model_name
        self._backend_name = backend
        self._model = None
        self._store: "VectorStore | None" = None
        self._loaded = False

    def load(self) -> bool:
        """モデルとインデックスを読み込む（時間がかかる場合あり）"""
        if not SEMANTIC_AVAILABLE:
            return False
        try:
            import numpy as np
            from core.vector_store import make_vector_store

            logger.info("[Semantic] モデルを読み込み中: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            self._loaded = True

            # 次元推定: まず trivial encode で次元取得
            probe = self._model.encode(["probe"], show_progress_bar=False)
            dim = int(probe.shape[1])
            self._store = make_vector_store(
                backend=self._backend_name,
                data_dir=self.data_dir,
                dim=dim,
            )
            try:
                self._store.load()
            except Exception as exc:
                logger.warning("[Semantic] インデックス load 失敗: %s", exc)

            actual_backend = getattr(self._store, "backend_name", "?")
            logger.info(
                "[Semantic] ✓ セマンティック検索エンジン準備完了 (backend=%s)",
                actual_backend,
            )
            return True
        except Exception as e:
            logger.warning("[Semantic] 読み込みエラー: %s", e)
            return False

    def is_ready(self) -> bool:
        return self._loaded and self._model is not None and self._store is not None

    @property
    def backend_name(self) -> str:
        """現在利用中のベクトルストア backend 名（fallback 後を反映）。"""
        if self._store is not None:
            return getattr(self._store, "backend_name", self._backend_name)
        return self._backend_name

    # ─── インデックス管理 ────────────────────────────────────────

    def rebuild_index(self, memories: list):
        """
        全記憶のベクトルインデックスを再構築する。
        memories: MemoryManager の全記憶リスト
        """
        if not self.is_ready() or not memories:
            return

        import numpy as np
        texts = [m.content[:512] for m in memories]
        db_ids = [m.id for m in memories]

        logger.info("[Semantic] %d 件のインデックスを構築中...", len(texts))
        embeddings = self._model.encode(texts, show_progress_bar=False)
        embeddings = embeddings.astype(np.float32)
        # cosine 類似度のため L2 正規化（FAISS IP と sqlite-vec cosine 両方で正）
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings = embeddings / norms

        if self._store is None:
            return
        self._store.rebuild(db_ids=db_ids, embeddings=embeddings)
        self._store.save()
        logger.info("[Semantic] ✓ インデックス構築完了")

    def add_memory(self, memory):
        """新しい記憶をインデックスに追加する（インクリメンタル更新）"""
        if not self.is_ready():
            return
        import numpy as np

        embedding = self._model.encode([memory.content[:512]])
        embedding = embedding.astype(np.float32)
        norm = float(np.linalg.norm(embedding))
        if norm > 0:
            embedding = embedding / norm

        if self._store is None:
            return
        self._store.add(db_id=int(memory.id), embedding=embedding)
        self._store.save()

    # ─── 検索 ────────────────────────────────────────────────────

    def search(self, query: str, memories: list, limit: int = 5) -> list:
        """
        クエリに意味的に近い記憶を返す。
        セマンティックエンジンが利用不可の場合は Tier 1 にフォールバック。
        memories: MemoryManager の全記憶リスト（フィルタリング用）
        """
        if not self.is_ready() or self._store is None or self._store.count() == 0:
            return keyword_search(query, memories, limit)

        try:
            import numpy as np
            q_emb = self._model.encode([query[:512]])
            q_emb = q_emb.astype(np.float32)
            norm = float(np.linalg.norm(q_emb))
            if norm > 0:
                q_emb = q_emb / norm

            k = min(limit * 3, self._store.count())
            ids, _scores = self._store.search(q_emb, k)

            # DB id → Memory のマッピング
            id_to_mem = {m.id: m for m in memories if m.id is not None}
            results = []
            for db_id in ids:
                if db_id in id_to_mem:
                    results.append(id_to_mem[db_id])
                if len(results) >= limit:
                    break
            return results if results else keyword_search(query, memories, limit)

        except Exception as e:
            logger.warning("[Semantic] 検索エラー: %s", e)
            return keyword_search(query, memories, limit)
