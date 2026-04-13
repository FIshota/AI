"""
MoE ルーター (Mixture of Experts Router)
ヤマト計画 A1: 複数GGUFモデルを動的に切り替えるプラグアンドプレイ型専門家システム。

機能:
- 複数モデル（日常会話用小型 + 推論用大型）の管理
- タスク種別による自動ルーティング
- モデルのホットスワップ（遅延ロード）
- フォールバックチェーン（大型→小型→テンプレート）
- 推論コスト追跡
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generator


@dataclass
class ExpertModel:
    """専門家モデルの定義"""
    name: str                    # 識別名（例: "chat", "reasoning", "coding"）
    model_path: str              # GGUFファイルパス
    specialty: list[str]         # 得意分野タグ
    priority: int = 0            # 優先度（高いほど優先）
    context_length: int = 4096
    max_tokens: int = 500
    temperature: float = 0.7
    loaded: bool = False
    cost_weight: float = 1.0     # 推論コスト重み（大型モデル=高い）

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model_path": self.model_path,
            "specialty": self.specialty,
            "priority": self.priority,
            "loaded": self.loaded,
            "cost_weight": self.cost_weight,
        }


@dataclass
class RoutingDecision:
    """ルーティング決定"""
    expert_name: str
    reason: str
    confidence: float = 0.8


# ─── タスク分類 ──────────────────────────────────────────────

# タスク種別→専門分野のマッピング
_TASK_SPECIALTY_MAP = {
    "greeting": ["chat", "general"],
    "emotion": ["chat", "empathy"],
    "chat": ["chat", "general"],
    "question": ["reasoning", "knowledge"],
    "consultation": ["reasoning", "empathy"],
    "request": ["chat", "general"],
    "report": ["chat", "general"],
    "coding": ["coding", "reasoning"],
    "analysis": ["reasoning", "knowledge"],
    "creative": ["creative", "chat"],
    "translation": ["language", "knowledge"],
}


class MoERouter:
    """
    Mixture of Experts ルーター。
    複数のGGUFモデルを管理し、タスクに応じて最適なモデルを選択する。

    使い方:
      router = MoERouter(models_dir, config)
      router.register_expert(ExpertModel(...))
      expert, llm = router.route("question")
      response = llm.generate_chat(messages)
    """

    def __init__(self, models_dir: str | Path, config: dict | None = None):
        self._models_dir = Path(models_dir)
        self._config = config or {}
        self._experts: dict[str, ExpertModel] = {}
        self._llm_instances: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._stats = {
            "total_routes": 0,
            "routes_per_expert": {},
            "total_tokens_estimated": 0,
        }
        self._auto_discover_models()

    # ─── モデル登録 ──────────────────────────────────────────

    def register_expert(self, expert: ExpertModel) -> None:
        """専門家モデルを登録する"""
        with self._lock:
            self._experts[expert.name] = expert

    def _auto_discover_models(self) -> None:
        """models/ ディレクトリからGGUFファイルを自動発見して登録する"""
        if not self._models_dir.exists():
            return

        gguf_files = list(self._models_dir.glob("*.gguf"))
        if not gguf_files:
            return

        for gguf in gguf_files:
            name = gguf.stem.lower()
            size_mb = gguf.stat().st_size / (1024 * 1024)

            # モデルサイズから専門分野を推定
            if size_mb < 1000:
                # 小型モデル → 日常会話特化
                expert = ExpertModel(
                    name=f"small_{name[:20]}",
                    model_path=str(gguf),
                    specialty=["chat", "general", "empathy"],
                    priority=1,
                    context_length=2048,
                    max_tokens=300,
                    temperature=0.8,
                    cost_weight=0.3,
                )
            elif size_mb < 3000:
                # 中型モデル → バランス型
                expert = ExpertModel(
                    name=f"mid_{name[:20]}",
                    model_path=str(gguf),
                    specialty=["chat", "reasoning", "knowledge", "general"],
                    priority=5,
                    context_length=4096,
                    max_tokens=500,
                    temperature=0.7,
                    cost_weight=0.6,
                )
            else:
                # 大型モデル → 推論・知識特化
                expert = ExpertModel(
                    name=f"large_{name[:20]}",
                    model_path=str(gguf),
                    specialty=["reasoning", "knowledge", "coding", "analysis"],
                    priority=10,
                    context_length=4096,
                    max_tokens=800,
                    temperature=0.6,
                    cost_weight=1.0,
                )

            self.register_expert(expert)

    # ─── ルーティング ────────────────────────────────────────

    def route(self, task_type: str = "chat", prefer_fast: bool = False) -> RoutingDecision:
        """
        タスク種別に基づいて最適な専門家を選択する。
        戻り値: RoutingDecision（expert_name でモデルを特定）
        """
        if not self._experts:
            return RoutingDecision(
                expert_name="",
                reason="モデル未登録",
                confidence=0.0,
            )

        # タスクに対応する専門分野を取得
        required_specialties = _TASK_SPECIALTY_MAP.get(
            task_type, ["chat", "general"]
        )

        # スコアリング
        scored: list[tuple[float, str, ExpertModel]] = []
        for name, expert in self._experts.items():
            score = 0.0

            # 専門分野の一致度
            matching = set(expert.specialty) & set(required_specialties)
            score += len(matching) * 10

            # 優先度
            score += expert.priority

            # 速度優先の場合、コスト重みを反転
            if prefer_fast:
                score -= expert.cost_weight * 5

            scored.append((score, name, expert))

        scored.sort(key=lambda x: -x[0])
        best_score, best_name, best_expert = scored[0]

        # 統計更新
        self._stats["total_routes"] += 1
        self._stats["routes_per_expert"][best_name] = (
            self._stats["routes_per_expert"].get(best_name, 0) + 1
        )

        return RoutingDecision(
            expert_name=best_name,
            reason=f"専門分野一致: {best_expert.specialty}",
            confidence=min(1.0, best_score / 30),
        )

    def get_expert(self, name: str) -> ExpertModel | None:
        """名前で専門家モデルを取得する"""
        return self._experts.get(name)

    def get_expert_config(self, name: str) -> dict:
        """専門家モデルのLLM設定を返す"""
        expert = self._experts.get(name)
        if expert is None:
            return self._config
        return {
            **self._config,
            "model_path": expert.model_path,
            "context_length": expert.context_length,
            "max_tokens": expert.max_tokens,
            "temperature": expert.temperature,
        }

    # ─── 情報取得 ─────────────────────────────────────────────

    def list_experts(self) -> list[dict]:
        """登録済み専門家一覧"""
        return [e.to_dict() for e in self._experts.values()]

    def get_stats(self) -> dict:
        """ルーティング統計"""
        return dict(self._stats)

    def get_status_text(self) -> str:
        """ステータステキスト"""
        if not self._experts:
            return "🧠 MoE: モデル未登録（models/にGGUFファイルを配置してね）"

        lines = [f"🧠 MoE専門家システム（{len(self._experts)}モデル）："]
        for name, expert in self._experts.items():
            status = "✅" if expert.loaded else "💤"
            specs = ", ".join(expert.specialty[:3])
            lines.append(f"  {status} {name}: [{specs}] (コスト: {expert.cost_weight:.1f})")

        total = self._stats["total_routes"]
        if total > 0:
            lines.append(f"\n  📊 総ルーティング: {total}回")

        return "\n".join(lines)

    @property
    def expert_count(self) -> int:
        return len(self._experts)
