"""
プロンプト A/B テスト

2つのプロンプトバリアントを交互に使用し、品質スコアを追跡します。
20会話後に統計的に優れたバリアントを自動選択します。
状態は data/ab_test_state.json に永続化されます。
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── デフォルト設定 ───────────────────────────────────────────

STATE_FILE: Path = Path("data/ab_test_state.json")
MIN_CONVERSATIONS_FOR_WINNER: int = 20


# ─── データモデル ─────────────────────────────────────────────


@dataclass
class PromptVariant:
    """プロンプトバリアントとそのスコア

    Attributes:
        name: バリアント名（"A" or "B"）
        template: プロンプトテンプレート
        scores: 品質スコアのリスト
        use_count: 使用回数
    """

    name: str
    template: str
    scores: List[float] = field(default_factory=list)
    use_count: int = 0

    @property
    def average_score(self) -> float:
        """平均スコアを返す"""
        if not self.scores:
            return 0.0
        return sum(self.scores) / len(self.scores)


@dataclass
class ABTestState:
    """A/B テストの状態

    Attributes:
        variant_a: バリアント A
        variant_b: バリアント B
        total_conversations: 累計会話数
        winner: 決定済みの勝者（未決定なら空文字）
        next_variant: 次に使用するバリアント名
    """

    variant_a: PromptVariant
    variant_b: PromptVariant
    total_conversations: int = 0
    winner: str = ""
    next_variant: str = "A"


# ─── A/B テストマネージャー ───────────────────────────────────


class PromptABTest:
    """プロンプトの A/B テスト管理"""

    def __init__(
        self,
        template_a: str = "",
        template_b: str = "",
        state_path: Optional[Path] = None,
    ) -> None:
        self._state_path: Path = state_path or STATE_FILE
        self._state: ABTestState = self._load_or_create(template_a, template_b)

    def get_current_template(self) -> str:
        """現在の会話で使用すべきプロンプトテンプレートを返す

        勝者が決まっている場合は勝者のテンプレートを返す。
        そうでなければ交互にバリアントを返す。

        Returns:
            プロンプトテンプレート
        """
        if self._state.winner:
            variant = self._get_variant(self._state.winner)
            return variant.template

        current_name: str = self._state.next_variant
        variant = self._get_variant(current_name)
        variant.use_count += 1

        # 次回のバリアントを交互に設定
        self._state.next_variant = "B" if current_name == "A" else "A"
        self._save()

        logger.debug(
            "A/Bテスト: バリアント %s を使用 (使用回数=%d)",
            current_name,
            variant.use_count,
        )
        return variant.template

    def record_score(self, variant_name: str, score: float) -> None:
        """品質スコアを記録する

        Args:
            variant_name: "A" or "B"
            score: 品質スコア（0.0 - 1.0）
        """
        clamped_score: float = max(0.0, min(1.0, score))
        variant = self._get_variant(variant_name)
        variant.scores.append(clamped_score)
        self._state.total_conversations += 1

        logger.debug(
            "A/Bテスト スコア記録: variant=%s score=%.2f avg=%.2f",
            variant_name,
            clamped_score,
            variant.average_score,
        )

        self._check_winner()
        self._save()

    def get_stats(self) -> Dict[str, Any]:
        """現在のテスト統計を返す

        Returns:
            統計情報の辞書
        """
        return {
            "total_conversations": self._state.total_conversations,
            "variant_a": {
                "use_count": self._state.variant_a.use_count,
                "average_score": self._state.variant_a.average_score,
                "sample_count": len(self._state.variant_a.scores),
            },
            "variant_b": {
                "use_count": self._state.variant_b.use_count,
                "average_score": self._state.variant_b.average_score,
                "sample_count": len(self._state.variant_b.scores),
            },
            "winner": self._state.winner,
        }

    def reset(self, template_a: str = "", template_b: str = "") -> None:
        """テスト状態をリセットする

        Args:
            template_a: 新しいバリアント A テンプレート
            template_b: 新しいバリアント B テンプレート
        """
        self._state = ABTestState(
            variant_a=PromptVariant(name="A", template=template_a),
            variant_b=PromptVariant(name="B", template=template_b),
        )
        self._save()
        logger.info("A/Bテストをリセット")

    @property
    def winner(self) -> str:
        """決定済みの勝者を返す（未決定なら空文字）"""
        return self._state.winner

    # ─── 内部メソッド ─────────────────────────────────────────

    def _get_variant(self, name: str) -> PromptVariant:
        """名前からバリアントを取得する"""
        if name == "A":
            return self._state.variant_a
        return self._state.variant_b

    def _check_winner(self) -> None:
        """勝者を判定する"""
        if self._state.winner:
            return

        if self._state.total_conversations < MIN_CONVERSATIONS_FOR_WINNER:
            return

        avg_a: float = self._state.variant_a.average_score
        avg_b: float = self._state.variant_b.average_score

        if len(self._state.variant_a.scores) < 5:
            return
        if len(self._state.variant_b.scores) < 5:
            return

        if avg_a > avg_b:
            self._state.winner = "A"
        elif avg_b > avg_a:
            self._state.winner = "B"
        else:
            # 同点の場合は引き続きテスト
            return

        logger.info(
            "A/Bテスト勝者決定: %s (A=%.2f, B=%.2f)",
            self._state.winner,
            avg_a,
            avg_b,
        )

    def _save(self) -> None:
        """状態をファイルに保存する"""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {
            "variant_a": asdict(self._state.variant_a),
            "variant_b": asdict(self._state.variant_b),
            "total_conversations": self._state.total_conversations,
            "winner": self._state.winner,
            "next_variant": self._state.next_variant,
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_or_create(
        self, template_a: str, template_b: str
    ) -> ABTestState:
        """状態ファイルから読み込むか、新規作成する"""
        if self._state_path.is_file():
            try:
                raw: str = self._state_path.read_text(encoding="utf-8")
                data: Dict[str, Any] = json.loads(raw)
                return ABTestState(
                    variant_a=PromptVariant(**data.get("variant_a", {"name": "A", "template": template_a})),
                    variant_b=PromptVariant(**data.get("variant_b", {"name": "B", "template": template_b})),
                    total_conversations=data.get("total_conversations", 0),
                    winner=data.get("winner", ""),
                    next_variant=data.get("next_variant", "A"),
                )
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning("A/Bテスト状態の読み込みに失敗、新規作成")

        return ABTestState(
            variant_a=PromptVariant(name="A", template=template_a),
            variant_b=PromptVariant(name="B", template=template_b),
        )
