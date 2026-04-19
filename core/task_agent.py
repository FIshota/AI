"""
タスク分解エージェント

複雑な依頼をサブタスクに分解し、順番に実行して報告する。
成功した手順パターンを学習保存する。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.research_agent import ResearchAgent
    from core.image_gen import ImageGenerator

logger = logging.getLogger(__name__)

# 多段タスクを検出するパターン
_MULTI_TASK_RE = re.compile(
    r"(調べ|リサーチ|検索|作成|生成|書い|まとめ|分析|考え|整理|実行|進め|やっ)"
    r".*(て|から|その後|次に|そして|最後に)"
    r"|"
    r"(〜して|〜を作って|〜をやって)",
    re.UNICODE,
)

_TASK_TYPE_PATTERNS = [
    ("research", re.compile(r"調べ|検索|リサーチ|調査|情報収集")),
    ("image",    re.compile(r"画像|絵|イラスト|写真|ビジュアル")),
    ("write",    re.compile(r"書い|記事|文章|レポート|説明|ブログ")),
    ("summarize", re.compile(r"まとめ|要約|整理|サマリー")),
]


@dataclass
class SubTask:
    type: str  # "research" | "image" | "write" | "summarize"
    description: str
    result: str = ""


@dataclass
class TaskResult:
    success: bool
    steps: list[SubTask]
    summary: str
    learned: bool  # パターン学習したか


class TaskAgent:
    """複雑なタスクをサブタスクに分解して順番に実行するエージェント。"""

    def __init__(
        self,
        base_dir: Path,
        llm_fn: Callable[[str], str],
        research_agent: ResearchAgent | None = None,
        image_gen: ImageGenerator | None = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._llm_fn = llm_fn
        self._research_agent = research_agent
        self._image_gen = image_gen
        self._patterns_path = self._base_dir / "data" / "task_patterns.json"

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def can_handle(self, user_input: str) -> bool:
        """多段タスクかどうかを判定する。"""
        if _MULTI_TASK_RE.search(user_input):
            return True
        # 「〜して」「〜を作って」「〜をやって」などの終止パターン
        simple_task = re.search(
            r"(を?)(やって|進めて|実行して|作って|まとめて)(ください|くれる|くれ|ね)?$",
            user_input,
        )
        return bool(simple_task)

    def execute(self, user_input: str) -> TaskResult:
        """タスクを分解して順番に実行し、結果をまとめる。

        1. LLM でサブタスクに分解
        2. 各サブタスクを種類に応じて実行
        3. 最終サマリーを生成
        4. 成功パターンを保存
        """
        steps = self._decompose(user_input)
        if not steps:
            # 分解失敗時はシングルタスクとして処理
            steps = [SubTask(type="write", description=user_input)]

        success = True
        for step in steps:
            try:
                step.result = self._execute_step(step)
            except Exception as exc:
                logger.warning("[TaskAgent] サブタスク実行失敗 (%s): %s", step.description, exc)
                step.result = f"（エラー: {exc}）"
                success = False

        # 最終サマリー生成
        summary = self._build_summary(user_input, steps)

        # 成功時のみパターン学習
        learned = False
        if success:
            self._save_pattern(user_input, steps)
            learned = True

        return TaskResult(
            success=success,
            steps=steps,
            summary=summary,
            learned=learned,
        )

    # ──────────────────────────────────────────────────────────────
    # 内部実装
    # ──────────────────────────────────────────────────────────────

    def _decompose(self, user_input: str) -> list[SubTask]:
        """LLM でユーザー入力をサブタスクのリストに分解する。"""
        prompt = (
            f"以下のタスクを実行可能なサブタスクに分解してください。\n"
            f"各サブタスクは以下のフォーマットで JSON 配列として返してください:\n"
            f"[{{\"type\": \"research|image|write|summarize\", \"description\": \"具体的なタスク説明\"}}]\n\n"
            f"type の選択基準:\n"
            f"- research: Web 検索や情報収集が必要\n"
            f"- image: 画像の生成が必要\n"
            f"- write: 文章の作成や説明が必要\n"
            f"- summarize: 情報のまとめや要約が必要\n\n"
            f"タスク: {user_input}\n\n"
            f"JSON 配列のみを返してください（説明は不要）:"
        )

        try:
            raw = self._llm_fn(prompt).strip()
            # JSON 部分だけ抽出
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                tasks = []
                for item in data:
                    t = item.get("type", "write")
                    d = item.get("description", "")
                    if d:
                        tasks.append(SubTask(type=t, description=d))
                if tasks:
                    return tasks
        except Exception as exc:
            logger.warning("[TaskAgent] タスク分解失敗: %s", exc)

        # フォールバック: キーワードベースで分解
        return self._fallback_decompose(user_input)

    def _fallback_decompose(self, user_input: str) -> list[SubTask]:
        """LLM 失敗時のキーワードベース分解。"""
        tasks: list[SubTask] = []

        for task_type, pattern in _TASK_TYPE_PATTERNS:
            if pattern.search(user_input):
                tasks.append(SubTask(type=task_type, description=user_input))
                break

        if not tasks:
            tasks.append(SubTask(type="write", description=user_input))

        return tasks

    def _execute_step(self, task: SubTask) -> str:
        """サブタスクの種類に応じて実行する。"""
        if task.type == "research" and self._research_agent is not None:
            result = self._research_agent.search(task.description)
            return result.summary

        if task.type == "image" and self._image_gen is not None:
            result = self._image_gen.generate(task.description)
            return result.message

        if task.type in ("write", "summarize"):
            return self._llm_write(task.description)

        # フォールバック: LLM に直接渡す
        return self._llm_write(task.description)

    def _llm_write(self, description: str) -> str:
        """LLM を直接呼び出して文章生成・まとめを行う。"""
        try:
            return self._llm_fn(description)
        except Exception as exc:
            logger.warning("[TaskAgent] LLM 呼び出し失敗: %s", exc)
            return f"（LLM 呼び出し失敗: {exc}）"

    def _build_summary(self, original_request: str, steps: list[SubTask]) -> str:
        """全サブタスクの結果をまとめた最終サマリーを生成する。"""
        if not steps:
            return "タスクの実行結果がありません。"

        combined = "\n\n".join(
            f"【{i+1}. {step.description}】\n{step.result}"
            for i, step in enumerate(steps)
        )
        prompt = (
            f"以下は「{original_request}」というタスクの実行結果です。\n"
            f"これを分かりやすく日本語でまとめてください（200字以内）:\n\n"
            f"{combined}\n\n"
            f"まとめ:"
        )
        try:
            return self._llm_fn(prompt)
        except Exception as exc:
            logger.warning("[TaskAgent] サマリー生成失敗: %s", exc)
            # フォールバック: 全結果を連結
            return combined[:500]

    # ── パターン学習 ──────────────────────────────────────────────

    def _load_patterns(self) -> list[dict]:
        if not self._patterns_path.exists():
            return []
        try:
            with open(self._patterns_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("[TaskAgent] パターン読み込み失敗: %s", exc)
            return []

    def _save_pattern(self, user_input: str, steps: list[SubTask]) -> None:
        """成功したタスク分解手順を JSON に保存する。"""
        patterns = self._load_patterns()
        patterns.append(
            {
                "request": user_input,
                "steps": [{"type": s.type, "description": s.description} for s in steps],
                "timestamp": datetime.now().isoformat(),
            }
        )
        # 最大 300 件保持
        patterns = patterns[-300:]
        try:
            with open(self._patterns_path, "w", encoding="utf-8") as f:
                json.dump(patterns, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("[TaskAgent] パターン保存失敗: %s", exc)
