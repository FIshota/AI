"""
セマンティック記憶検索エンジン（機能⑧）
二段階アーキテクチャ:

Tier 1 (常時有効): TF-IDF 風スコアリング（純粋 Python、追加インストール不要）
Tier 2 (オプション): sentence-transformers + FAISS ベクトル検索
  インストール: pip install sentence-transformers faiss-cpu

sentence-transformers が利用可能な場合は Tier 2 が自動的に使われます。
"""
from __future__ import annotations
import json
import math
import re
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory import MemoryManager

# Tier 2 オプション依存
try:
    from sentence_transformers import SentenceTransformer
    import faiss
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
# Tier 2: ベクトル検索エンジン（sentence-transformers + FAISS）
# ────────────────────────────────────────────────────────────────

# 軽量な多言語モデル（日本語対応、~100MB）
_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


class SemanticSearchEngine:
    """
    sentence-transformers + FAISS による高精度ベクトル検索。
    利用可能な場合のみ有効化。未インストールでも安全に動作（Tier 1 にフォールバック）。
    """

    def __init__(self, data_dir: Path, model_name: str = _DEFAULT_MODEL):
        self.data_dir   = Path(data_dir)
        self._index_path  = self.data_dir / "semantic_index.bin"
        self._map_path    = self.data_dir / "semantic_map.json"
        self._model_name  = model_name
        self._model       = None
        self._index       = None          # FAISS index
        self._id_map: list[int] = []      # FAISS 順位 → DB id のマッピング
        self._loaded      = False

    def load(self) -> bool:
        """モデルとインデックスを読み込む（時間がかかる場合あり）"""
        if not SEMANTIC_AVAILABLE:
            return False
        try:
            import numpy as np
            print(f"[Semantic] モデルを読み込み中: {self._model_name}", flush=True)
            self._model  = SentenceTransformer(self._model_name)
            self._loaded = True
            self._load_index()
            print("[Semantic] ✓ セマンティック検索エンジン準備完了", flush=True)
            return True
        except Exception as e:
            print(f"[Semantic] 読み込みエラー: {e}", flush=True)
            return False

    def is_ready(self) -> bool:
        return self._loaded and self._model is not None

    # ─── インデックス管理 ────────────────────────────────────────

    def _load_index(self):
        if self._index_path.exists() and self._map_path.exists():
            try:
                self._index  = faiss.read_index(str(self._index_path))
                self._id_map = json.loads(self._map_path.read_text("utf-8"))
            except Exception:
                self._index  = None
                self._id_map = []

    def rebuild_index(self, memories: list):
        """
        全記憶のベクトルインデックスを再構築する。
        memories: MemoryManager の全記憶リスト
        """
        if not self.is_ready() or not memories:
            return

        import numpy as np
        texts   = [m.content[:512] for m in memories]
        db_ids  = [m.id for m in memories]

        print(f"[Semantic] {len(texts)} 件のインデックスを構築中...", flush=True)
        embeddings = self._model.encode(texts, show_progress_bar=False)
        embeddings = embeddings.astype(np.float32)

        dim   = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)   # 内積（コサイン類似度に相当）
        faiss.normalize_L2(embeddings)
        index.add(embeddings)

        self._index  = index
        self._id_map = db_ids

        faiss.write_index(index, str(self._index_path))
        self._map_path.write_text(
            json.dumps(db_ids, ensure_ascii=False), "utf-8"
        )
        print(f"[Semantic] ✓ インデックス構築完了", flush=True)

    def add_memory(self, memory):
        """新しい記憶をインデックスに追加する（インクリメンタル更新）"""
        if not self.is_ready():
            return
        import numpy as np

        embedding = self._model.encode([memory.content[:512]])
        embedding = embedding.astype(np.float32)
        faiss.normalize_L2(embedding)

        if self._index is None:
            dim = embedding.shape[1]
            self._index = faiss.IndexFlatIP(dim)

        self._index.add(embedding)
        self._id_map.append(memory.id)

        # インデックスを保存
        faiss.write_index(self._index, str(self._index_path))
        self._map_path.write_text(
            json.dumps(self._id_map, ensure_ascii=False), "utf-8"
        )

    # ─── 検索 ────────────────────────────────────────────────────

    def search(self, query: str, memories: list, limit: int = 5) -> list:
        """
        クエリに意味的に近い記憶を返す。
        セマンティックエンジンが利用不可の場合は Tier 1 にフォールバック。
        memories: MemoryManager の全記憶リスト（フィルタリング用）
        """
        if not self.is_ready() or self._index is None or self._index.ntotal == 0:
            return keyword_search(query, memories, limit)

        try:
            import numpy as np
            q_emb = self._model.encode([query[:512]])
            q_emb = q_emb.astype(np.float32)
            faiss.normalize_L2(q_emb)

            k = min(limit * 3, self._index.ntotal)
            scores, indices = self._index.search(q_emb, k)

            # DB id → Memory のマッピング
            id_to_mem = {m.id: m for m in memories if m.id is not None}
            results = []
            for idx, score in zip(indices[0], scores[0]):
                if idx < 0 or idx >= len(self._id_map):
                    continue
                db_id = self._id_map[idx]
                if db_id in id_to_mem:
                    results.append(id_to_mem[db_id])
                if len(results) >= limit:
                    break
            return results if results else keyword_search(query, memories, limit)

        except Exception as e:
            print(f"[Semantic] 検索エラー: {e}", flush=True)
            return keyword_search(query, memories, limit)
