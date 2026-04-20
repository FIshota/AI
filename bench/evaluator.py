"""Shared bench evaluator (Phase 1).

各 suite の共通ループ: dataset から QAItem を取り、LLM で推論、judge で採点する。
zero-cost 原則により OpenAI / Claude API は使わない。

使い方 (suite 内部から):

    from bench.evaluator import evaluate_suite, EvalConfig
    from bench.datasets import load_jcommonsenseqa
    from bench.judges.rule_judge import RuleJudge

    items = load_jcommonsenseqa(limit=50)
    records = evaluate_suite(
        items,
        EvalConfig(model_family="sarashina2-7b"),
        judges=[RuleJudge()],
    )
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Protocol

from .datasets import QAItem
from .judges.base import JudgeScore

logger = logging.getLogger(__name__)


class _Judge(Protocol):
    name: str

    def score(
        self, prediction: str, reference: str | list[str], **kwargs
    ) -> JudgeScore: ...


@dataclass(frozen=True)
class EvalConfig:
    """評価実行の設定."""
    model_family: str = "sarashina2-7b"
    model_path: Optional[Path] = None   # None なら models/*.gguf を自動選択
    max_tokens: int = 256
    temperature: float = 0.7
    prompt_template: Optional[str] = None  # None なら question をそのまま入力
    # 選択式問題向けテンプレート (JCommonsenseQA 用)
    choice_format: bool = False


@dataclass(frozen=True)
class EvalRecord:
    """1 問分の評価結果."""
    qid: str
    question: str
    reference: str | list[str]
    prediction: str
    scores: dict[str, float]           # judge_name -> score
    judge_raw: dict[str, dict] = field(default_factory=dict)
    latency_sec: float = 0.0
    error: Optional[str] = None


# ─── LLM lazy-loader ─────────────────────────────────────

_CACHED_ENGINE = None
_CACHED_ENGINE_KEY: tuple | None = None


def _find_gguf() -> Path:
    models_dir = Path("models")
    found = sorted(models_dir.glob("*.gguf"))
    if not found:
        raise RuntimeError(
            "models/*.gguf が見つかりません。"
            " scripts/setup_model.py で DL してください。"
        )
    return found[0]


def _load_engine(cfg: EvalConfig):
    """LLMEngine を (プロセス内で) キャッシュしつつロード."""
    global _CACHED_ENGINE, _CACHED_ENGINE_KEY
    model_path = cfg.model_path or _find_gguf()
    key = (str(model_path), cfg.model_family)
    if _CACHED_ENGINE is not None and _CACHED_ENGINE_KEY == key:
        return _CACHED_ENGINE

    from core.llm import LLMEngine

    engine = LLMEngine(
        model_path=model_path,
        config={
            "model_family": cfg.model_family,
            "n_ctx": 2048,
        },
    )
    _CACHED_ENGINE = engine
    _CACHED_ENGINE_KEY = key
    return engine


# ─── プロンプト整形 ────────────────────────────────────────

def _build_prompt(item: QAItem, cfg: EvalConfig) -> str:
    if cfg.prompt_template:
        return cfg.prompt_template.format(
            question=item.question,
            choices="\n".join(f"- {c}" for c in (item.choices or [])),
        )
    if cfg.choice_format and item.choices:
        body = "\n".join(f"{i}: {c}" for i, c in enumerate(item.choices))
        return (
            "以下の質問に対して、選択肢から最も適切なものを 1 つ選んでください。\n"
            "回答は選択肢の本文を 1 行だけで出力してください。\n\n"
            f"質問: {item.question}\n選択肢:\n{body}\n\n回答:"
        )
    return item.question


# ─── main loop ───────────────────────────────────────────

def evaluate_suite(
    items: Iterable[QAItem],
    cfg: EvalConfig,
    judges: list[_Judge],
    *,
    dry_run: bool = False,
    on_progress: Optional[callable] = None,
) -> list[EvalRecord]:
    """items を順に LLM で推論 → judge で採点し、EvalRecord のリストを返す.

    dry_run=True のときは LLM を読み込まず空文字を予測とする (pipeline 検証用)。
    """
    items_list = list(items)
    records: list[EvalRecord] = []

    engine = None
    if not dry_run:
        try:
            engine = _load_engine(cfg)
        except Exception as e:
            logger.warning("[evaluator] LLM load failed: %s → dry_run フォールバック", e)
            engine = None

    for idx, item in enumerate(items_list):
        prompt = _build_prompt(item, cfg)
        pred = ""
        err: Optional[str] = None
        t0 = time.time()
        try:
            if engine is None:
                pred = ""
                err = "dry_run" if dry_run else "engine_unavailable"
            else:
                out = engine.generate(prompt, stream=False)
                pred = out if isinstance(out, str) else "".join(out)
        except Exception as e:
            logger.warning("[evaluator] generate failed on %s: %s", item.qid, e)
            err = str(e)
            pred = ""
        latency = time.time() - t0

        scores: dict[str, float] = {}
        raws: dict[str, dict] = {}
        for j in judges:
            try:
                js = j.score(pred, item.reference)
                scores[js.judge_name or j.name] = js.score
                raws[js.judge_name or j.name] = js.raw
            except Exception as e:
                logger.warning("[evaluator] judge %s failed: %s", getattr(j, "name", "?"), e)
                scores[getattr(j, "name", "?")] = 0.0
                raws[getattr(j, "name", "?")] = {"error": str(e)}

        rec = EvalRecord(
            qid=item.qid,
            question=item.question,
            reference=item.reference,
            prediction=pred,
            scores=scores,
            judge_raw=raws,
            latency_sec=latency,
            error=err,
        )
        records.append(rec)
        if on_progress is not None:
            on_progress(idx + 1, len(items_list), rec)

    return records


def aggregate(records: list[EvalRecord]) -> dict:
    """judge ごとの平均スコアと統計を返す."""
    if not records:
        return {"n": 0, "means": {}, "latency_mean": 0.0, "errors": 0}
    judge_keys: set[str] = set()
    for r in records:
        judge_keys.update(r.scores.keys())
    means = {
        k: sum(r.scores.get(k, 0.0) for r in records) / len(records)
        for k in judge_keys
    }
    errors = sum(1 for r in records if r.error)
    latency_mean = sum(r.latency_sec for r in records) / len(records)
    return {
        "n": len(records),
        "means": means,
        "latency_mean": latency_mean,
        "errors": errors,
    }
