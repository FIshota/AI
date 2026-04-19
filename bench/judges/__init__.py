"""Phase 1 judge パッケージ.

各 judge は同じインターフェイスを実装する:
    score(prediction: str, reference: str | list[str], **kwargs) -> JudgeScore

利用可能 judge:
  - rule_judge    : ROUGE-L / BLEU / exact / partial (無料・高速・API不要)
  - semantic_judge: sentence-transformers 埋め込み類似度 (無料・ローカル)
  - local_judge   : ローカル LLM (Sarashina2-7B 等) による自己採点 (無料)

設計方針: 「お金をかけない」ため全て無料代替のみ。
OpenAI / Anthropic API を使う judge は実装しない。
"""
from __future__ import annotations

from .base import JudgeScore, Judge

__all__ = ["JudgeScore", "Judge"]
