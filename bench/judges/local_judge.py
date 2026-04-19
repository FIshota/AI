"""Local LLM judge: ローカル LLM に採点させる (Phase 1).

無料・ローカル完結。Claude Haiku / GPT-4o judge の代替。
Sarashina2-7B 等を採点者として使う。

⚠ 注意: 採点モデルが被採点モデルと同一の場合、バイアスが出る。
    本来は異なるモデル (Qwen2.5 / Gemma) で採点すべき。
    Phase 1 では "仮 judge" として動くことを優先。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .base import JudgeScore

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE = """あなたは厳格な日本語評価者です。
以下の予測文が、参照文と意味的にどれだけ正しいかを 0.0 から 1.0 の数値で採点してください。

採点基準:
- 1.0: 参照と完全に同じ意味
- 0.8: 参照の意図を正しく伝えているが表現が異なる
- 0.5: 部分的に正しい / 不完全
- 0.2: 大きく外れている / 一部だけ合っている
- 0.0: 無関係 / 間違い

出力は必ず以下の形式を守ってください:
SCORE: <数値>
REASON: <1-2 文の理由>

---
参照: {reference}

予測: {prediction}
---
"""


@dataclass
class LocalJudge:
    """ローカル LLM を呼び出して採点."""
    name: str = "local"
    # llm 呼び出し関数。シグネチャ: (prompt: str) -> str
    # 渡されない場合は core.llm.AiLLM を lazy-load する
    llm_call: Optional[callable] = None
    model_family: Optional[str] = None   # None なら default
    _cached_llm: Optional[object] = field(default=None, init=False, repr=False)

    def _ensure_llm(self):
        """core.llm の AiLLM を lazy-load."""
        if self.llm_call is not None:
            return self.llm_call
        if self._cached_llm is None:
            from core.llm import AiLLM
            config = {}
            if self.model_family:
                config["model_family"] = self.model_family
            llm = AiLLM(config=config)
            self._cached_llm = llm

        def _call(prompt: str) -> str:
            # AiLLM の interface は respond() or generate() の可能性
            obj = self._cached_llm
            if hasattr(obj, "generate"):
                return obj.generate(prompt, max_tokens=128)
            elif hasattr(obj, "respond"):
                return obj.respond(prompt)
            elif hasattr(obj, "complete"):
                return obj.complete(prompt)
            else:
                raise RuntimeError(
                    f"AiLLM has no known generate/respond/complete method"
                )

        return _call

    def score(
        self,
        prediction: str,
        reference: str | list[str],
        **kwargs,
    ) -> JudgeScore:
        ref_text = reference if isinstance(reference, str) else (
            "\n---\n".join(reference) if reference else ""
        )
        prompt = PROMPT_TEMPLATE.format(
            prediction=prediction[:1000],
            reference=ref_text[:1000],
        )

        try:
            call = self._ensure_llm()
            raw_output = call(prompt)
        except Exception as e:
            logger.warning("[local_judge] LLM call failed: %s", e)
            return JudgeScore(
                score=0.0, judge_name=self.name,
                raw={"error": str(e)},
                reasoning="LLM 呼び出し失敗",
            )

        score, reason = _parse_score(raw_output)
        return JudgeScore(
            score=score,
            raw={"output": raw_output[:500]},
            judge_name=self.name,
            reasoning=reason,
        )


def _parse_score(text: str) -> tuple[float, str]:
    """LLM 出力から SCORE と REASON を抽出."""
    if not text:
        return 0.0, "(empty)"

    # SCORE: <数値> のパース
    m = re.search(r"SCORE\s*[:：]\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
    if m:
        try:
            score = float(m.group(1))
            # 範囲外は clamp
            if score > 1.5:
                score = score / 10.0 if score <= 10.0 else 1.0
            score = max(0.0, min(1.0, score))
        except ValueError:
            score = 0.0
    else:
        # fallback: 最初の 0-1 小数を拾う
        m2 = re.search(r"\b([01]\.?[0-9]*)\b", text)
        if m2:
            try:
                score = float(m2.group(1))
                score = max(0.0, min(1.0, score))
            except ValueError:
                score = 0.0
        else:
            score = 0.0

    # REASON: <...> 抽出
    m3 = re.search(r"REASON\s*[:：]\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    reason = m3.group(1).strip()[:200] if m3 else text[:200]

    return score, reason
