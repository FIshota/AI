"""
CodeReviewer — コードレビュー & 修正
Sprint 2 Feature J
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
class ReviewResult:
    issues: list[str]
    suggestions: list[str]
    fixed_code: str
    summary: str
    language: str


class CodeReviewer:
    """コードをレビューして問題点・改善提案・修正済みコードを返すエージェント。"""

    # 言語判別パターン
    _LANG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("python",     re.compile(r"\bdef \w+\(|import \w+|from \w+ import|\bprint\(", re.MULTILINE)),
        ("javascript", re.compile(r"\bfunction\s+\w+\(|const\s+\w+\s*=|let\s+\w+|=>\s*\{|console\.log", re.MULTILINE)),
        ("html",       re.compile(r"<!DOCTYPE|<html|<div|<p>|<span|<head>", re.IGNORECASE | re.MULTILINE)),
        ("css",        re.compile(r"\{[^}]+\}|:\s*\w+;|@media|\.[\w-]+\s*\{", re.MULTILINE)),
    ]

    def __init__(self, base_dir: Path, llm_fn: Callable[[str], str]) -> None:
        self.base_dir = Path(base_dir)
        self.llm_fn = llm_fn
        self._patterns_path = self.base_dir / "data" / "code_review_patterns.json"
        self._patterns_path.parent.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────
    # 公開 API
    # ─────────────────────────────────────────────────────────

    def review(self, code: str, language: str = "python") -> ReviewResult:
        """コードをレビューして ReviewResult を返す。"""
        if not language or language == "auto":
            language = self.detect_language(code)

        prompt = self._build_review_prompt(code, language)
        try:
            raw = self.llm_fn(prompt)
            result = self._parse_review_response(raw, language)
        except Exception as exc:
            logger.warning("[CodeReviewer] レビュー失敗: %s", exc)
            result = ReviewResult(
                issues=[f"レビュー処理中にエラーが発生しました: {exc}"],
                suggestions=[],
                fixed_code=code,
                summary="レビューに失敗しました。",
                language=language,
            )

        # 成功パターンを保存
        self._save_pattern(language, len(result.issues), len(result.suggestions))
        return result

    def detect_language(self, code: str) -> str:
        """コードの言語を自動判別する。

        Returns:
            "python" / "javascript" / "html" / "css" / "other"
        """
        best_lang = "other"
        best_score = 0
        for lang, pattern in self._LANG_PATTERNS:
            matches = len(pattern.findall(code))
            if matches > best_score:
                best_score = matches
                best_lang = lang
        return best_lang

    # ─────────────────────────────────────────────────────────
    # プライベートメソッド
    # ─────────────────────────────────────────────────────────

    def _build_review_prompt(self, code: str, language: str) -> str:
        return (
            f"以下の {language} コードをレビューしてください。\n\n"
            "【コード】\n"
            f"```{language}\n{code}\n```\n\n"
            "以下の形式で出力してください（各セクションのヘッダーを正確に守ること）:\n\n"
            "## 問題点\n"
            "- 問題1\n"
            "- 問題2\n\n"
            "## 改善提案\n"
            "- 提案1\n"
            "- 提案2\n\n"
            "## 修正済みコード\n"
            f"```{language}\n"
            "(修正済みコードをここに記述)\n"
            "```\n\n"
            "## 総評\n"
            "(総評テキスト)"
        )

    def _parse_review_response(self, raw: str, language: str) -> ReviewResult:
        """LLM の応答を ReviewResult にパースする。"""

        def _extract_section(header: str) -> str:
            pattern = re.compile(
                rf"##\s*{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)",
                re.DOTALL,
            )
            m = pattern.search(raw)
            return m.group(1).strip() if m else ""

        def _extract_bullets(text: str) -> list[str]:
            lines = []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith(("-", "*", "・", "•")):
                    lines.append(re.sub(r"^[-\*・•]\s*", "", line).strip())
                elif line and not line.startswith("#"):
                    lines.append(line)
            return [l for l in lines if l]

        def _extract_code_block(text: str) -> str:
            # ```lang ... ``` を抽出
            m = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
            if m:
                return m.group(1).strip()
            # コードブロックが見つからなければテキストをそのまま返す
            return text.strip()

        issues_text = _extract_section("問題点")
        suggestions_text = _extract_section("改善提案")
        fixed_section = _extract_section("修正済みコード")
        summary = _extract_section("総評")

        issues = _extract_bullets(issues_text)
        suggestions = _extract_bullets(suggestions_text)
        fixed_code = _extract_code_block(fixed_section) if fixed_section else ""

        if not summary:
            summary = "レビューが完了しました。"

        return ReviewResult(
            issues=issues,
            suggestions=suggestions,
            fixed_code=fixed_code,
            summary=summary,
            language=language,
        )

    def _save_pattern(
        self, language: str, issue_count: int, suggestion_count: int
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
                "language": language,
                "issue_count": issue_count,
                "suggestion_count": suggestion_count,
            }
        )
        patterns = patterns[-100:]
        try:
            with open(self._patterns_path, "w", encoding="utf-8") as f:
                json.dump(patterns, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("[CodeReviewer] パターン保存失敗: %s", exc)
