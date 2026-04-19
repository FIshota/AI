"""
ニュースブリーフィングエンジン（Sprint 3-G）
指定キーワードの最新ニュースを収集・要約する。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_KEYWORDS_FILE = "data/news_keywords.json"
_DEFAULT_KEYWORDS: list[str] = ["AI", "テクノロジー", "日本"]
_MAX_HEADLINES = 10   # RSS から取得する最大件数


class NewsBriefing:
    """指定キーワードの最新ニュースを収集・要約。"""

    def __init__(self, base_dir: Path, llm_fn: Callable[[str], str]) -> None:
        self._base_dir = Path(base_dir)
        self._llm_fn = llm_fn
        self._keywords_path = self._base_dir / _KEYWORDS_FILE
        self._keywords_path.parent.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def get_briefing(self, keywords: list[str] | None = None) -> str:
        """
        NHK RSS + web_fetcher の get_news_headlines を使用してニュースを取得。
        キーワードでフィルタして要約し「今日のニュースをまとめると...」形式で返す。
        """
        try:
            active_keywords = keywords if keywords is not None else self._load_keywords()

            from core.web_fetcher import get_news_headlines

            headlines = get_news_headlines(n=_MAX_HEADLINES)
            if not headlines:
                return "今日のニュース、取得できなかったよ。ネット接続を確認してみてね💦"

            # キーワードフィルタ（大文字小文字不問）
            if active_keywords:
                filtered = [
                    h for h in headlines
                    if any(kw.lower() in h.lower() for kw in active_keywords)
                ]
                # フィルタ後に 0 件ならフィルタなしで全件使用
                if not filtered:
                    filtered = headlines
            else:
                filtered = headlines

            headline_text = "\n".join(f"・{h}" for h in filtered[:5])
            prompt = (
                "以下のニュース見出しを、アイちゃんとして親しみやすく簡潔にまとめてください。"
                "「今日のニュースをまとめると...」で始めてください（3〜4文）。\n\n"
                f"見出し:\n{headline_text}"
            )
            try:
                return self._llm_fn(prompt)
            except Exception:
                return f"今日のニュースをまとめると…\n{headline_text}"

        except ImportError:
            logger.warning("[NewsBriefing] web_fetcher が見つからない")
            return "ニュース取得モジュールが読み込めなかったよ💦"
        except Exception as e:
            logger.warning("[NewsBriefing] get_briefing error: %s", e)
            return "ニュースの取得中にエラーが発生しちゃった。ごめんね💦"

    def add_keyword(self, keyword: str) -> None:
        """キーワードを追加する。"""
        try:
            kws = self._load_keywords()
            if keyword not in kws:
                kws.append(keyword)
                self._save_keywords(kws)
                logger.info("[NewsBriefing] キーワード追加: %s", keyword)
        except Exception as e:
            logger.warning("[NewsBriefing] add_keyword error: %s", e)

    def remove_keyword(self, keyword: str) -> None:
        """キーワードを削除する。"""
        try:
            kws = self._load_keywords()
            if keyword in kws:
                kws.remove(keyword)
                self._save_keywords(kws)
                logger.info("[NewsBriefing] キーワード削除: %s", keyword)
        except Exception as e:
            logger.warning("[NewsBriefing] remove_keyword error: %s", e)

    def get_keywords(self) -> list[str]:
        """現在のキーワード一覧を返す。"""
        return self._load_keywords()

    # ──────────────────────────────────────────────────────────────
    # 内部ヘルパー
    # ──────────────────────────────────────────────────────────────

    def _load_keywords(self) -> list[str]:
        if self._keywords_path.exists():
            try:
                return json.loads(self._keywords_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        # デフォルトを初期化
        self._save_keywords(_DEFAULT_KEYWORDS)
        return list(_DEFAULT_KEYWORDS)

    def _save_keywords(self, keywords: list[str]) -> None:
        self._keywords_path.write_text(
            json.dumps(keywords, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
