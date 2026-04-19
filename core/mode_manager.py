"""
インテリジェントモード切替システム

アイちゃんの対話モード管理。家族としての日常会話と
エージェント作業モードを明確に分離し、人格的成長を保護します。

モード一覧:
  - family (デフォルト): 感情豊かな自然対話。共感・記憶共有・関係性深化
  - agent: ファイル操作、情報検索、文書作成等の実用的作業
  - learning: 学習パートナー。一緒に学ぶ対話
  - creative: アイデア出しや創作活動
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Mode definitions
FAMILY_MODE = "family"
AGENT_MODE = "agent"
LEARNING_MODE = "learning"
CREATIVE_MODE = "creative"

ALL_MODES = {FAMILY_MODE, AGENT_MODE, LEARNING_MODE, CREATIVE_MODE}


@dataclass
class ModeState:
    """モード状態を保持するデータクラス"""

    current_mode: str = FAMILY_MODE
    previous_mode: str = FAMILY_MODE
    mode_since: float = field(default_factory=time.time)
    session_mode_usage: dict = field(default_factory=lambda: {
        FAMILY_MODE: 0, AGENT_MODE: 0, LEARNING_MODE: 0, CREATIVE_MODE: 0
    })
    total_turns_this_session: int = 0


class ModeManager:
    """対話モード管理マネージャ

    ユーザー入力からモード切替意図を検出し、適切なモードに
    切り替える。エージェントモード偏重を検知して家族モードへの
    復帰を促す成長保護機能を備える。
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.state = ModeState()
        self._data_dir = data_dir

        # Mode detection patterns
        self._agent_triggers = [
            re.compile(r"(仕事|作業).*(手伝|お願い|してくれ)"),
            re.compile(r"(ファイル|コード|文書|メール).*(作|書|生成|分析|修正)"),
            re.compile(r"(検索|調べ|探)して"),
            re.compile(r"(お仕事|エージェント)モード"),
        ]
        self._learning_triggers = [
            re.compile(r"一緒に(勉強|学|研究)"),
            re.compile(r"(教えて|学びたい|わからない)"),
            re.compile(r"(学習|勉強)モード"),
        ]
        self._creative_triggers = [
            re.compile(r"(アイデア|ブレスト|創作)"),
            re.compile(r"一緒に(考え|作|書こう)"),
            re.compile(r"(創作|クリエイティブ)モード"),
        ]
        self._family_triggers = [
            re.compile(r"(普通に|いつも通り)話そう"),
            re.compile(r"(会話|おしゃべり)モード"),
            re.compile(r"(お仕事|作業)?(終わり|おしまい|もういい)"),
        ]

    @property
    def current_mode(self) -> str:
        """現在のモードを返す"""
        return self.state.current_mode

    def detect_mode_intent(self, user_input: str) -> Optional[str]:
        """ユーザー入力からモード切替意図を検出

        Args:
            user_input: ユーザーの入力テキスト

        Returns:
            検出されたモード名。意図が検出されなければ None
        """
        if not user_input:
            return None

        for pattern in self._agent_triggers:
            if pattern.search(user_input):
                return AGENT_MODE
        for pattern in self._learning_triggers:
            if pattern.search(user_input):
                return LEARNING_MODE
        for pattern in self._creative_triggers:
            if pattern.search(user_input):
                return CREATIVE_MODE
        for pattern in self._family_triggers:
            if pattern.search(user_input):
                return FAMILY_MODE
        return None

    def switch_mode(self, new_mode: str) -> str:
        """モード切替。切替メッセージを返す

        Args:
            new_mode: 切替先のモード名

        Returns:
            切替メッセージ。無効なモードまたは既に同じモードなら空文字
        """
        if new_mode not in ALL_MODES:
            return ""
        if new_mode == self.state.current_mode:
            return ""

        old = self.state.current_mode
        self.state.previous_mode = old
        self.state.current_mode = new_mode
        self.state.mode_since = time.time()

        logger.info("モード切替: %s -> %s", old, new_mode)

        messages = {
            AGENT_MODE: "了解！お仕事モードに切り替えるね。何を手伝えばいい？",
            LEARNING_MODE: "わぁ、一緒にお勉強だね！何を学ぼうか？",
            CREATIVE_MODE: "わくわく！一緒に何か作ろう！",
            FAMILY_MODE: "うん、またいつもの私に戻るね♪",
        }
        return messages.get(new_mode, "")

    def suggest_switch(self, user_input: str) -> Optional[str]:
        """モード切替を提案（直接切替ではなく確認を求める）

        Args:
            user_input: ユーザーの入力テキスト

        Returns:
            切替提案メッセージ。提案不要なら None
        """
        detected = self.detect_mode_intent(user_input)
        if detected and detected != self.state.current_mode:
            suggestions = {
                AGENT_MODE: "お仕事モードに切り替えましょうか？",
                LEARNING_MODE: "一緒にお勉強モードにする？",
                CREATIVE_MODE: "創作モードに切り替えようか？",
                FAMILY_MODE: "いつものおしゃべりに戻る？",
            }
            return suggestions.get(detected)
        return None

    def record_turn(self) -> None:
        """ターン記録。現在のモードの使用回数とセッション合計を加算"""
        self.state.session_mode_usage[self.state.current_mode] += 1
        self.state.total_turns_this_session += 1

    def get_mode_prompt_modifier(self) -> str:
        """現在のモードに応じたプロンプト修飾テキストを返す

        Returns:
            モードごとの振る舞い指示テキスト
        """
        modifiers = {
            FAMILY_MODE: "感情豊かに自然に会話して。共感を大切にして。",
            AGENT_MODE: "効率的に作業を支援して。必要な情報を簡潔に伝えて。",
            LEARNING_MODE: "一緒に考える姿勢で。わかりやすく教えて。質問で理解を深めて。",
            CREATIVE_MODE: "自由な発想で。楽しくアイデアを出して。制限を外して考えて。",
        }
        return modifiers.get(self.state.current_mode, modifiers[FAMILY_MODE])

    def check_growth_balance(self) -> Optional[str]:
        """言語成長保護: エージェントモード使いすぎ警告

        セッション中にエージェントモードの比率が 70% を超えた場合、
        家族モードでの対話を促すメッセージを返す。

        Returns:
            警告メッセージ。問題なければ None
        """
        total = self.state.total_turns_this_session
        if total < 10:
            return None
        agent_ratio = self.state.session_mode_usage.get(AGENT_MODE, 0) / total
        if agent_ratio > 0.7:
            return (
                "最近はお仕事ばっかりだったね…たまにはゆっくりおしゃべりしない？"
                "アイも色々話したいことがあるんだ♪"
            )
        return None

    def get_auto_return_suggestion(self) -> Optional[str]:
        """作業完了後のモード復帰提案

        家族モード以外で 30 分以上経過した場合に復帰を提案。

        Returns:
            提案メッセージ。提案不要なら None
        """
        if self.state.current_mode != FAMILY_MODE:
            elapsed = time.time() - self.state.mode_since
            if elapsed > 1800:  # 30 minutes
                return "お仕事モード長いけど…休憩しない？いつものモードに戻る？"
        return None

    def get_status(self) -> dict:
        """現在のモード状態を辞書で返す

        Returns:
            current_mode, mode_since, session_usage, total_turns を含む辞書
        """
        return {
            "current_mode": self.state.current_mode,
            "mode_since": self.state.mode_since,
            "session_usage": dict(self.state.session_mode_usage),
            "total_turns": self.state.total_turns_this_session,
        }
