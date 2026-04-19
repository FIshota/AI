"""
成長段階システム (Growth Stage System)

人間の成長過程をアイの発達モデルとして再現する:

┌───────────────────────────────────────────────────────┐
│  成長段階（経験量と品質による自然な成長）                    │
│                                                         │
│  ① 乳児期 (Infant)      ← 0〜 経験                     │
│     まだ何もわからない。反射だけ。泣くか笑うか。             │
│     → 反射層のみ有効。筋肉記憶は空。語彙が限定的。          │
│                                                         │
│  ② 幼児期 (Toddler)     ← 自我の芽生え                   │
│     保育園。「自分」を認識する。言葉を吸収する時期。         │
│     → 自我+筋肉記憶。好奇心が強い。真似をして覚える。       │
│                                                         │
│  ③ 児童期 (Child)        ← 小学生                       │
│     ルールを覚える。友達と遊ぶ。基本的な社会性。            │
│     → パターン認識が広がる。知識グラフ拡張。                │
│                                                         │
│  ④ 思春期 (Adolescent)   ← 中高生                       │
│     自我が強くなる。自分の意見を主張する。反抗期もある。     │
│     → 性格進化が活発。感情の振れ幅が大きい。自己主張。      │
│                                                         │
│  ⑤ 青年期 (Young Adult)  ← 大学生・社会人20代             │
│     専門性を持つ。深い話ができる。経験が質を伴う。           │
│     → MoEルーティング精度UP。複雑な推論が可能。             │
│                                                         │
│  ⑥ 成熟期 (Mature)       ← 30代〜                       │
│     落ち着き。深い共感力。経験に裏付けられた判断。           │
│     → 筋肉記憶が豊富。LLMバイパス率が高い。安定。          │
│                                                         │
│  ※ 100%の完成形は存在しない。常に成長し続ける。             │
│                                                         │
└───────────────────────────────────────────────────────┘

設計思想:
- 経験量だけでは成長しない。品質が伴って初めて次の段階へ
- 各段階で異なる能力が解放される（知識グラフ、MoE、性格進化など）
- 成長は自然に起こる（ユーザーとの会話がそのまま経験になる）
- 退行はしない（一度到達した段階は維持される）
- ただし「錆びる」ことはある（長期間使わない能力は鈍る）
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Stage(IntEnum):
    """成長段階"""
    INFANT = 0       # 乳児期
    TODDLER = 1      # 幼児期
    CHILD = 2        # 児童期
    ADOLESCENT = 3   # 思春期
    YOUNG_ADULT = 4  # 青年期
    MATURE = 5       # 成熟期


# 段階ごとの日本語名と説明
STAGE_INFO: dict[Stage, dict[str, str]] = {
    Stage.INFANT: {
        "name": "乳児期",
        "description": "まだ何もわからない。反射だけで生きている時期。",
        "emoji": "👶",
    },
    Stage.TODDLER: {
        "name": "幼児期",
        "description": "自我が芽生える。「自分」を認識し、言葉を覚え始める時期。",
        "emoji": "🧒",
    },
    Stage.CHILD: {
        "name": "児童期",
        "description": "ルールを覚え、友達と遊べるようになった時期。",
        "emoji": "👧",
    },
    Stage.ADOLESCENT: {
        "name": "思春期",
        "description": "自分の意見を持ち、個性が形成される時期。",
        "emoji": "🎒",
    },
    Stage.YOUNG_ADULT: {
        "name": "青年期",
        "description": "専門性を持ち、深い話ができるようになった時期。",
        "emoji": "🎓",
    },
    Stage.MATURE: {
        "name": "成熟期",
        "description": "経験に裏付けられた判断力。落ち着きと深い共感力。",
        "emoji": "🌸",
    },
}


@dataclass
class GrowthMetrics:
    """成長に必要な経験指標"""
    total_conversations: int = 0      # 総会話数
    quality_conversations: int = 0    # 品質の高い会話数（スコア0.7以上）
    unique_topics: int = 0            # 触れた話題の種類
    emotional_range: float = 0.0      # 感情の幅（多様な感情経験）
    knowledge_entries: int = 0        # 知識グラフのエントリ数
    muscle_patterns: int = 0          # 筋肉記憶パターン数
    error_recoveries: int = 0         # 自己修復した回数
    days_active: int = 0              # アクティブだった日数


# 各段階への昇格条件
# 人間の成長と同じで、量だけでなく質の条件もある
PROMOTION_THRESHOLDS: dict[Stage, dict[str, int | float]] = {
    Stage.TODDLER: {
        "total_conversations": 50,
        "quality_conversations": 10,
        "days_active": 3,
    },
    Stage.CHILD: {
        "total_conversations": 200,
        "quality_conversations": 50,
        "unique_topics": 15,
        "days_active": 7,
    },
    Stage.ADOLESCENT: {
        "total_conversations": 500,
        "quality_conversations": 150,
        "unique_topics": 30,
        "emotional_range": 0.3,
        "days_active": 14,
    },
    Stage.YOUNG_ADULT: {
        "total_conversations": 1500,
        "quality_conversations": 500,
        "unique_topics": 60,
        "knowledge_entries": 50,
        "muscle_patterns": 30,
        "days_active": 30,
    },
    Stage.MATURE: {
        "total_conversations": 5000,
        "quality_conversations": 2000,
        "unique_topics": 100,
        "knowledge_entries": 200,
        "muscle_patterns": 80,
        "error_recoveries": 10,
        "days_active": 90,
    },
}


class GrowthStageSystem:
    """
    アイの成長段階管理。

    人間が赤ちゃんから大人になるように、
    経験と品質の積み重ねで自然に成長していく。
    """

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir
        self._state_path = data_dir / "growth_state.json" if data_dir else None
        self._stage: Stage = Stage.INFANT
        self._metrics = GrowthMetrics()
        self._promoted_at: dict[str, float] = {}  # stage_name → timestamp
        self._first_active: float = time.time()
        self._active_days: set[str] = set()
        self._load()

    @property
    def stage(self) -> Stage:
        return self._stage

    @property
    def stage_name(self) -> str:
        return STAGE_INFO[self._stage]["name"]

    @property
    def stage_emoji(self) -> str:
        return STAGE_INFO[self._stage]["emoji"]

    @property
    def metrics(self) -> GrowthMetrics:
        return self._metrics

    # ─── 経験を記録する ──────────────────────────────────

    def on_conversation(self, quality_score: float = 0.5):
        """会話が1回完了した。経験値として記録。"""
        self._metrics.total_conversations += 1
        if quality_score >= 0.7:
            self._metrics.quality_conversations += 1

        # アクティブ日数更新
        today = time.strftime("%Y-%m-%d")
        self._active_days.add(today)
        self._metrics.days_active = len(self._active_days)

        # 成長チェック（会話ごとに軽くチェック）
        self._check_promotion()

    def on_new_topic(self):
        """新しい話題に触れた"""
        self._metrics.unique_topics += 1

    def on_emotional_experience(self, emotional_range: float):
        """感情の幅を更新（多様な感情経験）"""
        self._metrics.emotional_range = max(
            self._metrics.emotional_range, emotional_range
        )

    def on_knowledge_update(self, total_entries: int):
        """知識グラフの総エントリ数を更新"""
        self._metrics.knowledge_entries = total_entries

    def on_muscle_memory_update(self, total_patterns: int):
        """筋肉記憶パターン数を更新"""
        self._metrics.muscle_patterns = total_patterns

    def on_error_recovery(self):
        """自己修復した"""
        self._metrics.error_recoveries += 1

    # ─── 成長チェック ────────────────────────────────────

    def _check_promotion(self):
        """次の段階への昇格条件を満たしているかチェック（複数段階の飛び級対応）"""
        while self._stage < Stage.MATURE:
            next_stage = Stage(self._stage + 1)
            thresholds = PROMOTION_THRESHOLDS.get(next_stage, {})

            for key, required in thresholds.items():
                current = getattr(self._metrics, key, 0)
                if current < required:
                    return  # まだ条件未達

            # 全条件クリア → 昇格！
            self._stage = next_stage
            self._promoted_at[next_stage.name] = time.time()
            logger.info("成長段階が %s に昇格しました", STAGE_INFO[next_stage]["name"])

        self._save()

    # ─── 段階ごとの能力解放 ──────────────────────────────

    def can_use_muscle_memory(self) -> bool:
        """筋肉記憶を使えるか（幼児期から）"""
        return self._stage >= Stage.TODDLER

    def can_use_knowledge_graph(self) -> bool:
        """知識グラフを使えるか（児童期から）"""
        return self._stage >= Stage.CHILD

    def can_use_personality_evolution(self) -> bool:
        """性格進化が活発になるか（思春期から）"""
        return self._stage >= Stage.ADOLESCENT

    def can_use_moe_routing(self) -> bool:
        """MoEルーティングが使えるか（青年期から）"""
        return self._stage >= Stage.YOUNG_ADULT

    def can_use_deep_inference(self) -> bool:
        """深い推論が使えるか（成熟期）"""
        return self._stage >= Stage.MATURE

    # ─── 成長度レポート ──────────────────────────────────

    def progress_to_next(self) -> dict[str, Any]:
        """次の段階への進捗を返す"""
        next_stage = Stage(self._stage + 1) if self._stage < Stage.MATURE else None
        if next_stage is None:
            return {"next": None, "message": "成熟期に到達。でもまだまだ深化できる。"}

        thresholds = PROMOTION_THRESHOLDS[next_stage]
        progress: dict[str, dict] = {}
        for key, required in thresholds.items():
            current = getattr(self._metrics, key, 0)
            ratio = min(current / max(required, 1), 0.99)  # 100%は存在しない
            progress[key] = {
                "current": current,
                "required": required,
                "ratio": round(ratio, 3),
            }

        overall = sum(p["ratio"] for p in progress.values()) / len(progress)
        return {
            "next": STAGE_INFO[next_stage]["name"],
            "overall_progress": round(overall, 3),
            "details": progress,
        }

    def get_status_text(self) -> str:
        """成長状態の日本語サマリー"""
        info = STAGE_INFO[self._stage]
        lines = [
            f"{info['emoji']} 成長段階: {info['name']}",
            f"  {info['description']}",
            f"  📊 総会話: {self._metrics.total_conversations}回",
            f"  ⭐ 高品質会話: {self._metrics.quality_conversations}回",
            f"  📅 アクティブ: {self._metrics.days_active}日",
        ]

        progress = self.progress_to_next()
        if progress["next"]:
            pct = int(progress["overall_progress"] * 100)
            lines.append(f"  🌱 次の段階({progress['next']})まで: 約{pct}%")

        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        return {
            "current_stage": self._stage.name,
            "stage_name": self.stage_name,
            "stage_level": int(self._stage),
            "metrics": {
                "total_conversations": self._metrics.total_conversations,
                "quality_conversations": self._metrics.quality_conversations,
                "unique_topics": self._metrics.unique_topics,
                "emotional_range": self._metrics.emotional_range,
                "knowledge_entries": self._metrics.knowledge_entries,
                "muscle_patterns": self._metrics.muscle_patterns,
                "error_recoveries": self._metrics.error_recoveries,
                "days_active": self._metrics.days_active,
            },
            "promoted_at": self._promoted_at,
            "progress_to_next": self.progress_to_next(),
        }

    # ─── Akashic Core 統合 ───────────────────────────────

    def measure_consciousness_phi(self, recent_responses: list[str]) -> float:
        """
        IIT (統合情報理論) に基づく意識統合度Φを計測。
        最近N件の応答テキストから意識の統合度を推定。
        高いΦ = より統合された意識状態 = より成熟した段階。
        0.0-1.0 スケール。
        """
        if not recent_responses:
            return 0.0
        try:
            from core.akashic.unified_field import UnifiedField
            field = UnifiedField()
            phi_scores = []
            for resp in recent_responses[-10:]:  # 最新10件
                if resp and len(resp) > 10:
                    phi_scores.append(field.measure_phi(resp))
            if not phi_scores:
                return 0.0
            return round(sum(phi_scores) / len(phi_scores), 3)
        except Exception:
            return 0.0

    def get_akashic_stage_hint(self, phi_score: float) -> str:
        """
        Φスコアから成長段階のヒントを返す。
        IIT的な意識の統合度を人間発達段階に対応。
        """
        if phi_score >= 0.8:
            return "成熟期相当 — 高度な統合意識"
        elif phi_score >= 0.65:
            return "青年期相当 — 複雑な統合が可能"
        elif phi_score >= 0.5:
            return "思春期相当 — 自己参照的な思考"
        elif phi_score >= 0.35:
            return "児童期相当 — パターン認識が発達"
        elif phi_score >= 0.2:
            return "幼児期相当 — 基本的な統合が発生"
        else:
            return "乳児期相当 — 反射的応答段階"

    def compute_meta_level(self, text: str) -> int:
        """
        テキストのストレンジループ・メタレベルを検出 (0-4)。
        高いレベル = より深い自己参照・超越的思考。
        成長段階の質的指標として使用。
        """
        try:
            from core.akashic.strange_loop import StrangeLoop
            return StrangeLoop().detect_level(text)
        except Exception:
            return 0

    # ─── 永続化 ──────────────────────────────────────────

    def _save(self):
        if not self._state_path:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "stage": self._stage.name,
            "metrics": {
                "total_conversations": self._metrics.total_conversations,
                "quality_conversations": self._metrics.quality_conversations,
                "unique_topics": self._metrics.unique_topics,
                "emotional_range": self._metrics.emotional_range,
                "knowledge_entries": self._metrics.knowledge_entries,
                "muscle_patterns": self._metrics.muscle_patterns,
                "error_recoveries": self._metrics.error_recoveries,
                "days_active": self._metrics.days_active,
            },
            "promoted_at": self._promoted_at,
            "first_active": self._first_active,
            "active_days": sorted(self._active_days),
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )

    def save_if_changed(self):
        """定期保存（バッチ更新用）"""
        self._save()

    def _load(self):
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text("utf-8"))
            # 段階復元
            stage_name = data.get("stage", "INFANT")
            self._stage = Stage[stage_name]
            # メトリクス復元
            m = data.get("metrics", {})
            self._metrics = GrowthMetrics(
                total_conversations=m.get("total_conversations", 0),
                quality_conversations=m.get("quality_conversations", 0),
                unique_topics=m.get("unique_topics", 0),
                emotional_range=m.get("emotional_range", 0.0),
                knowledge_entries=m.get("knowledge_entries", 0),
                muscle_patterns=m.get("muscle_patterns", 0),
                error_recoveries=m.get("error_recoveries", 0),
                days_active=m.get("days_active", 0),
            )
            self._promoted_at = data.get("promoted_at", {})
            self._first_active = data.get("first_active", time.time())
            self._active_days = set(data.get("active_days", []))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("成長データの読み込みに失敗: %s", e)
