"""
WebBuilder — HP構成案 → HTML/CSS/JS コード生成
Sprint 2 Feature H
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class WebBuildResult:
    success: bool
    project_dir: str
    sitemap: list[str]
    files: list[str]
    message: str


class WebBuilder:
    """ユーザーのリクエストからウェブサイトを生成するエージェント。

    処理フロー:
    1. LLM でサイト構成案（サイトマップ）を生成
    2. 各ページの HTML/CSS/JS を生成
    3. data/web_projects/{timestamp}/ に保存
    4. 成功パターンを data/web_build_patterns.json に学習
    """

    def __init__(self, base_dir: Path, llm_fn: Callable[[str], str]) -> None:
        self.base_dir = Path(base_dir)
        self.llm_fn = llm_fn
        self._projects_dir = self.base_dir / "data" / "web_projects"
        self._patterns_path = self.base_dir / "data" / "web_build_patterns.json"
        self._projects_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────
    # 公開 API
    # ─────────────────────────────────────────────────────────

    def build(self, user_request: str) -> WebBuildResult:
        """サイトを構成して生成する。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = self._projects_dir / timestamp
        project_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. サイトマップ生成
            sitemap = self._generate_sitemap(user_request)
            if not sitemap:
                return WebBuildResult(
                    success=False,
                    project_dir=str(project_dir),
                    sitemap=[],
                    files=[],
                    message="サイト構成案の生成に失敗しました。",
                )

            # 2. 共通 CSS を生成
            css_content = self._generate_css(user_request, sitemap)
            css_path = project_dir / "style.css"
            css_path.write_text(css_content, encoding="utf-8")
            generated_files: list[str] = [str(css_path)]

            # 3. 各ページを生成
            for page_name in sitemap:
                html_content = self._generate_page(
                    user_request, page_name, sitemap, css_content
                )
                filename = self._page_to_filename(page_name)
                page_path = project_dir / filename
                page_path.write_text(html_content, encoding="utf-8")
                generated_files.append(str(page_path))

            # 4. 成功パターン保存
            self._save_pattern(user_request, sitemap, len(generated_files))

            message = (
                f"✅ ウェブサイトを生成したよ！\n"
                f"📁 保存先: {project_dir}\n"
                f"📄 ページ数: {len(sitemap)}\n"
                f"🗂 ファイル数: {len(generated_files)}"
            )
            return WebBuildResult(
                success=True,
                project_dir=str(project_dir),
                sitemap=sitemap,
                files=generated_files,
                message=message,
            )

        except Exception as exc:
            logger.warning("[WebBuilder] ビルド失敗: %s", exc)
            return WebBuildResult(
                success=False,
                project_dir=str(project_dir),
                sitemap=[],
                files=[],
                message=f"ウェブサイトの生成中にエラーが発生したよ: {exc}",
            )

    # ─────────────────────────────────────────────────────────
    # プライベートメソッド
    # ─────────────────────────────────────────────────────────

    def _generate_sitemap(self, user_request: str) -> list[str]:
        """LLM でサイト構成案を生成し、ページ名リストを返す。"""
        prompt = (
            f"以下のリクエストに合うウェブサイトのサイトマップを日本語で作成してください。\n"
            f"リクエスト: {user_request}\n\n"
            "出力形式: ページ名を1行1つ、シンプルなテキストで列挙してください（番号や記号は不要）。\n"
            "例:\nトップページ\n会社概要\nサービス紹介\nお問い合わせ\n\n"
            "3〜6ページ程度で構成してください。"
        )
        try:
            response = self.llm_fn(prompt)
            pages = [
                line.strip()
                for line in response.strip().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            # 不要なプレフィックスを除去
            cleaned = []
            for p in pages:
                p = re.sub(r"^[\d\.\-\*\・\s]+", "", p).strip()
                if p:
                    cleaned.append(p)
            return cleaned[:8] if cleaned else ["トップページ", "お問い合わせ"]
        except Exception as exc:
            logger.warning("[WebBuilder] サイトマップ生成失敗: %s", exc)
            return ["トップページ", "お問い合わせ"]

    def _generate_css(self, user_request: str, sitemap: list[str]) -> str:
        """共通 CSS を生成する。"""
        prompt = (
            f"以下のウェブサイト向けにモダンでレスポンシブな CSS を生成してください。\n"
            f"サイト概要: {user_request}\n"
            f"ページ構成: {', '.join(sitemap)}\n\n"
            "要件:\n"
            "- CSS カスタムプロパティ（変数）を使用\n"
            "- モバイルファースト\n"
            "- シンプルで読みやすいデザイン\n"
            "- ナビゲーション、ヘッダー、フッター、メインコンテンツのスタイルを含む\n"
            "コードブロックなしで CSS のみ出力してください。"
        )
        try:
            return self.llm_fn(prompt)
        except Exception as exc:
            logger.warning("[WebBuilder] CSS 生成失敗: %s", exc)
            return self._fallback_css()

    def _generate_page(
        self,
        user_request: str,
        page_name: str,
        sitemap: list[str],
        css_content: str,
    ) -> str:
        """指定ページの HTML を生成する。"""
        nav_links = "\n".join(
            f'        <li><a href="{self._page_to_filename(p)}">{p}</a></li>'
            for p in sitemap
        )
        prompt = (
            f"以下の条件で HTML ページを生成してください。\n"
            f"サイト概要: {user_request}\n"
            f"現在のページ: {page_name}\n"
            f"ナビゲーションリンク:\n{nav_links}\n\n"
            "要件:\n"
            "- DOCTYPE html 宣言から始まる完全な HTML5\n"
            "- <link rel=\"stylesheet\" href=\"style.css\"> でスタイルシートを読み込む\n"
            "- セマンティック HTML タグを使用（header, nav, main, footer など）\n"
            "- 日本語コンテンツ（lang=\"ja\"）\n"
            "- このページ固有のコンテンツを作成\n"
            "コードブロックなしで HTML のみ出力してください。"
        )
        try:
            return self.llm_fn(prompt)
        except Exception as exc:
            logger.warning("[WebBuilder] ページ生成失敗 (%s): %s", page_name, exc)
            return self._fallback_html(page_name, nav_links)

    def _page_to_filename(self, page_name: str) -> str:
        """ページ名をファイル名に変換する。"""
        mapping = {
            "トップページ": "index.html",
            "ホーム": "index.html",
            "TOP": "index.html",
        }
        if page_name in mapping:
            return mapping[page_name]
        # ASCII 以外の文字を除去してスネークケース化
        ascii_name = re.sub(r"[^\w\s]", "", page_name).strip()
        if not ascii_name:
            ascii_name = "page"
        snake = re.sub(r"\s+", "_", ascii_name).lower()
        return f"{snake}.html"

    def _save_pattern(
        self, user_request: str, sitemap: list[str], file_count: int
    ) -> None:
        """成功パターンを JSON に追記保存する。"""
        try:
            patterns: list[dict] = []
            if self._patterns_path.exists():
                with open(self._patterns_path, encoding="utf-8") as f:
                    patterns = json.load(f)
        except Exception:
            patterns = []

        patterns.append(
            {
                "timestamp": datetime.now().isoformat(),
                "request": user_request[:200],
                "sitemap": sitemap,
                "file_count": file_count,
            }
        )
        # 最新 50 件を保持
        patterns = patterns[-50:]
        try:
            with open(self._patterns_path, "w", encoding="utf-8") as f:
                json.dump(patterns, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("[WebBuilder] パターン保存失敗: %s", exc)

    # ─────────────────────────────────────────────────────────
    # フォールバックテンプレート
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_css() -> str:
        return (
            ":root {\n"
            "  --color-primary: #0066cc;\n"
            "  --color-bg: #ffffff;\n"
            "  --color-text: #333333;\n"
            "  --space-md: 1rem;\n"
            "}\n"
            "* { box-sizing: border-box; margin: 0; padding: 0; }\n"
            "body { font-family: sans-serif; color: var(--color-text); background: var(--color-bg); }\n"
            "header { background: var(--color-primary); color: #fff; padding: var(--space-md); }\n"
            "nav ul { list-style: none; display: flex; gap: var(--space-md); }\n"
            "nav a { color: #fff; text-decoration: none; }\n"
            "main { padding: var(--space-md); max-width: 960px; margin: auto; }\n"
            "footer { text-align: center; padding: var(--space-md); background: #f0f0f0; }\n"
        )

    @staticmethod
    def _fallback_html(page_name: str, nav_links: str) -> str:
        return (
            "<!DOCTYPE html>\n"
            '<html lang="ja">\n'
            "<head>\n"
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"  <title>{page_name}</title>\n"
            '  <link rel="stylesheet" href="style.css">\n'
            "</head>\n"
            "<body>\n"
            "  <header>\n"
            "    <nav>\n"
            f"      <ul>\n{nav_links}\n      </ul>\n"
            "    </nav>\n"
            "  </header>\n"
            "  <main>\n"
            f"    <h1>{page_name}</h1>\n"
            "    <p>コンテンツを準備中です。</p>\n"
            "  </main>\n"
            "  <footer><p>&copy; 2025</p></footer>\n"
            "</body>\n"
            "</html>\n"
        )
