"""
Web リサーチエージェント

DuckDuckGo でWeb検索し、上位ページをスクレイプして要点を抽出。
成功した検索パターンを学習して類似クエリに再利用する。
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 24


@dataclass
class ResearchResult:
    query: str
    summary: str
    sources: list[str]
    raw_snippets: list[str]
    cached: bool
    timestamp: str


class ResearchAgent:
    """DuckDuckGo 検索 + ページスクレイプ + LLM 要約エージェント。"""

    def __init__(self, base_dir: Path, llm_fn: Callable[[str], str]) -> None:
        self._base_dir = Path(base_dir)
        self._llm_fn = llm_fn
        self._cache_dir = self._base_dir / "data" / "research_cache"
        self._patterns_path = self._base_dir / "data" / "research_patterns.json"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def search(self, query: str, max_results: int = 5) -> ResearchResult:
        """DuckDuckGo で検索し、上位ページをスクレイプして LLM で要約する。

        キャッシュが有効（24時間以内）であればキャッシュを返す。
        成功した検索パターンを data/research_patterns.json に保存する。
        """
        # キャッシュ確認
        cached = self._load_cache(query)
        if cached is not None:
            logger.info("[ResearchAgent] キャッシュヒット: %s", query)
            return cached

        snippets: list[str] = []
        sources: list[str] = []

        # DuckDuckGo 検索
        try:
            results = self._ddg_search(query, max_results=max_results)
            for item in results:
                url = item.get("href") or item.get("url", "")
                body = item.get("body") or item.get("snippet", "")
                if body:
                    snippets.append(body)
                if url:
                    sources.append(url)
        except ImportError:
            logger.warning("[ResearchAgent] duckduckgo_search が未インストール。スニペットなしで続行します")
        except Exception as exc:
            logger.warning("[ResearchAgent] DDG 検索失敗: %s", exc)

        # 上位ページをスクレイプ（最大3件）
        for url in sources[:3]:
            try:
                text = self._fetch_page(url)
                if text:
                    snippets.append(text[:1000])
            except Exception as exc:
                logger.warning("[ResearchAgent] ページ取得失敗 %s: %s", url, exc)

        # LLM 要約
        if snippets:
            summary = self._summarize(query, snippets)
        else:
            summary = f"「{query}」に関する情報は見つかりませんでした。"

        timestamp = datetime.now().isoformat()
        result = ResearchResult(
            query=query,
            summary=summary,
            sources=sources,
            raw_snippets=snippets,
            cached=False,
            timestamp=timestamp,
        )

        # キャッシュ保存
        self._save_cache(query, result)

        # 成功パターン学習
        if snippets:
            self._save_pattern(query)

        return result

    def expand_query_orthogonally(self, query: str, llm_fn=None) -> list[str]:
        """
        フレーム解体器による直交クエリ展開。
        元のクエリを複数の独立した視点に展開し、
        検索の盲点を減らす（ゲーデル的: 単一フレームの限界を超える）。
        """
        try:
            from core.akashic.frame_destructor import FrameDestructor
            fn = llm_fn or self._llm_fn
            expansions = FrameDestructor(llm_fn=fn).orthogonalize(query, llm_fn=fn)
            return [q for q in expansions if q and q != query][:5]
        except Exception:
            return []

    def search_multi_domain(self, query: str, max_results: int = 3) -> list["ResearchResult"]:
        """
        多次元クエリ検索: 元クエリ + 直交展開クエリで並列検索。
        UnifiedField の多ドメイン共鳴 + FrameDestructor の直交化で
        単一検索では見えない情報を発掘する。
        """
        results = []
        # 元クエリ
        try:
            results.append(self.search(query, max_results=max_results))
        except Exception:
            pass
        # 直交展開クエリ (最大2件追加)
        expansions = self.expand_query_orthogonally(query)
        for expansion in expansions[:2]:
            try:
                r = self.search(expansion, max_results=max_results)
                results.append(r)
            except Exception:
                pass
        return results

    def get_learned_patterns(self) -> list[dict]:
        """過去の成功検索パターンを返す（類似クエリの再利用に使う）。"""
        if not self._patterns_path.exists():
            return []
        try:
            with open(self._patterns_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("[ResearchAgent] パターン読み込み失敗: %s", exc)
            return []

    # ──────────────────────────────────────────────────────────────
    # 内部実装
    # ──────────────────────────────────────────────────────────────

    def _ddg_search(self, query: str, max_results: int) -> list[dict]:
        """DuckDuckGo で検索して結果リストを返す。"""
        try:
            from ddgs import DDGS  # type: ignore  # 新パッケージ名 (ddgs>=9.x)
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore  # 旧パッケージ名

        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    def _fetch_page(self, url: str) -> str:
        """urllib でページを取得し、BeautifulSoup でテキストを抽出する。"""
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except ImportError:
            logger.warning("[ResearchAgent] beautifulsoup4 が未インストール。テキスト抽出をスキップします")
            return ""

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read(50_000)
        except urllib.error.URLError as exc:
            logger.warning("[ResearchAgent] URL 取得失敗 %s: %s", url, exc)
            return ""

        encoding = "utf-8"
        try:
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)[:3000]
        except Exception as exc:
            logger.warning("[ResearchAgent] HTML パース失敗: %s", exc)
            try:
                return raw.decode(encoding, errors="replace")[:3000]
            except Exception:
                return ""

    def _summarize(self, query: str, texts: list[str]) -> str:
        """LLM でテキストリストを箇条書き形式で要約する。"""
        combined = "\n\n".join(texts[:5])[:3000]
        prompt = (
            f"以下は「{query}」についての Web 検索結果です。\n"
            f"重要な情報を日本語で箇条書き（3〜5点）にまとめてください。\n\n"
            f"{combined}\n\n"
            f"箇条書きまとめ:"
        )
        try:
            return self._llm_fn(prompt)
        except Exception as exc:
            logger.warning("[ResearchAgent] LLM 要約失敗: %s", exc)
            # フォールバック: テキストの先頭を返す
            first = texts[0][:300] if texts else ""
            return f"（要約生成に失敗しました）\n{first}"

    # ── キャッシュ ────────────────────────────────────────────────

    def _cache_key(self, query: str) -> str:
        # MD5 is used only as a deterministic cache filename, not for security
        return hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _cache_path(self, query: str) -> Path:
        return self._cache_dir / f"{self._cache_key(query)}.json"

    def _load_cache(self, query: str) -> ResearchResult | None:
        path = self._cache_path(query)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # TTL チェック
            ts = datetime.fromisoformat(data["timestamp"])
            if datetime.now() - ts > timedelta(hours=_CACHE_TTL_HOURS):
                path.unlink(missing_ok=True)
                return None
            return ResearchResult(
                query=data["query"],
                summary=data["summary"],
                sources=data["sources"],
                raw_snippets=data["raw_snippets"],
                cached=True,
                timestamp=data["timestamp"],
            )
        except Exception as exc:
            logger.warning("[ResearchAgent] キャッシュ読み込み失敗: %s", exc)
            return None

    def _save_cache(self, query: str, result: ResearchResult) -> None:
        path = self._cache_path(query)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "query": result.query,
                        "summary": result.summary,
                        "sources": result.sources,
                        "raw_snippets": result.raw_snippets,
                        "timestamp": result.timestamp,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as exc:
            logger.warning("[ResearchAgent] キャッシュ保存失敗: %s", exc)

    # ── パターン学習 ──────────────────────────────────────────────

    def _save_pattern(self, query: str) -> None:
        """成功した検索クエリをパターンとして保存する。"""
        patterns = self.get_learned_patterns()
        # 重複排除（直近 200 件を上限）
        existing_queries = {p["query"] for p in patterns}
        if query not in existing_queries:
            patterns.append({"query": query, "timestamp": datetime.now().isoformat()})
        patterns = patterns[-200:]
        try:
            with open(self._patterns_path, "w", encoding="utf-8") as f:
                json.dump(patterns, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("[ResearchAgent] パターン保存失敗: %s", exc)
