"""
Sprint 3・4 機能の統合ハンドラ。
ai_chan.py からインポートして使う。

使い方:
    from core.sprint34_handlers import Sprint34Handler
    handler = Sprint34Handler(base_dir, llm_fn, emotion_engine, research_agent)
    result = handler.handle(user_input, emotion_state)
    if result is not None:
        # Sprint 3/4 の機能が処理した
        reply = result
    else:
        # 通常の会話フローへ
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

from core.bgm_suggester import BGMSuggester
from core.clipboard_assistant import ClipboardAssistant
from core.competitor_analyzer import CompetitorAnalyzer
from core.multi_agent import MultiAgent
from core.news_briefing import NewsBriefing
from core.schedule_announcer import ScheduleAnnouncer

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# コマンドパターン
# ──────────────────────────────────────────────────────────────────────

CMD_NEWS = re.compile(
    r"^(今日の?)?(ニュース|最新情報)(教えて|見せて|まとめて)?$"
)
CMD_SCHEDULE = re.compile(
    r"^(今日の?)?(予定|スケジュール)(教えて|確認|ある)?$"
)
CMD_COMPETITOR = re.compile(
    r"^(.+)(の?)?(競合|ライバル)(を?)(調べて|分析して|教えて)$"
)
CMD_BGM = re.compile(
    r"^(BGM|音楽|曲)(教えて|おすすめ|かけて)?$"
)
CMD_CLIPBOARD = re.compile(
    r"^(クリップボード|コピーしたもの)(を?)(要約|翻訳|レビュー|添削)(して|くれ)?$"
)

# キーワードコマンドパターン（CMD_NEWS 等に合わない文でも反応させる）
CMD_NEWS_KEYWORD = re.compile(r"(ニュース|最新情報).{0,6}(教えて|まとめて|見せて)")
CMD_SCHEDULE_KEYWORD = re.compile(r"(今日の?(予定|スケジュール)|スケジュール.{0,4}確認|予定.{0,4}教えて)")
CMD_BGM_KEYWORD = re.compile(r"(BGM|音楽|曲).{0,6}(教えて|おすすめ|かけて|提案)")
CMD_COMPETITOR_KEYWORD = re.compile(r"(.{1,20})(の)?(競合|ライバル).{0,6}(調べて|分析|教えて)")
CMD_CLIPBOARD_KEYWORD = re.compile(
    r"(クリップボード|コピーしたもの|コピー内容).{0,4}(要約|翻訳|レビュー|添削)"
)


class Sprint34Handler:
    """Sprint 3・4 機能をまとめたハンドラクラス。"""

    def __init__(
        self,
        base_dir: Path,
        llm_fn: Callable[[str], str],
        emotion_engine=None,
        research_agent=None,
    ) -> None:
        base_dir = Path(base_dir)
        self.clipboard = ClipboardAssistant(base_dir, llm_fn)
        self.schedule = ScheduleAnnouncer(base_dir, llm_fn)
        self.news = NewsBriefing(base_dir, llm_fn)
        self.competitor = CompetitorAnalyzer(base_dir, llm_fn, research_agent)
        self.bgm = BGMSuggester()
        self.multi = MultiAgent(base_dir, llm_fn, {})
        self._emotion_engine = emotion_engine
        self._llm_fn = llm_fn

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def handle(
        self,
        user_input: str,
        emotion_state: dict | None = None,
    ) -> str | None:
        """
        各コマンドを検出して対応するエージェントを呼び出す。
        処理できなければ None を返す（通常の会話フローへ）。
        """
        try:
            stripped = user_input.strip()

            # ─── ニュース ──────────────────────────────────────────
            if CMD_NEWS.match(stripped) or CMD_NEWS_KEYWORD.search(stripped):
                return self._handle_news(stripped)

            # ─── スケジュール ──────────────────────────────────────
            if CMD_SCHEDULE.match(stripped) or CMD_SCHEDULE_KEYWORD.search(stripped):
                return self._handle_schedule()

            # ─── 競合分析 ──────────────────────────────────────────
            m = CMD_COMPETITOR.match(stripped) or CMD_COMPETITOR_KEYWORD.search(stripped)
            if m:
                # group(1) が「Googleの」のように助詞付きになるため末尾の「の」を除去
                target = m.group(1).strip().rstrip("の")
                if target:
                    return self._handle_competitor(target)

            # ─── BGM ───────────────────────────────────────────────
            if CMD_BGM.match(stripped) or CMD_BGM_KEYWORD.search(stripped):
                return self._handle_bgm(emotion_state)

            # ─── クリップボード操作 ────────────────────────────────
            m_cb = CMD_CLIPBOARD.match(stripped) or CMD_CLIPBOARD_KEYWORD.search(stripped)
            if m_cb:
                return self._handle_clipboard(stripped)

        except Exception as e:
            logger.warning("[Sprint34Handler] handle error: %s", e)

        return None  # 通常の会話フローへ

    def announce_schedule_if_needed(self) -> str | None:
        """
        起動時に呼び出す。should_announce() が True なら今日の予定を返す。
        """
        try:
            if self.schedule.should_announce():
                summary = self.schedule.get_today_summary()
                self.schedule.mark_announced()
                return summary
        except Exception as e:
            logger.warning("[Sprint34Handler] announce_schedule_if_needed error: %s", e)
        return None

    # ──────────────────────────────────────────────────────────────
    # 内部ハンドラ
    # ──────────────────────────────────────────────────────────────

    def _handle_news(self, user_input: str) -> str:
        """ニュースブリーフィングを返す。"""
        try:
            return self.news.get_briefing()
        except Exception as e:
            logger.warning("[Sprint34Handler] _handle_news error: %s", e)
            return "ニュースの取得中にエラーが発生しちゃった。ごめんね💦"

    def _handle_schedule(self) -> str:
        """今日のスケジュールサマリーを返す。"""
        try:
            return self.schedule.get_today_summary()
        except Exception as e:
            logger.warning("[Sprint34Handler] _handle_schedule error: %s", e)
            return "予定の取得中にエラーが発生しちゃった。ごめんね💦"

    def _handle_competitor(self, target: str) -> str:
        """競合分析レポートを生成して結果メッセージを返す。"""
        try:
            report = self.competitor.analyze(target)
            return report.message
        except Exception as e:
            logger.warning("[Sprint34Handler] _handle_competitor error: %s", e)
            return f"競合分析中にエラーが発生しちゃった: {e}"

    def _handle_bgm(self, emotion_state: dict | None) -> str:
        """BGM 提案を返す。"""
        try:
            # emotion_engine から最新の感情状態を取得
            if emotion_state is None and self._emotion_engine is not None:
                try:
                    state_obj = self._emotion_engine.state
                    emotion_state = (
                        state_obj.to_dict()
                        if hasattr(state_obj, "to_dict")
                        else vars(state_obj)
                    )
                except Exception:
                    emotion_state = {}

            suggestion = self.bgm.suggest(emotion_state or {})
            return (
                f"{suggestion.message}\n"
                f"「{suggestion.playlist_name}」で検索したよ：\n"
                f"{suggestion.youtube_url}"
            )
        except Exception as e:
            logger.warning("[Sprint34Handler] _handle_bgm error: %s", e)
            return "BGM の提案中にエラーが発生しちゃった。ごめんね💦"

    def _handle_clipboard(self, user_input: str) -> str:
        """クリップボード操作コマンドを処理する。"""
        try:
            # macOS クリップボードを読む
            import subprocess
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=3
            )
            text = result.stdout.strip()
            if not text:
                return "クリップボードが空みたいだよ。先にテキストをコピーしてね😊"

            if "要約" in user_input:
                return self.clipboard.summarize(text)
            if "翻訳" in user_input:
                return self.clipboard.translate_to_ja(text)
            if "レビュー" in user_input:
                return self.clipboard.review_code(text)
            if "添削" in user_input:
                return self.clipboard.proofread(text)

            # 種類を判別して提案
            return self.clipboard.process_clipboard(text)

        except FileNotFoundError:
            # pbpaste が使えない環境（non-macOS）
            return "クリップボードの読み取りは macOS でのみ対応しているよ💦"
        except Exception as e:
            logger.warning("[Sprint34Handler] _handle_clipboard error: %s", e)
            return "クリップボードの処理中にエラーが発生しちゃった。ごめんね💦"
