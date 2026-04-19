"""
メモリコンテキストビルダー
LLM へ渡すシステムプロンプトと記憶コンテキストの組み立てを担当します。
"""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ai_chan import AiChan

logger = logging.getLogger(__name__)


class MemoryContextBuilder:
    """
    ユーザープロファイル・記憶検索・気分ヒント・フォローアップ等を
    集約して LLM 用のコンテキスト文字列を組み立てる。
    """

    def __init__(self, ai: AiChan) -> None:
        self.ai = ai
        self._sys_prompt_cache: str = ""
        self._sys_prompt_cache_key: tuple[str, ...] = ("",) * 4
        self._mem_ctx_cache: str = ""
        self._mem_ctx_turn: int = 0

    # ──────────────────────────────────────────────────────────
    # システムプロンプト組み立て
    # ──────────────────────────────────────────────────────────

    def build_system_prompt(self) -> str:
        """
        ユーザーの名前・呼び方をシステムプロンプト本体に直接埋め込む。
        「あなた」と登録名が同一人物であることを明示し、俯瞰視点を防ぐ。

        脊髄反射パターン: プロフィールが変わるまでキャッシュを再利用。
        """
        ai = self.ai
        profile = ai.memory.get_all_user_profile()
        profile_key = (
            profile.get("呼び方", ""),
            profile.get("auto:呼び方", ""),
            profile.get("名前", ""),
            profile.get("auto:名前", ""),
        )

        # モードをキャッシュキーに含める
        _mode = getattr(ai, "mode_manager", None)
        _current_mode = _mode.current_mode if _mode else "family"
        full_key = profile_key + (_current_mode,)

        # キャッシュヒット
        if self._sys_prompt_cache and self._sys_prompt_cache_key == full_key:
            return self._sys_prompt_cache

        base = ai.persona["personality"]["system_prompt"]

        call_name = profile_key[0] or profile_key[1] or profile_key[2] or profile_key[3] or ""
        full_name = profile_key[2] or profile_key[3] or ""

        if call_name:
            lines = [
                f"\n今話している「あなた」は「{call_name}」のこと。",
                f"「あなた」と「{call_name}」は同じ一人の人。呼ぶときは必ず「{call_name}」と呼んで。",
            ]
            if full_name and full_name != call_name:
                lines.append(f"フルネームは「{full_name}」。")
            base = base + "".join(lines)

        # モードに応じたシステムプロンプト補足
        mode_mgr = getattr(ai, "mode_manager", None)
        if mode_mgr and mode_mgr.current_mode == "agent":
            base = base + "\n今はお仕事モードです。効率的で簡潔な応答を心がけて。感情表現は控えめに。"
        elif mode_mgr and mode_mgr.current_mode == "learning":
            base = base + "\n今は学習モードです。一緒に考える姿勢で、わかりやすく教えて。"
        elif mode_mgr and mode_mgr.current_mode == "creative":
            base = base + "\n今は創作モードです。自由な発想で楽しくアイデアを出して。"

        self._sys_prompt_cache = base
        self._sys_prompt_cache_key = full_key
        return base

    # ──────────────────────────────────────────────────────────
    # 話題要約の注入 (Item #71)
    # ──────────────────────────────────────────────────────────

    def _build_topic_summary_hint(self) -> str:
        """直近の主要トピックを要約してシステムプロンプトに添える"""
        ai = self.ai
        tracker = getattr(ai, "topic_tracker", None)
        if tracker is None:
            return ""
        try:
            recent = getattr(tracker, "topics", [])[-10:]
            if not recent:
                return ""
            unique = list(dict.fromkeys(
                t.get("text", "")[:15] if isinstance(t, dict) else str(t)[:15]
                for t in recent
            ))[:5]
            if unique:
                return "最近の話題：" + "、".join(unique) + "。"
        except Exception:
            pass
        return ""

    # ──────────────────────────────────────────────────────────
    # 記憶コンテキスト組み立て
    # ──────────────────────────────────────────────────────────

    def build_memory_context(self, user_input: str) -> str:
        """
        LLM のシステムプロンプトに追記する自然な日本語指示文を生成する。
        括弧・記号などの特殊表記は使わず、通常の指示文として書く。

        脊髄反射パターン: 2ターン以内で同トピックなら重い検索をスキップし
        キャッシュされたコンテキストを再利用。
        """
        ai = self.ai

        # フォローアップ保留をリセット
        ai._pending_followup_topic = None

        # ── キャッシュ判定 ──
        if (len(user_input) <= 5
                and self._mem_ctx_cache
                and self._mem_ctx_turn >= ai.turn_count - 2):
            return self._mem_ctx_cache

        parts: list[str] = []

        # ── 今日の日付（LLM の日付感覚を正しくする） ──
        from datetime import datetime as _dt
        parts.append(f"今日は{_dt.now().strftime('%Y年%m月%d日')}。")

        # ── ユーザープロファイル（重複排除・auto:プレフィックス除去） ──
        profile = ai.memory.get_all_user_profile()
        if profile:
            clean: dict[str, str] = {}
            for k, v in profile.items():
                if k.startswith("auto:"):
                    bare = k[5:]
                    if bare not in clean:
                        clean[bare] = v
                else:
                    clean[k] = v
            items = list(clean.items())[:4]
            desc = "、".join(f"{k}は{v}" for k, v in items)
            parts.append(f"ユーザーの{desc}。")

        # ── 関連記憶の自動検索 ──
        try:
            related = ai._search_relevant_memories(user_input, limit=3)
            if related:
                _now_ts = _time.time()

                def _mem_score(m):
                    imp = getattr(m, "importance", 0.5)
                    try:
                        acc = datetime.strptime(m.accessed_at, "%Y-%m-%d %H:%M").timestamp()
                        recency = max(0.0, 1.0 - (_now_ts - acc) / (86400 * 30))
                    except Exception:
                        recency = 0.3
                    return imp * 0.6 + recency * 0.4

                ranked = sorted(related, key=_mem_score, reverse=True)[:2]
                snippets = [m.content[:40].replace("\n", " ") for m in ranked]
                parts.append("関連する過去の記憶：" + "／".join(snippets) + "。")
        except Exception:
            pass

        # ── 気分ヒント ──
        from core.emotion import MoodAnalyzer
        mood_info = MoodAnalyzer.analyze(user_input)
        if mood_info["hint"]:
            hint = mood_info["hint"]
            if "→" in hint:
                parts.append(hint.split("→")[-1].strip() + "。")
            else:
                parts.append(hint + "。")

        # ── フォローアップ（前の話の続きを自然に振る） ──
        followup = ai.topic_tracker.get_followup_topic(ai.turn_count, min_gap=5)
        if followup:
            brief = followup["text"][:30]
            # 「この間の話の続き」感を出す。唐突に質問するのではなく、
            # 前に話してた話題を自然に再開する形で振る。
            parts.append(
                f"前に「{brief}」という話をしてた。"
                "話の流れに合えば「そういえばこの間の話だけど」みたいに自然に続きを振って。"
                "流れに合わなければ触れなくていい。"
            )
            ai._pending_followup_topic = followup

        # ── 天気・ニュース（ネットワーク許可時、5ターンに1回） ──
        if ai._allow_network and ai.turn_count % 5 == 1:
            try:
                from core.web_fetcher import build_weather_hint, build_news_hint
                w_hint = build_weather_hint(ai._weather_city)
                if w_hint:
                    parts.append(f"今日の{w_hint}。")
                elif ai.turn_count % 15 == 1:
                    n_hint = build_news_hint()
                    if n_hint:
                        parts.append(f"最近のニュース：{n_hint[:40]}。")
            except Exception:
                pass

        # ── バッテリー警告（20ターンに1回） ──
        if ai.turn_count % 20 == 1:
            try:
                from core.battery_monitor import get_battery_hint
                batt_hint = get_battery_hint()
                if batt_hint:
                    parts.append(batt_hint)
            except Exception:
                pass

        # ── カレンダー（10ターンに1回） ──
        if ai.turn_count % 10 == 1:
            try:
                from core.calendar_reader import build_calendar_hint
                cal_hint = build_calendar_hint(days=1)
                if cal_hint:
                    parts.append(cal_hint + "。")
            except Exception:
                pass

        # ── 直近の応答を繰り返さないよう指示 ──
        if len(ai.conversation_history) >= 4:
            parts.append("直前と同じ言い回しを繰り返さず、新鮮な表現で答えて。")

        # ─── モード別コンテキスト ───
        mode_mgr = getattr(ai, "mode_manager", None)
        if mode_mgr:
            current = mode_mgr.current_mode
            if current != "family":
                mode_labels = {
                    "agent": "今はお仕事モード。効率的に作業を支援して。",
                    "learning": "今は学習モード。一緒に学ぶ姿勢で。",
                    "creative": "今は創作モード。自由に発想して。",
                }
                label = mode_labels.get(current, "")
                if label:
                    parts.append(label)

        result = "".join(parts)[:250]
        self._mem_ctx_cache = result
        self._mem_ctx_turn = ai.turn_count
        return result
