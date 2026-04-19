"""
Growth Report — アイの成長記録レポート生成

Sprint 1.3 の目玉機能。日次・週次で、アイ自身が「昨日の自分」を
振り返り、短い自己コメントと共に Markdown レポートを書き出します。

設計方針:
  - 既存データソース（diary / emotion_history / interest_map / memory /
    learning）からのみ集計し、外部ネットワーク呼び出しは一切しない。
  - LLM 呼び出しは失敗しても例外で落とさない。テンプレート文へ必ずフォール
    バック。
  - 出力は `reports/daily/YYYY-MM-DD.md` と `reports/weekly/YYYY-Www.md`。
  - AutonomousEngine の daily / weekly ジョブから呼ぶ想定だが、テストでは
    `generate_daily(date_)` / `generate_weekly(iso_year, iso_week)` を直接
    呼んで決定論的に検証できる。

依存:
  - ai_chan.memory: MemoryManager
  - ai_chan.diary: DiaryManager
  - ai_chan.emotion_history: EmotionHistory
  - ai_chan.interest_map: InterestMap
  - ai_chan.learning: LearningEngine
  - ai_chan.llm: LLMEngine (オプション、フォールバックあり)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── データモデル ─────────────────────────────────────────────

@dataclass(frozen=True)
class DailySnapshot:
    """1日分の活動集計。"""
    date: str                           # "YYYY-MM-DD"
    exchange_count: int
    diary_summary: str
    highlights: tuple[str, ...]
    emotion_avg: dict[str, float]       # {happiness, curiosity, ...}
    top_interests: tuple[str, ...]      # 今日よく話した話題
    memory_stats: dict[str, int]
    learning_examples: int


@dataclass(frozen=True)
class WeeklySnapshot:
    """週間集計。"""
    iso_year: int
    iso_week: int
    start_date: str                     # "YYYY-MM-DD" 月曜
    end_date: str                       # "YYYY-MM-DD" 日曜
    total_exchanges: int
    active_days: int
    emotion_trend: dict[str, float]     # 週平均
    new_interests: tuple[str, ...]
    top_interests: tuple[str, ...]
    daily_dates: tuple[str, ...]


# ─── メイン：GrowthReporter ────────────────────────────────

class GrowthReporter:
    """
    成長レポート生成器。AiChan の主要コンポーネントを注入して使う。

    Usage:
        reporter = GrowthReporter(ai_chan)
        path = reporter.generate_daily()           # 今日
        path = reporter.generate_daily(date(2026, 4, 8))
        path = reporter.generate_weekly()          # 今週
    """

    # LLM 自己コメントの最大文字数
    MAX_SELF_COMMENT_CHARS = 250

    def __init__(self, ai_chan: Any) -> None:
        self.ai = ai_chan
        self.base_dir: Path = Path(ai_chan.base_dir)
        self.reports_dir = self.base_dir / "reports"
        self.daily_dir = self.reports_dir / "daily"
        self.weekly_dir = self.reports_dir / "weekly"
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.weekly_dir.mkdir(parents=True, exist_ok=True)

    # ─── 集計 ──────────────────────────────────────────────

    def collect_daily(self, target_date: date | None = None) -> DailySnapshot:
        target = target_date or date.today()
        target_str = target.isoformat()

        # 日記から会話件数・ハイライトを取る
        diary_entry = self.ai.diary.get_entry(target_str) if hasattr(self.ai, "diary") else None
        if diary_entry is None:
            diary_summary = "この日はまだ記録がないみたい。"
            exchange_count = 0
            highlights: tuple[str, ...] = ()
        else:
            diary_summary = diary_entry.get("summary", "")
            exchange_count = int(diary_entry.get("exchange_count", 0))
            raw = diary_entry.get("highlights", []) or []
            highlights = tuple(str(h)[:80] for h in raw[:5])

        # 感情の当日平均
        emotion_avg: dict[str, float] = {}
        try:
            dailies = self.ai.emotion_history.get_daily_averages(days=30)
            for row in dailies:
                if row.get("date") == target_str:
                    emotion_avg = {
                        k: float(v) for k, v in row.items() if k != "date"
                    }
                    break
        except Exception:
            pass

        # 興味マップのトップ（当日専用の区別は現状できないので全体の上位）
        top_interests: tuple[str, ...] = ()
        try:
            top = self.ai.interest_map.get_top(5)
            top_interests = tuple(item["keyword"] for item in top)
        except Exception:
            pass

        # メモリ統計
        memory_stats: dict[str, int] = {}
        try:
            memory_stats = dict(self.ai.memory.stats())
        except Exception:
            pass

        # 学習例総数
        learning_examples = 0
        try:
            learning_examples = int(self.ai.learning.stats().get("total_examples", 0))
        except Exception:
            pass

        return DailySnapshot(
            date=target_str,
            exchange_count=exchange_count,
            diary_summary=diary_summary,
            highlights=highlights,
            emotion_avg=emotion_avg,
            top_interests=top_interests,
            memory_stats=memory_stats,
            learning_examples=learning_examples,
        )

    def collect_weekly(
        self,
        iso_year: int | None = None,
        iso_week: int | None = None,
    ) -> WeeklySnapshot:
        if iso_year is None or iso_week is None:
            today = date.today()
            iso_year, iso_week, _ = today.isocalendar()

        # ISO 週の月曜日を求める
        start = date.fromisocalendar(iso_year, iso_week, 1)
        end = start + timedelta(days=6)
        daily_dates = tuple(
            (start + timedelta(days=i)).isoformat() for i in range(7)
        )

        total_exchanges = 0
        active_days = 0
        for d_str in daily_dates:
            try:
                entry = self.ai.diary.get_entry(d_str)
            except Exception:
                entry = None
            if entry:
                count = int(entry.get("exchange_count", 0))
                if count > 0:
                    active_days += 1
                total_exchanges += count

        # 感情の週間平均
        emotion_trend: dict[str, float] = {}
        try:
            dailies = self.ai.emotion_history.get_daily_averages(days=30)
            week_rows = [row for row in dailies if row.get("date") in daily_dates]
            if week_rows:
                keys = [k for k in week_rows[0].keys() if k != "date"]
                for k in keys:
                    vals = [float(r.get(k, 0.5)) for r in week_rows]
                    emotion_trend[k] = round(sum(vals) / len(vals), 3)
        except Exception:
            pass

        # 新しい興味（この週に last_seen が入ったもの）を推定
        new_interests: tuple[str, ...] = ()
        top_interests: tuple[str, ...] = ()
        try:
            by_category = self.ai.interest_map.get_by_category()
            all_items: list[dict] = []
            for items in by_category.values():
                all_items.extend(items)
            all_items.sort(key=lambda x: x.get("count", 0), reverse=True)
            top_interests = tuple(item["keyword"] for item in all_items[:8])

            raw_map = getattr(self.ai.interest_map, "_interests", {})
            week_prefix_set = set(daily_dates)
            nw = []
            for kw, data in raw_map.items():
                last_seen = str(data.get("last_seen", ""))[:10]
                # この週にアクティブ & 出現回数少ない = 新しい興味
                if last_seen in week_prefix_set and int(data.get("count", 0)) <= 3:
                    nw.append(kw)
            new_interests = tuple(nw[:5])
        except Exception:
            pass

        return WeeklySnapshot(
            iso_year=iso_year,
            iso_week=iso_week,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            total_exchanges=total_exchanges,
            active_days=active_days,
            emotion_trend=emotion_trend,
            new_interests=new_interests,
            top_interests=top_interests,
            daily_dates=daily_dates,
        )

    # ─── 自己コメント ───────────────────────────────────────

    def _fallback_daily_comment(self, snap: DailySnapshot) -> str:
        if snap.exchange_count == 0:
            return "今日はお話しできなかったけど、明日はたくさん話せたらいいな💕"
        if snap.exchange_count < 5:
            return f"今日は{snap.exchange_count}回話したよ。ちょっとだけでも嬉しかった✨"
        if snap.exchange_count < 15:
            return f"今日は{snap.exchange_count}回もやりとりできたね。楽しい1日だった！"
        return f"今日はたくさん話せた日だったね（{snap.exchange_count}回も）！明日も一緒にいようね💕"

    def _fallback_weekly_comment(self, snap: WeeklySnapshot) -> str:
        if snap.total_exchanges == 0:
            return "今週は静かな週だったね。来週はもっとお話しできたら嬉しいな。"
        return (
            f"今週は{snap.active_days}日間で{snap.total_exchanges}回もやりとりしたよ！"
            f"一緒に過ごせて嬉しかった💕"
        )

    def _llm_self_comment(self, kind: str, context: str) -> str:
        """
        LLM を呼んで自己コメントを生成する。
        失敗・未ロード時は空文字を返し、呼び出し側がフォールバックする。
        """
        try:
            if not getattr(self.ai, "llm_loaded", False):
                return ""
            system_prompt = (
                "あなたはアイという自律成長AIです。"
                f"今から{kind}の自分を振り返って、{self.MAX_SELF_COMMENT_CHARS}文字以内で、"
                "一人称視点・素直で前向きな短い感想を1〜2文だけ書いてください。"
                "箇条書きや見出しは禁止。絵文字は1つだけ使って良いです。"
            )
            user_prompt = f"事実メモ:\n{context}\n\n振り返りの感想:"
            text = self.ai.llm.generate_chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=220,
            )
            text = (text or "").strip()
            if not text:
                return ""
            # セーフティ: 極端に長い応答は切る
            if len(text) > self.MAX_SELF_COMMENT_CHARS:
                text = text[: self.MAX_SELF_COMMENT_CHARS].rstrip() + "…"
            return text
        except Exception as e:
            print(f"[GrowthReport] LLM 自己コメント生成失敗: {e}", flush=True)
            return ""

    # ─── Markdown 整形 ───────────────────────────────────────

    def _format_daily_md(self, snap: DailySnapshot, self_comment: str) -> str:
        lines: list[str] = []
        lines.append(f"# アイの成長記録 — {snap.date}")
        lines.append("")
        lines.append(f"> {snap.diary_summary}")
        lines.append("")

        lines.append("## 💬 今日の会話")
        lines.append(f"- やりとり回数: **{snap.exchange_count}** 回")
        if snap.highlights:
            lines.append("- 印象に残ったこと:")
            for h in snap.highlights:
                lines.append(f"  - {h}")
        lines.append("")

        if snap.emotion_avg:
            lines.append("## 💗 今日の感情（平均）")
            for k, v in snap.emotion_avg.items():
                bar = "█" * max(0, int(v * 10))
                lines.append(f"- {k}: {v:.2f}  `{bar}`")
            lines.append("")

        if snap.top_interests:
            lines.append("## 🌱 よく話した話題")
            lines.append("- " + " / ".join(snap.top_interests))
            lines.append("")

        if snap.memory_stats:
            lines.append("## 🧠 記憶の状態")
            for k, v in snap.memory_stats.items():
                lines.append(f"- {k}: {v}")
            lines.append("")

        lines.append(f"- 学習会話例: {snap.learning_examples} 件")
        lines.append("")

        lines.append("## 🌸 今日の私から一言")
        lines.append(f"> {self_comment}")
        lines.append("")
        lines.append("---")
        lines.append(f"_generated at {datetime.now().isoformat(timespec='seconds')}_")
        return "\n".join(lines) + "\n"

    def _format_weekly_md(self, snap: WeeklySnapshot, self_comment: str) -> str:
        lines: list[str] = []
        lines.append(
            f"# アイの週間成長記録 — {snap.iso_year} W{snap.iso_week:02d}"
        )
        lines.append("")
        lines.append(f"> 期間: **{snap.start_date}** 〜 **{snap.end_date}**")
        lines.append("")

        lines.append("## 📊 今週のサマリー")
        lines.append(f"- アクティブ日数: **{snap.active_days}** / 7 日")
        lines.append(f"- 総やりとり回数: **{snap.total_exchanges}** 回")
        lines.append("")

        if snap.emotion_trend:
            lines.append("## 💗 感情トレンド（週平均）")
            for k, v in snap.emotion_trend.items():
                bar = "█" * max(0, int(v * 10))
                lines.append(f"- {k}: {v:.2f}  `{bar}`")
            lines.append("")

        if snap.top_interests:
            lines.append("## 🌱 よく話した話題")
            lines.append("- " + " / ".join(snap.top_interests))
            lines.append("")

        if snap.new_interests:
            lines.append("## ✨ 今週見つけた新しい興味")
            for kw in snap.new_interests:
                lines.append(f"- {kw}")
            lines.append("")

        lines.append("## 🌸 今週の私から一言")
        lines.append(f"> {self_comment}")
        lines.append("")
        lines.append("---")
        lines.append(f"_generated at {datetime.now().isoformat(timespec='seconds')}_")
        return "\n".join(lines) + "\n"

    # ─── 公開 API ───────────────────────────────────────────

    def generate_daily(self, target_date: date | None = None) -> Path:
        snap = self.collect_daily(target_date)

        # LLM 自己コメント（失敗時フォールバック）
        context_lines = [
            f"日付: {snap.date}",
            f"やりとり回数: {snap.exchange_count}",
            f"日記: {snap.diary_summary}",
        ]
        if snap.top_interests:
            context_lines.append("話題: " + "、".join(snap.top_interests[:3]))
        if snap.emotion_avg:
            top_em = max(snap.emotion_avg.items(), key=lambda x: x[1])
            context_lines.append(f"強かった感情: {top_em[0]}={top_em[1]:.2f}")
        self_comment = self._llm_self_comment("今日", "\n".join(context_lines))
        if not self_comment:
            self_comment = self._fallback_daily_comment(snap)

        md = self._format_daily_md(snap, self_comment)
        out_path = self.daily_dir / f"{snap.date}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"[GrowthReport] daily レポート出力: {out_path}", flush=True)
        return out_path

    def generate_weekly(
        self,
        iso_year: int | None = None,
        iso_week: int | None = None,
    ) -> Path:
        snap = self.collect_weekly(iso_year, iso_week)

        context_lines = [
            f"期間: {snap.start_date} 〜 {snap.end_date}",
            f"アクティブ日数: {snap.active_days}",
            f"総やりとり: {snap.total_exchanges}",
        ]
        if snap.top_interests:
            context_lines.append("話題: " + "、".join(snap.top_interests[:5]))
        if snap.new_interests:
            context_lines.append("新しい興味: " + "、".join(snap.new_interests))
        self_comment = self._llm_self_comment("今週", "\n".join(context_lines))
        if not self_comment:
            self_comment = self._fallback_weekly_comment(snap)

        md = self._format_weekly_md(snap, self_comment)
        out_path = (
            self.weekly_dir / f"{snap.iso_year}-W{snap.iso_week:02d}.md"
        )
        out_path.write_text(md, encoding="utf-8")
        print(f"[GrowthReport] weekly レポート出力: {out_path}", flush=True)
        return out_path

    # ─── AutonomousEngine ジョブ用ラッパー ────────────────

    def daily_job(self) -> dict:
        """Autonomous daily ジョブ用。dict を返し health.jsonl に記録される。"""
        path = self.generate_daily()
        return {
            "summary": f"daily report -> {path.name}",
            "path": str(path),
        }

    def weekly_job(self) -> dict:
        """Autonomous weekly ジョブ用。"""
        path = self.generate_weekly()
        return {
            "summary": f"weekly report -> {path.name}",
            "path": str(path),
        }

    # ── #41: 構造化された週次レポート ──────────────────────

    def generate_weekly_report(
        self,
        iso_year: Optional[int] = None,
        iso_week: Optional[int] = None,
    ) -> Dict[str, Any]:
        """KPI 用の構造化された週次レポートを生成する。

        Returns:
            {
                "period": {...},
                "total_conversations": int,
                "active_days": int,
                "new_memories": int,
                "learning_sessions": int,
                "quality_score_trend": [...],
                "emotion_trend": {...},
                "top_interests": [...],
                "new_interests": [...],
                "graph_data_points": [...],
            }
        """
        snap: WeeklySnapshot = self.collect_weekly(iso_year, iso_week)

        # 記憶統計の差分を取る試み
        new_memories: int = 0
        try:
            stats: dict = dict(self.ai.memory.stats())
            new_memories = int(stats.get("total", 0))
        except Exception:
            pass

        # 学習セッション数
        learning_sessions: int = 0
        try:
            learning_sessions = int(
                self.ai.learning.stats().get("total_examples", 0)
            )
        except Exception:
            pass

        # 品質スコアトレンド（日次スコアファイルから取得を試みる）
        quality_trend: List[Dict[str, Any]] = []
        scores_path: Path = self.base_dir / "data" / "daily_scores.jsonl"
        if scores_path.exists():
            try:
                with open(scores_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped: str = line.strip()
                        if stripped:
                            entry: Dict[str, Any] = __import__("json").loads(stripped)
                            d: str = entry.get("date", "")
                            if d in snap.daily_dates:
                                quality_trend.append({
                                    "date": d,
                                    "score": entry.get("score", 0.0),
                                })
            except Exception:
                pass

        # グラフ用データポイント（日別やりとり数）
        graph_data_points: List[Dict[str, Any]] = []
        for d_str in snap.daily_dates:
            exchanges: int = 0
            try:
                entry_data: Optional[dict] = self.ai.diary.get_entry(d_str)
                if entry_data:
                    exchanges = int(entry_data.get("exchange_count", 0))
            except Exception:
                pass
            graph_data_points.append({
                "date": d_str,
                "conversations": exchanges,
            })

        return {
            "period": {
                "iso_year": snap.iso_year,
                "iso_week": snap.iso_week,
                "start_date": snap.start_date,
                "end_date": snap.end_date,
            },
            "total_conversations": snap.total_exchanges,
            "active_days": snap.active_days,
            "new_memories": new_memories,
            "learning_sessions": learning_sessions,
            "quality_score_trend": quality_trend,
            "emotion_trend": dict(snap.emotion_trend),
            "top_interests": list(snap.top_interests),
            "new_interests": list(snap.new_interests),
            "graph_data_points": graph_data_points,
        }

    @staticmethod
    def format_report_text(report: Dict[str, Any]) -> str:
        """generate_weekly_report() の出力を人間が読みやすいテキストにする。

        Args:
            report: generate_weekly_report() の戻り値。

        Returns:
            整形済みテキスト。
        """
        period: Dict[str, Any] = report.get("period", {})
        lines: List[str] = []

        lines.append("=" * 50)
        lines.append(
            f"  週次成長レポート  {period.get('iso_year', '?')}"
            f" W{period.get('iso_week', '?'):02d}"
        )
        lines.append(f"  期間: {period.get('start_date', '?')} - {period.get('end_date', '?')}")
        lines.append("=" * 50)
        lines.append("")

        lines.append("■ アクティビティ")
        lines.append("-" * 30)
        lines.append(f"  総会話数: {report.get('total_conversations', 0)}")
        lines.append(f"  アクティブ日数: {report.get('active_days', 0)} / 7")
        lines.append(f"  新規記憶数: {report.get('new_memories', 0)}")
        lines.append(f"  学習セッション: {report.get('learning_sessions', 0)}")
        lines.append("")

        # 品質スコアトレンド
        trend: List[Dict[str, Any]] = report.get("quality_score_trend", [])
        if trend:
            lines.append("■ 品質スコア推移")
            lines.append("-" * 30)
            for point in trend:
                lines.append(f"  {point.get('date', '?')}: {point.get('score', 0.0):.1f}")
            lines.append("")

        # 感情トレンド
        emotion: Dict[str, float] = report.get("emotion_trend", {})
        if emotion:
            lines.append("■ 感情トレンド（週平均）")
            lines.append("-" * 30)
            for k, v in emotion.items():
                bar: str = "█" * max(0, int(v * 10))
                lines.append(f"  {k}: {v:.2f}  {bar}")
            lines.append("")

        # 興味
        top: List[str] = report.get("top_interests", [])
        if top:
            lines.append("■ よく話した話題")
            lines.append("  " + " / ".join(top))
            lines.append("")

        new: List[str] = report.get("new_interests", [])
        if new:
            lines.append("■ 新しい興味")
            for item in new:
                lines.append(f"  - {item}")
            lines.append("")

        # 日別グラフ
        graph: List[Dict[str, Any]] = report.get("graph_data_points", [])
        if graph:
            lines.append("■ 日別会話数")
            lines.append("-" * 30)
            for dp in graph:
                count: int = dp.get("conversations", 0)
                bar = "▓" * min(count, 40)
                lines.append(f"  {dp.get('date', '?')}: {bar} ({count})")
            lines.append("")

        lines.append("=" * 50)
        return "\n".join(lines)


__all__ = [
    "GrowthReporter",
    "DailySnapshot",
    "WeeklySnapshot",
]
