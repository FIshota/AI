"""Phase 1 judge 基底定義."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class JudgeScore:
    """judge の採点結果 (不変)."""
    score: float                    # 0.0 - 1.0 に正規化
    raw: dict = field(default_factory=dict)  # 生の metric 値 (rouge_l など)
    judge_name: str = ""
    reasoning: str = ""              # local_judge の場合の理由テキスト

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            # 範囲外は clamp
            object.__setattr__(self, "score",
                               max(0.0, min(1.0, self.score)))


@runtime_checkable
class Judge(Protocol):
    """全 judge が実装するインターフェイス."""
    name: str

    def score(
        self,
        prediction: str,
        reference: str | list[str],
        **kwargs,
    ) -> JudgeScore:
        """prediction を reference と比較して 0.0-1.0 のスコアを返す."""
        ...
