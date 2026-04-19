"""
マルチエージェント協調エンジン（Sprint 4-M）
複数の専門エージェントを並列・直列で協調実行する。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_WORKERS = 4
_TASK_TIMEOUT = 60  # 秒


class MultiAgent:
    """複数の専門エージェントを並列・直列で協調実行。"""

    def __init__(
        self,
        base_dir: Path,
        llm_fn: Callable[[str], str],
        agents: dict,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._llm_fn = llm_fn
        # agents = {"research": ResearchAgent, "image": ImageGenerator, ...}
        self._agents = agents

    # ──────────────────────────────────────────────────────────────
    # 公開 API
    # ──────────────────────────────────────────────────────────────

    def execute_parallel(self, tasks: list[dict]) -> list[str]:
        """
        ThreadPoolExecutor で複数タスクを並列実行する。
        tasks = [{"type": "research", "query": "..."}, ...]
        戻り値: 各タスクの結果文字列リスト（順序は tasks に対応）
        """
        results: list[str] = [""] * len(tasks)
        try:
            with ThreadPoolExecutor(max_workers=_DEFAULT_WORKERS) as executor:
                future_to_idx = {
                    executor.submit(self._run_task, task): idx
                    for idx, task in enumerate(tasks)
                }
                for future in as_completed(future_to_idx, timeout=_TASK_TIMEOUT * len(tasks)):
                    idx = future_to_idx[future]
                    try:
                        results[idx] = future.result(timeout=_TASK_TIMEOUT)
                    except TimeoutError:
                        logger.warning("[MultiAgent] タスク %d タイムアウト", idx)
                        results[idx] = f"タスク {idx} がタイムアウトしました。"
                    except Exception as e:
                        logger.warning("[MultiAgent] タスク %d エラー: %s", idx, e)
                        results[idx] = f"タスク {idx} でエラーが発生しました: {e}"
        except Exception as e:
            logger.warning("[MultiAgent] execute_parallel error: %s", e)
        return results

    def execute_pipeline(self, pipeline: list[dict]) -> str:
        """
        直列パイプライン実行: 前のステップの出力を次のステップの入力に渡す。
        例: research → summarize → doc_create
        pipeline = [
            {"type": "research", "query": "..."},
            {"type": "summarize"},      # input は前ステップの結果
            {"type": "llm", "prompt_template": "次の内容を整形:\n{input}"},
        ]
        """
        output = ""
        for step_idx, step in enumerate(pipeline):
            try:
                # 前ステップの出力を input として注入
                step_with_input = {**step, "_pipeline_input": output}
                output = self._run_task(step_with_input)
                logger.info("[MultiAgent] pipeline step %d 完了", step_idx)
            except Exception as e:
                logger.warning("[MultiAgent] pipeline step %d エラー: %s", step_idx, e)
                output = f"ステップ {step_idx} でエラー: {e}"
        return output

    def register_agent(self, name: str, agent) -> None:
        """実行中にエージェントを追加登録する。"""
        self._agents[name] = agent

    # ──────────────────────────────────────────────────────────────
    # 内部ヘルパー
    # ──────────────────────────────────────────────────────────────

    def _run_task(self, task: dict) -> str:
        """
        タスク辞書を解釈して適切なエージェント / LLM を呼び出す。
        type キーによって振り分ける。
        """
        task_type = task.get("type", "llm")
        pipeline_input = task.get("_pipeline_input", "")

        # ─── research ──────────────────────────────────────────────
        if task_type == "research":
            agent = self._agents.get("research")
            if agent is None:
                return self._llm_search(task.get("query", pipeline_input))
            try:
                result = agent.search(task.get("query", pipeline_input))
                return result.summary if hasattr(result, "summary") else str(result)
            except Exception as e:
                logger.warning("[MultiAgent] research エラー: %s", e)
                return self._llm_search(task.get("query", pipeline_input))

        # ─── summarize ─────────────────────────────────────────────
        if task_type == "summarize":
            text = task.get("text", pipeline_input)
            return self._llm_fn(f"以下を簡潔に要約してください:\n\n{text[:3000]}")

        # ─── translate ─────────────────────────────────────────────
        if task_type == "translate":
            text = task.get("text", pipeline_input)
            target_lang = task.get("target_lang", "日本語")
            return self._llm_fn(
                f"以下を {target_lang} に翻訳してください:\n\n{text[:3000]}"
            )

        # ─── image ─────────────────────────────────────────────────
        if task_type == "image":
            agent = self._agents.get("image")
            if agent is None:
                return "画像生成エージェントが登録されていません。"
            try:
                prompt = task.get("prompt", pipeline_input)
                result = agent.generate(prompt)
                return str(result)
            except Exception as e:
                logger.warning("[MultiAgent] image エラー: %s", e)
                return f"画像生成エラー: {e}"

        # ─── doc_create ────────────────────────────────────────────
        if task_type == "doc_create":
            agent = self._agents.get("document") or self._agents.get("doc")
            if agent is None:
                return f"文書内容:\n{pipeline_input}"
            try:
                content = task.get("content", pipeline_input)
                result = agent.create(content)
                return str(result)
            except Exception as e:
                logger.warning("[MultiAgent] doc_create エラー: %s", e)
                return f"文書生成エラー: {e}"

        # ─── llm (デフォルト) ──────────────────────────────────────
        prompt_template = task.get("prompt_template", "{input}")
        prompt = task.get("prompt", prompt_template.format(input=pipeline_input))
        if not prompt:
            prompt = pipeline_input
        return self._llm_fn(prompt)

    def _llm_search(self, query: str) -> str:
        """ResearchAgent がない場合の LLM ベースフォールバック検索。"""
        return self._llm_fn(
            f"「{query}」について調査し、要点を日本語でまとめてください。"
        )
