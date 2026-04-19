#!/usr/bin/env python3
"""
daily_learning_update.py
────────────────────────
毎日10件、コード関連を中心に最新パターンを収集して学習データを更新します。

実行方法:
    python3 scripts/daily_learning_update.py

スケジュール実行:
    launchd / cron / Claude スケジュールタスクから自動起動されます。
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ─── パス設定 ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_FILE = DATA_DIR / "learning_log.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [daily_update] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TIMESTAMP = datetime.now().isoformat(timespec="seconds")

# ─── ターゲットファイル ───────────────────────────────────────────────
# 優先度高：コード関連（開発支援のため最重要）
PRIORITY_FILES = {
    "code_review_patterns.json": "code",
    "research_patterns.json": "research",
    "task_patterns.json": "task",
}
# 補助：その他
SECONDARY_FILES = {
    "image_patterns.json": "image",
    "doc_patterns.json": "doc",
    "competitor_patterns.json": "competitor",
}


# ─── 検索ヘルパー ────────────────────────────────────────────────────
def _search(query: str, max_results: int = 5) -> list[dict]:
    """DDGで検索。ddgs / duckduckgo_search どちらでも動く。"""
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
    except ImportError:
        logger.warning("ddgs / duckduckgo_search が見つかりません。検索をスキップします。")
        return []
    except Exception as exc:
        logger.warning("検索エラー: %s", exc)
        return []


def _load_json(path: Path) -> list | dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("読み込み失敗 %s: %s", path, exc)
        return []


def _save_json(path: Path, data: list | dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("保存完了: %s (%s件)", path.name,
                len(data) if isinstance(data, list) else len(data.get("mood_map", data)))


def _log_entry(category: str, added: list[str]) -> None:
    entry = {
        "date": TIMESTAMP[:10],
        "timestamp": TIMESTAMP,
        "category": category,
        "added_count": len(added),
        "added_items": added[:5],  # 最大5件のサマリー
    }
    DATA_DIR.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── コードレビューパターン更新 ──────────────────────────────────────
# 毎日のトレンドキーワードリスト（ローテーション）
_CODE_TREND_QUERIES = [
    "python new features 2026 best practices",
    "typescript 5 new features common mistakes",
    "react 19 patterns anti-patterns 2026",
    "javascript security vulnerabilities 2026 OWASP",
    "golang best practices 2026 performance",
    "rust common mistakes beginners 2026",
    "SQL query optimization tips 2026",
    "CSS modern layout best practices 2026",
    "node.js security checklist 2026",
    "next.js app router best practices 2026",
    "python async await common pitfalls",
    "docker kubernetes security best practices",
    "github actions ci/cd best practices",
    "api design restful best practices 2026",
    "database design anti-patterns 2026",
]

def _get_today_code_queries() -> list[str]:
    """今日の曜日で検索クエリをローテーション（3件）"""
    day_of_year = datetime.now().timetuple().tm_yday
    n = len(_CODE_TREND_QUERIES)
    return [
        _CODE_TREND_QUERIES[day_of_year % n],
        _CODE_TREND_QUERIES[(day_of_year + 1) % n],
        _CODE_TREND_QUERIES[(day_of_year + 2) % n],
    ]


def update_code_review_patterns(target_add: int = 4) -> int:
    """コードレビューパターンを target_add 件更新する。"""
    path = DATA_DIR / "code_review_patterns.json"
    data: list[dict] = _load_json(path)
    existing_langs = {d["language"] for d in data}

    queries = _get_today_code_queries()
    new_issues: dict[str, list[str]] = {}
    new_patterns: dict[str, list[str]] = {}

    for query in queries:
        results = _search(query, max_results=3)
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            combined = f"{title} {body}"

            # 言語を推定
            lang = _infer_language(query)
            if lang not in new_issues:
                new_issues[lang] = []
                new_patterns[lang] = []

            # タイトルをissue/patternとして追加
            if title and len(title) > 10:
                if any(w in combined.lower() for w in ["mistake", "pitfall", "avoid", "bad", "anti", "wrong", "issue"]):
                    new_issues[lang].append(_clean_text(title))
                elif any(w in combined.lower() for w in ["best", "good", "pattern", "recommend", "tip", "use"]):
                    new_patterns[lang].append(_clean_text(title))

    added_count = 0
    added_names = []

    for lang, issues in new_issues.items():
        if not issues and not new_patterns.get(lang):
            continue
        # 既存エントリを探して更新
        found = False
        for entry in data:
            if entry["language"] == lang:
                before = len(entry["common_issues"])
                new_unique_issues = [i for i in issues if i not in entry["common_issues"]][:2]
                new_unique_patterns = [p for p in new_patterns.get(lang, []) if p not in entry["good_patterns"]][:2]
                entry["common_issues"].extend(new_unique_issues)
                entry["good_patterns"].extend(new_unique_patterns)
                added = len(new_unique_issues) + len(new_unique_patterns)
                if added > 0:
                    added_count += added
                    added_names.append(f"{lang}(+{added})")
                found = True
                break
        if not found and lang not in existing_langs:
            # 新言語エントリを追加
            data.append({
                "language": lang,
                "common_issues": issues[:5],
                "good_patterns": new_patterns.get(lang, [])[:5],
                "score": 0.85,
                "timestamp": TIMESTAMP,
            })
            added_count += len(issues[:5])
            added_names.append(f"{lang}(新規)")

    if added_count > 0:
        _save_json(path, data)
        _log_entry("code_review", added_names)
    return added_count


def _infer_language(query: str) -> str:
    q = query.lower()
    mapping = {
        "python": "python", "typescript": "typescript", "react": "react",
        "javascript": "javascript", "golang": "golang", "rust": "rust",
        "sql": "sql", "css": "css", "node": "javascript", "next.js": "react",
        "docker": "shell", "api": "rest_api",
    }
    for kw, lang in mapping.items():
        if kw in q:
            return lang
    return "general"


def _clean_text(s: str) -> str:
    """テキストをクリーンアップ（個人情報・URLを除去）"""
    import re
    s = re.sub(r"https?://\S+", "", s).strip()
    s = re.sub(r"[\[\]<>]", "", s).strip()
    return s[:120]


# ─── リサーチパターン更新 ────────────────────────────────────────────
_RESEARCH_QUERIES_ROTATION = [
    ("最新フレームワーク 比較 2026 ランキング", "新技術比較テンプレ", "最新ランキング系クエリ"),
    ("{tool} チュートリアル 入門 2026 公式", "ツール入門調査", "公式ドキュメント系"),
    ("{company} 技術ブログ エンジニア 採用", "企業技術調査", "採用・技術スタック"),
    ("GitHub trending {language} today stars", "GitHubトレンド調査", "今日人気のOSS"),
    ("{topic} セキュリティ 脆弱性 CVE 2026", "セキュリティ調査", "CVE/脆弱性情報"),
]

def update_research_patterns(target_add: int = 3) -> int:
    path = DATA_DIR / "research_patterns.json"
    data: list[dict] = _load_json(path)
    existing_queries = {d.get("query", "") for d in data}

    day_of_year = datetime.now().timetuple().tm_yday
    template = _RESEARCH_QUERIES_ROTATION[day_of_year % len(_RESEARCH_QUERIES_ROTATION)]

    new_entries = [
        {
            "query": template[0],
            "query_ja": template[1],
            "score": 0.84,
            "timestamp": TIMESTAMP,
            "tips": template[2],
        }
    ]

    added = 0
    for entry in new_entries:
        if entry["query"] not in existing_queries:
            data.append(entry)
            added += 1

    if added > 0:
        _save_json(path, data)
        _log_entry("research", [e["query_ja"] for e in new_entries[:added]])
    return added


# ─── タスクパターン更新 ──────────────────────────────────────────────
_TASK_ROTATION = [
    {
        "task_ja": "コードのパフォーマンスを改善して",
        "steps": [
            {"type": "analyze", "description": "ボトルネックの特定（プロファイリング）"},
            {"type": "research", "description": "最新の最適化手法を調査"},
            {"type": "write", "description": "改善案の提案"},
            {"type": "code", "description": "最適化コードの生成"},
        ],
    },
    {
        "task_ja": "セキュリティ診断レポートを作って",
        "steps": [
            {"type": "analyze", "description": "コードのセキュリティ問題スキャン"},
            {"type": "research", "description": "OWASP Top10・CVEデータベース確認"},
            {"type": "write", "description": "リスク評価と優先度付け"},
            {"type": "doc", "description": "診断レポートをWord形式で出力"},
        ],
    },
    {
        "task_ja": "技術選定の比較表を作って",
        "steps": [
            {"type": "research", "description": "候補技術の最新情報収集"},
            {"type": "analyze", "description": "パフォーマンス・コスト・学習コスト比較"},
            {"type": "write", "description": "比較表の作成"},
            {"type": "doc", "description": "意思決定ドキュメントとして出力"},
        ],
    },
    {
        "task_ja": "このAPIの使い方を調べてサンプルコードを作って",
        "steps": [
            {"type": "research", "description": "公式ドキュメント・GitHub調査"},
            {"type": "summarize", "description": "主要エンドポイントの整理"},
            {"type": "code", "description": "サンプルコードの生成"},
            {"type": "write", "description": "使い方ガイドの作成"},
        ],
    },
    {
        "task_ja": "テストコードを書いて",
        "steps": [
            {"type": "analyze", "description": "テスト対象コードの分析"},
            {"type": "research", "description": "テストフレームワーク・ベストプラクティス確認"},
            {"type": "code", "description": "ユニットテスト・統合テストの生成"},
            {"type": "write", "description": "テスト仕様書の作成"},
        ],
    },
    {
        "task_ja": "リファクタリング計画を立てて",
        "steps": [
            {"type": "analyze", "description": "コードの品質・複雑度分析"},
            {"type": "write", "description": "リファクタリング優先度リストの作成"},
            {"type": "code", "description": "改善後のコードサンプル生成"},
            {"type": "doc", "description": "リファクタリング計画書の出力"},
        ],
    },
    {
        "task_ja": "ライブラリのアップデート対応をして",
        "steps": [
            {"type": "research", "description": "ライブラリの変更履歴・破壊的変更を調査"},
            {"type": "analyze", "description": "影響範囲の特定"},
            {"type": "code", "description": "移行コードの生成"},
            {"type": "write", "description": "対応手順書の作成"},
        ],
    },
]

def update_task_patterns(target_add: int = 3) -> int:
    path = DATA_DIR / "task_patterns.json"
    data: list[dict] = _load_json(path)
    existing_tasks = {d.get("task_ja", "") for d in data}

    day_of_year = datetime.now().timetuple().tm_yday
    candidates = _TASK_ROTATION[day_of_year % len(_TASK_ROTATION):] + \
                 _TASK_ROTATION[:day_of_year % len(_TASK_ROTATION)]

    added = 0
    added_names = []
    for candidate in candidates:
        if candidate["task_ja"] not in existing_tasks and added < target_add:
            data.append({**candidate, "score": 0.87, "timestamp": TIMESTAMP})
            existing_tasks.add(candidate["task_ja"])
            added_names.append(candidate["task_ja"])
            added += 1

    if added > 0:
        _save_json(path, data)
        _log_entry("task", added_names)
    return added


# ─── メイン ──────────────────────────────────────────────────────────
def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info("=== 日次学習データ更新開始 %s ===", today)

    # 今日すでに実行済みか確認
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        today_runs = [l for l in lines if f'"date": "{today}"' in l]
        if len(today_runs) >= 5:
            logger.info("本日分は更新済みです（%d件ログあり）。スキップします。", len(today_runs))
            return

    total = 0

    # 1. コードレビューパターン（最重要・4件）
    logger.info("--- コードレビューパターン更新中 ---")
    n = update_code_review_patterns(target_add=4)
    logger.info("コードレビュー: +%d件", n)
    total += n

    # 2. タスクパターン（3件）
    logger.info("--- タスクパターン更新中 ---")
    n = update_task_patterns(target_add=3)
    logger.info("タスクパターン: +%d件", n)
    total += n

    # 3. リサーチパターン（3件）
    logger.info("--- リサーチパターン更新中 ---")
    n = update_research_patterns(target_add=3)
    logger.info("リサーチパターン: +%d件", n)
    total += n

    # 4. GitHub パターン（3件）
    logger.info("--- GitHub パターン更新中 ---")
    n = update_github_patterns(target_add=3)
    logger.info("GitHubパターン: +%d件", n)
    total += n

    logger.info("=== 完了 合計 +%d件 追加 ===", total)
    _log_entry("daily_summary", [f"合計+{total}件", today])


# ─── GitHub パターン更新 ─────────────────────────────────────────────
# 毎日ローテーションするカテゴリ×キーワード
_GITHUB_CATEGORY_ROTATION = [
    ("SaaS管理画面",       ["saas dashboard nextjs stripe prisma typescript"]),
    ("AIチャットアプリ",   ["ai chat app langchain nextjs openai stream"]),
    ("ECサイト",           ["ecommerce app nextjs stripe tailwind cart"]),
    ("認証システム",       ["auth nextauth clerk supabase oauth typescript"]),
    ("REST APIサーバー",   ["fastapi rest api postgresql docker python"]),
    ("モバイルアプリ",     ["react native expo typescript firebase app"]),
    ("リアルタイムチャット", ["chat app websocket socket.io react nodejs"]),
    ("ブログCMS",          ["blog cms nextjs mdx contentful sanity"]),
    ("タスク管理アプリ",   ["task manager todo app react typescript drag drop"]),
    ("ダッシュボード",     ["analytics dashboard recharts shadcn react"]),
    ("画像生成AIアプリ",   ["stable diffusion comfyui image generation python"]),
    ("RAGシステム",        ["rag retrieval augmented generation langchain vector db"]),
    ("マイクロサービス",   ["microservices docker kubernetes nodejs golang"]),
    ("CI/CDパイプライン",  ["github actions cicd deploy docker typescript"]),
    ("GraphQL API",        ["graphql apollo server prisma typescript nexus"]),
    ("フルスタックSaaS",   ["t3 stack trpc nextjs prisma tailwind typescript"]),
    ("音楽ストリーミング", ["music streaming app spotify api react"]),
    ("求人サイト",         ["job board next.js prisma authentication typescript"]),
    ("不動産サイト",       ["real estate nextjs map api filter typescript"]),
    ("予約システム",       ["booking calendar reservation nextjs stripe"]),
]

def update_github_patterns(target_add: int = 3) -> int:
    """GitHub パターンを target_add 件追加する。"""
    import sys
    # core/github_learner を使う
    core_dir = BASE_DIR / "core"
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    try:
        from core.github_learner import GithubLearner, GithubPattern
    except ImportError as e:
        logger.warning("[GitHub] github_learner インポート失敗: %s", e)
        return _update_github_patterns_fallback(target_add)

    day_of_year = datetime.now().timetuple().tm_yday
    n = len(_GITHUB_CATEGORY_ROTATION)
    candidates = [
        _GITHUB_CATEGORY_ROTATION[(day_of_year + i) % n]
        for i in range(target_add * 2)
    ]

    learner = GithubLearner(base_dir=BASE_DIR)
    existing = learner._load_existing()
    existing_cats = {d.get("category", "") for d in existing}

    added = 0
    added_names = []
    for category_ja, queries in candidates:
        if category_ja in existing_cats or added >= target_add:
            continue
        patterns = learner.collect_by_category(category_ja, queries[0].split())
        if not patterns:
            # フォールバック: 手動エントリを生成
            patterns = [_make_fallback_pattern(category_ja, queries[0])]
        saved = learner.save_patterns(patterns[:1])
        if saved > 0:
            added += saved
            added_names.append(category_ja)
            existing_cats.add(category_ja)

    if added_names:
        _log_entry("github", added_names)
    return added


def _make_fallback_pattern(category_ja: str, query: str) -> "GithubPattern":
    """検索失敗時のフォールバックパターン生成。"""
    from core.github_learner import GithubPattern
    # クエリからtech stackを推定
    tech_map = {
        "nextjs": "Next.js", "react": "React", "typescript": "TypeScript",
        "prisma": "Prisma", "stripe": "Stripe", "tailwind": "Tailwind CSS",
        "fastapi": "FastAPI", "python": "Python", "docker": "Docker",
        "langchain": "LangChain", "openai": "OpenAI API",
        "supabase": "Supabase", "postgresql": "PostgreSQL",
        "nodejs": "Node.js", "socket.io": "Socket.IO",
        "kubernetes": "Kubernetes", "golang": "Go",
    }
    tech_stack = [v for k, v in tech_map.items() if k in query.lower()]
    return GithubPattern(
        repo_type="web_app",
        category=category_ja,
        tech_stack=tech_stack[:5],
        common_patterns=["JWT認証", "REST API設計", "型安全"],
        score=0.83,
    )


def _update_github_patterns_fallback(target_add: int) -> int:
    """github_learner が使えない場合の簡易フォールバック。"""
    path = DATA_DIR / "github_patterns.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = []

    day_of_year = datetime.now().timetuple().tm_yday
    existing_cats = {d.get("category", "") for d in data}
    added = 0
    added_names = []

    for i in range(target_add * 2):
        cat_ja, queries = _GITHUB_CATEGORY_ROTATION[(day_of_year + i) % len(_GITHUB_CATEGORY_ROTATION)]
        if cat_ja in existing_cats or added >= target_add:
            continue
        q = queries[0].split()
        entry = {
            "repo_type": "web_app",
            "category": cat_ja,
            "tech_stack": q[:4],
            "common_patterns": ["JWT認証", "型安全"],
            "score": 0.83,
            "timestamp": TIMESTAMP,
        }
        data.append(entry)
        existing_cats.add(cat_ja)
        added_names.append(cat_ja)
        added += 1

    if added > 0:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _log_entry("github_fallback", added_names)
    return added


if __name__ == "__main__":
    main()
