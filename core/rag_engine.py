"""
RAG エンジン (Retrieval-Augmented Generation)
Sprint 3.0-B: ローカルドキュメントを読み込み、質問に正確に回答する。

対応形式: .txt, .md, .pdf, .json, .csv
ドキュメントをチャンクに分割し、セマンティック検索で関連箇所を引用。
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.semantic_search import SemanticSearchEngine

# チャンク設定
CHUNK_SIZE = 400       # 文字数
CHUNK_OVERLAP = 80     # オーバーラップ文字数
MAX_CHUNKS_PER_DOC = 200


def _split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """テキストを重複付きチャンクに分割する"""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
        if len(chunks) >= MAX_CHUNKS_PER_DOC:
            break
    return chunks


def _read_text_file(path: Path) -> str:
    """テキストファイルを読み込む"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="shift_jis")
        except Exception:
            return ""


def _read_pdf(path: Path) -> str:
    """PDFからテキストを抽出する（PyMuPDFまたはフォールバック）"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages)
    except ImportError:
        pass
    # フォールバック: pdfminer
    try:
        from pdfminer.high_level import extract_text
        return extract_text(str(path))
    except ImportError:
        return f"[PDF読み込み不可: pip install PyMuPDF が必要です]"
    except Exception:
        return ""


class DocumentChunk:
    """ドキュメントの1チャンク"""
    __slots__ = ("doc_id", "doc_name", "chunk_idx", "text", "embedding")

    def __init__(self, doc_id: str, doc_name: str, chunk_idx: int, text: str):
        self.doc_id = doc_id
        self.doc_name = doc_name
        self.chunk_idx = chunk_idx
        self.text = text
        self.embedding = None


class RAGEngine:
    """
    ローカルドキュメントの RAG 検索エンジン。

    使い方:
      rag.add_document("/path/to/file.txt")
      results = rag.search("質問文", limit=3)
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._docs_dir = self._base / "data" / "documents"
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._base / "data" / "rag_index.json"
        self._chunks: list[DocumentChunk] = []
        self._doc_registry: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._load_index()

    # ─── public ──────────────────────────────────────────────

    def add_document(self, file_path: str | Path) -> dict:
        """ドキュメントを追加してインデックスする"""
        path = Path(file_path)
        if not path.exists():
            return {"error": f"ファイルが見つかりません: {path}"}

        # テキスト抽出
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = _read_pdf(path)
        elif suffix in (".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml"):
            text = _read_text_file(path)
        else:
            return {"error": f"未対応の形式です: {suffix}"}

        if not text or len(text.strip()) < 10:
            return {"error": "テキストを抽出できませんでした"}

        # ドキュメントIDを生成
        doc_id = hashlib.sha256(f"{path.name}:{len(text)}".encode()).hexdigest()[:12]

        # 既に追加済みならスキップ
        if doc_id in self._doc_registry:
            return {"status": "already_indexed", "doc_id": doc_id}

        # チャンク分割
        raw_chunks = _split_into_chunks(text)
        new_chunks: list[DocumentChunk] = []
        for i, chunk_text in enumerate(raw_chunks):
            new_chunks.append(DocumentChunk(
                doc_id=doc_id,
                doc_name=path.name,
                chunk_idx=i,
                text=chunk_text,
            ))

        with self._lock:
            self._chunks.extend(new_chunks)
            self._doc_registry[doc_id] = {
                "name": path.name,
                "path": str(path),
                "chunks": len(new_chunks),
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_index()

        return {
            "status": "indexed",
            "doc_id": doc_id,
            "name": path.name,
            "chunks": len(new_chunks),
        }

    def search(self, query: str, limit: int = 3) -> list[dict]:
        """クエリに関連するチャンクを検索する"""
        if not self._chunks:
            return []

        # シンプルなキーワードスコアリング
        q_lower = query.lower()
        keywords = [w for w in q_lower.replace("　", " ").split() if len(w) >= 2]
        if not keywords:
            keywords = [q_lower]

        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in self._chunks:
            c_lower = chunk.text.lower()
            score = 0.0
            for kw in keywords:
                if kw in c_lower:
                    score += 1.0
                    # 出現回数でボーナス
                    score += c_lower.count(kw) * 0.2
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[dict] = []
        for score, chunk in scored[:limit]:
            results.append({
                "doc_name": chunk.doc_name,
                "chunk_idx": chunk.chunk_idx,
                "text": chunk.text,
                "score": round(score, 2),
            })
        return results

    def search_for_context(self, query: str, limit: int = 3, max_chars: int = 500) -> str:
        """LLMコンテキスト用に整形した検索結果を返す"""
        results = self.search(query, limit=limit)
        if not results:
            return ""
        parts: list[str] = []
        total = 0
        for r in results:
            snippet = r["text"][:200]
            entry = f"[{r['doc_name']}] {snippet}"
            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)
        if parts:
            return "参考資料：" + "／".join(parts)
        return ""

    def list_documents(self) -> list[dict]:
        """登録済みドキュメント一覧"""
        return [
            {"doc_id": did, **info}
            for did, info in self._doc_registry.items()
        ]

    def remove_document(self, doc_id: str) -> bool:
        """ドキュメントを削除"""
        if doc_id not in self._doc_registry:
            return False
        with self._lock:
            self._chunks = [c for c in self._chunks if c.doc_id != doc_id]
            del self._doc_registry[doc_id]
            self._save_index()
        return True

    @property
    def total_chunks(self) -> int:
        return len(self._chunks)

    # ─── private ─────────────────────────────────────────────

    def _save_index(self) -> None:
        data = {
            "documents": self._doc_registry,
            "chunks": [
                {
                    "doc_id": c.doc_id,
                    "doc_name": c.doc_name,
                    "chunk_idx": c.chunk_idx,
                    "text": c.text,
                }
                for c in self._chunks
            ],
        }
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(data, ensure_ascii=False, indent=2, fp=f)

    def _load_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._doc_registry = data.get("documents", {})
            for c in data.get("chunks", []):
                self._chunks.append(DocumentChunk(
                    doc_id=c["doc_id"],
                    doc_name=c["doc_name"],
                    chunk_idx=c["chunk_idx"],
                    text=c["text"],
                ))
        except (json.JSONDecodeError, KeyError):
            pass
