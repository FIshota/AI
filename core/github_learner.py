"""
github_learner.py
─────────────────
GitHubの公開リポジトリから学習データを収集するモジュール。

収集内容:
- トレンドリポジトリのtech stack / アーキテクチャパターン
- Awesomeリストからのライブラリ・ツール一覧
- READMEからプロジェクト構造のパターン
- 言語別・カテゴリ別の人気ライブラリ組み合わせ

学習ファイル:
- data/github_patterns.json  ← tech stack / architecture
- data/code_review_patterns.json  ← コードパターン追記
- data/research_patterns.json     ← GitHub検索クエリ追記
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TIMESTAMP = datetime.now().isoformat(timespec="seconds")


# ─── データクラス ───────────────────────────────────────────────────
@dataclass
class GithubPattern:
    """GitHubリポジトリから学習したパターン"""
    repo_type: str                        # web_app / mobile_app / api / cli / lib / ml / game
    category: str                         # 日本語カテゴリ名
    tech_stack: list[str] = field(default_factory=list)
    architecture: str = ""               # MVC / Clean Architecture / Microservices / etc.
    common_patterns: list[str] = field(default_factory=list)
    popular_libraries: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    github_topics: list[str] = field(default_factory=list)
    stars_range: str = ""                # "1k-10k" など
    score: float = 0.85
    timestamp: str = TIMESTAMP

    def to_dict(self) -> dict:
        return asdict(self)


# ─── GitHubラーナー ────────────────────────────────────────────────
class GithubLearner:
    """
    GitHubから学習データを収集する。
    APIキー不要。DuckDuckGo + web_fetcher を使用。
    """

    def __init__(self, base_dir: Path | str, llm_fn=None) -> None:
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.patterns_file = self.data_dir / "github_patterns.json"
        self._llm_fn = llm_fn
        self.data_dir.mkdir(exist_ok=True)

    # ── 公開API ────────────────────────────────────────────────────

    def collect_trending(self, language: str = "", limit: int = 10) -> list[GithubPattern]:
        """
        GitHubトレンドを検索して GithubPattern リストを返す。
        言語を指定しない場合は全言語トレンド。
        """
        query = f"github trending {language} repositories stars 2026"
        results = self._search(query, max_results=limit)
        patterns = []
        for r in results:
            p = self._parse_result(r, source="trending", language=language)
            if p:
                patterns.append(p)
        return patterns

    def collect_awesome_list(self, topic: str) -> list[GithubPattern]:
        """
        awesome-{topic} リストから関連パターンを収集する。
        例: topic="python", "react", "nodejs"
        """
        query = f"site:github.com awesome-{topic} list libraries frameworks"
        results = self._search(query, max_results=5)
        patterns = []
        for r in results:
            # awesome リストのURLを取得してパース
            url = r.get("href", "")
            if "github.com" in url and "awesome" in url.lower():
                content = self._fetch_url(url)
                if content:
                    p = self._parse_awesome_content(content, topic)
                    if p:
                        patterns.append(p)
        return patterns

    def collect_by_category(self, category_ja: str, keywords_en: list[str]) -> list[GithubPattern]:
        """
        カテゴリ名（日本語）と英語キーワードでGitHubを検索して収集。
        """
        query = " ".join(keywords_en[:3]) + " github popular 2025 2026"
        results = self._search(query, max_results=8)
        patterns = []
        for r in results:
            p = self._parse_result(r, source="category", language="")
            if p:
                p.category = category_ja
                patterns.append(p)
        return patterns

    def save_patterns(self, new_patterns: list[GithubPattern]) -> int:
        """
        新しいパターンをファイルに保存（重複スキップ）。
        追加した件数を返す。
        """
        existing = self._load_existing()
        existing_keys = {
            (d.get("repo_type", ""), d.get("category", ""))
            for d in existing
        }
        added = 0
        for p in new_patterns:
            key = (p.repo_type, p.category)
            if key not in existing_keys:
                existing.append(p.to_dict())
                existing_keys.add(key)
                added += 1

        if added > 0:
            with open(self.patterns_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            logger.info("[GithubLearner] %d件保存: %s", added, self.patterns_file.name)
        return added

    def get_summary(self) -> dict:
        """学習済みパターンのサマリーを返す。"""
        data = self._load_existing()
        by_type: dict[str, int] = {}
        for d in data:
            t = d.get("repo_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total": len(data),
            "by_type": by_type,
            "last_updated": data[-1]["timestamp"] if data else None,
        }

    # ── 内部ヘルパー ───────────────────────────────────────────────

    def _search(self, query: str, max_results: int = 5) -> list[dict]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except ImportError:
            pass
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as exc:
            logger.warning("[GithubLearner] 検索エラー: %s", exc)
            return []

    def _fetch_url(self, url: str, timeout: int = 8) -> str:
        """URLからテキストを取得。"""
        try:
            import urllib.request
            from utils.url_guard import assert_safe_http_url
            url = assert_safe_http_url(url)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AiChan-Learner/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                raw = resp.read(65536)  # 64KB まで
                return raw.decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.debug("[GithubLearner] fetch失敗 %s: %s", url, exc)
            return ""

    def _parse_result(
        self, result: dict, source: str, language: str
    ) -> Optional[GithubPattern]:
        """DDG検索結果から GithubPattern を生成。"""
        title = result.get("title", "")
        body = result.get("body", "")
        combined = f"{title} {body}".lower()

        repo_type = self._infer_repo_type(combined)
        category = self._infer_category_ja(combined, language)
        tech_stack = self._extract_tech_stack(combined)
        patterns = self._extract_patterns(combined)

        if not tech_stack and not patterns:
            return None

        return GithubPattern(
            repo_type=repo_type,
            category=category,
            tech_stack=tech_stack[:6],
            common_patterns=patterns[:6],
            github_topics=self._extract_topics(combined),
            stars_range=self._extract_stars(combined),
            score=0.84,
        )

    def _parse_awesome_content(self, content: str, topic: str) -> Optional[GithubPattern]:
        """awesomeリストのHTMLからライブラリ名を抽出。"""
        # href から github.com/xxx/yyy 形式を抽出
        repos = re.findall(r'github\.com/[\w-]+/([\w-]+)', content)
        unique_repos = list(dict.fromkeys(repos))[:20]  # 重複除去・最大20件

        if not unique_repos:
            return None

        return GithubPattern(
            repo_type="library",
            category=f"{topic} エコシステム",
            popular_libraries=unique_repos,
            github_topics=[topic, "awesome", "curated"],
            score=0.88,
        )

    # ── 推定ロジック ───────────────────────────────────────────────

    _REPO_TYPE_MAP = {
        "web_app": ["web app", "web application", "frontend", "fullstack", "next.js", "nuxt", "remix"],
        "api": ["api", "rest api", "graphql", "backend", "server", "fastapi", "express"],
        "mobile_app": ["mobile", "ios", "android", "react native", "flutter", "swift", "kotlin"],
        "cli": ["cli", "command line", "terminal", "shell tool"],
        "ml": ["machine learning", "deep learning", "neural", "pytorch", "tensorflow", "llm", "ai model"],
        "game": ["game", "pygame", "unity", "godot", "phaser"],
        "library": ["library", "package", "npm package", "pip package", "gem", "sdk"],
        "devtool": ["devtool", "developer tool", "ci/cd", "docker", "kubernetes", "automation"],
        "data": ["data pipeline", "etl", "analytics", "dashboard", "visualization"],
    }

    def _infer_repo_type(self, text: str) -> str:
        for rtype, keywords in self._REPO_TYPE_MAP.items():
            if any(kw in text for kw in keywords):
                return rtype
        return "web_app"

    _CATEGORY_MAP = {
        "ECサイト・ショッピング": ["ecommerce", "shopping cart", "stripe", "payment"],
        "SNS・コミュニティ": ["social media", "chat", "messaging", "forum", "community"],
        "タスク管理": ["todo", "task manager", "project management", "kanban"],
        "ブログ・CMS": ["blog", "cms", "content management", "markdown"],
        "認証・セキュリティ": ["auth", "authentication", "oauth", "jwt", "security"],
        "AIアシスタント": ["chatbot", "ai assistant", "llm", "gpt", "claude"],
        "ダッシュボード": ["dashboard", "admin panel", "analytics", "metrics"],
        "APIサーバー": ["rest api", "graphql api", "microservice", "backend"],
        "ポートフォリオ": ["portfolio", "personal website", "resume"],
        "ゲーム": ["game", "rpg", "puzzle", "arcade"],
        "機械学習": ["machine learning", "deep learning", "neural network", "nlp"],
        "データ分析": ["data analysis", "data science", "jupyter", "pandas"],
        "DevOps・インフラ": ["docker", "kubernetes", "ci/cd", "infrastructure", "terraform"],
        "モバイルアプリ": ["ios app", "android app", "react native", "flutter"],
        "CLIツール": ["command line", "cli tool", "terminal"],
    }

    def _infer_category_ja(self, text: str, language: str) -> str:
        for cat_ja, keywords in self._CATEGORY_MAP.items():
            if any(kw in text for kw in keywords):
                return cat_ja
        return f"{language}プロジェクト" if language else "汎用プロジェクト"

    _TECH_KEYWORDS = [
        # フロントエンド
        "react", "vue", "angular", "svelte", "next.js", "nuxt", "remix", "astro",
        "tailwindcss", "shadcn", "radix ui",
        # バックエンド
        "node.js", "express", "fastapi", "django", "flask", "rails", "laravel",
        "spring boot", "asp.net", "go fiber", "actix",
        # DB
        "postgresql", "mysql", "sqlite", "mongodb", "redis", "supabase",
        "prisma", "drizzle", "sqlalchemy",
        # 認証
        "nextauth", "clerk", "auth.js", "firebase auth", "supabase auth",
        # インフラ
        "docker", "kubernetes", "github actions", "vercel", "netlify",
        "aws", "gcp", "azure", "cloudflare",
        # 言語
        "typescript", "python", "rust", "go", "java", "kotlin", "swift",
        # AI/ML
        "openai", "langchain", "hugging face", "pytorch", "tensorflow",
        "anthropic", "ollama", "llama",
    ]

    def _extract_tech_stack(self, text: str) -> list[str]:
        found = []
        for tech in self._TECH_KEYWORDS:
            if tech in text and tech not in found:
                found.append(tech)
        return found

    _PATTERN_KEYWORDS = {
        "JWT認証": ["jwt", "json web token"],
        "REST API設計": ["rest api", "restful"],
        "GraphQL": ["graphql", "apollo"],
        "マイクロサービス": ["microservice", "micro service"],
        "Clean Architecture": ["clean architecture", "domain driven"],
        "リポジトリパターン": ["repository pattern"],
        "MVC": ["mvc", "model view controller"],
        "Server Components": ["server component", "rsc"],
        "Edge Functions": ["edge function", "edge runtime"],
        "Optimistic UI": ["optimistic update", "optimistic ui"],
        "認証フロー": ["oauth", "oidc", "saml", "sso"],
        "WebSocket": ["websocket", "ws", "socket.io", "realtime"],
        "バックグラウンドジョブ": ["background job", "queue", "bull", "celery"],
        "キャッシュ戦略": ["cache", "redis cache", "cdn cache"],
        "テスト戦略": ["jest", "vitest", "pytest", "e2e test"],
        "CI/CD": ["ci/cd", "github actions", "gitlab ci"],
        "コンテナ化": ["docker compose", "containerized"],
        "型安全": ["type safe", "typescript", "zod", "pydantic"],
    }

    def _extract_patterns(self, text: str) -> list[str]:
        found = []
        for pattern_name, keywords in self._PATTERN_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                found.append(pattern_name)
        return found

    def _extract_topics(self, text: str) -> list[str]:
        topics_re = re.findall(r'\b(saas|cms|api|cli|sdk|oss|spa|pwa|ssr|ssg)\b', text)
        return list(set(topics_re))[:5]

    def _extract_stars(self, text: str) -> str:
        m = re.search(r'(\d[\d,]+)\s*stars?', text)
        if m:
            n = int(m.group(1).replace(",", ""))
            if n >= 10000:
                return "10k+"
            elif n >= 1000:
                return "1k-10k"
            else:
                return "< 1k"
        return ""

    def _load_existing(self) -> list[dict]:
        if not self.patterns_file.exists():
            return []
        try:
            with open(self.patterns_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
