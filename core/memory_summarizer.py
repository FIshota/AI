"""
記憶要約チェーン (Memory Summarizer)
Sprint 3.0-B: 長い会話を自動要約して永続的な「思い出」にする。

- 会話が一定ターンを超えたら自動的に要約
- 要約は長期記憶として保存
- 直近の要約をコンテキストに含めて文脈維持
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm import LLMEngine
    from core.memory import MemoryManager

# 要約トリガーの閾値
SUMMARIZE_THRESHOLD = 16   # メッセージ数（8ターン）
SUMMARY_MAX_CHARS = 200    # 要約の最大文字数


class MemorySummarizer:
    """
    会話が長くなったら自動的に要約して長期記憶に保存する。

    フロー:
    1. 会話履歴が SUMMARIZE_THRESHOLD を超えたら前半を要約
    2. 要約を長期記憶に保存
    3. 会話履歴から要約済み部分を削除
    4. 次の会話時に要約を文脈として注入
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._summaries_path = self._base / "data" / "conversation_summaries.json"
        self._summaries: list[dict] = self._load_summaries()

    # ─── public ──────────────────────────────────────────────

    def should_summarize(self, conversation_history: list[dict]) -> bool:
        """要約すべきかどうか判定する"""
        return len(conversation_history) >= SUMMARIZE_THRESHOLD

    def summarize_and_trim(
        self,
        conversation_history: list[dict],
        llm: "LLMEngine | None" = None,
        memory: "MemoryManager | None" = None,
    ) -> list[dict]:
        """
        会話履歴の前半を要約し、trimされた履歴を返す。
        LLMが使えない場合はルールベースで要約する。

        戻り値: 新しい会話履歴（要約済み部分を除去、直近のみ残す）
        """
        if len(conversation_history) < SUMMARIZE_THRESHOLD:
            return conversation_history

        # 前半（古い部分）と後半（最新部分）に分割
        split_point = len(conversation_history) - 8  # 最新4ターンは残す
        old_messages = conversation_history[:split_point]
        recent_messages = conversation_history[split_point:]

        # 要約を生成
        summary = self._generate_summary(old_messages, llm)
        if not summary:
            return conversation_history  # 要約生成失敗時はそのまま

        # 要約を保存
        summary_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "messages_count": len(old_messages),
            "summary": summary,
        }
        self._summaries.append(summary_entry)
        # 最新10件のみ保持
        self._summaries = self._summaries[-10:]
        self._save_summaries()

        # 長期記憶にも保存
        if memory:
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                memory.add_mid_term(
                    content=f"[{ts}] 会話の要約: {summary}",
                    importance=0.6,
                    emotional_weight=0.5,
                    tags=["summary", "auto_generated"],
                )
            except Exception:
                pass

        return recent_messages

    def get_recent_summary(self) -> str:
        """直近の要約を返す（コンテキスト注入用）"""
        if not self._summaries:
            return ""
        latest = self._summaries[-1]
        return f"前の会話の要約：{latest['summary']}"

    def get_all_summaries(self, limit: int = 5) -> list[dict]:
        """要約一覧を返す"""
        return self._summaries[-limit:]

    # ─── private ─────────────────────────────────────────────

    def _generate_summary(
        self, messages: list[dict], llm: "LLMEngine | None"
    ) -> str:
        """メッセージ群を要約する"""
        # LLMが使えればLLMで要約
        if llm and getattr(llm, "llm", None) is not None:
            try:
                return self._llm_summarize(messages, llm)
            except Exception:
                pass

        # フォールバック: ルールベース要約
        return self._rule_based_summarize(messages)

    def _llm_summarize(self, messages: list[dict], llm: "LLMEngine") -> str:
        """LLMを使って要約する"""
        # 会話内容をテキスト化
        lines: list[str] = []
        for m in messages:
            role = "ユーザー" if m["role"] == "user" else "アイ"
            lines.append(f"{role}: {m['content'][:100]}")
        conversation_text = "\n".join(lines[-20:])  # 最新20発言

        prompt = [
            {"role": "system", "content": "以下の会話を100文字以内の日本語で要約してください。重要な話題とユーザーの感情を含めてください。"},
            {"role": "user", "content": conversation_text},
        ]
        result = llm.generate_chat(prompt)
        # 200文字に切り詰め
        result = result.strip()[:SUMMARY_MAX_CHARS]
        return result

    def _rule_based_summarize(self, messages: list[dict]) -> str:
        """ルールベースの要約（LLM不使用時のフォールバック）"""
        topics: list[str] = []
        for m in messages:
            if m["role"] == "user":
                text = m["content"][:60]
                # 質問文を抽出
                if any(q in text for q in ("？", "?", "って", "かな", "教えて")):
                    topics.append(text.split("？")[0].split("?")[0][:30])
                elif len(text) > 5:
                    topics.append(text[:30])

        if not topics:
            return "雑談をしていた"

        unique_topics = list(dict.fromkeys(topics))[:5]
        return "話題: " + "、".join(unique_topics)

    def _load_summaries(self) -> list[dict]:
        if not self._summaries_path.exists():
            return []
        try:
            with open(self._summaries_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_summaries(self) -> None:
        self._summaries_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._summaries_path, "w", encoding="utf-8") as f:
            json.dump(self._summaries, ensure_ascii=False, indent=2, fp=f)
