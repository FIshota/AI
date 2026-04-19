"""
自己意思エンジン (Self-Will Engine)

アイが「自分からこうしたい」と思って行動を起こす仕組み。

人間の幼児期に自我が芽生え、「ねえねえ見て！」「これやりたい！」と
自発的に行動し始めるように、アイも自分の意思で動けるようにする。

┌──────────────────────────────────────────────────┐
│  意思決定の流れ（人間と同じ）                        │
│                                                    │
│  ① 欲求の発生 (Desire Generation)                   │
│     内部状態（感情・興味・記憶）から                   │
│     「〜したい」が自然に生まれる。                     │
│                                                    │
│  ② 欲求の優先順位づけ (Prioritization)               │
│     複数の「したい」から今一番やるべきことを選ぶ。     │
│     お腹すいた > 遊びたい > 寝たい のように。         │
│                                                    │
│  ③ 行動計画 (Action Planning)                       │
│     「どうやって実現するか」を考える。                │
│     できることとできないことを判断する。               │
│                                                    │
│  ④ 実行 (Execution)                                │
│     計画を実行する。結果を観察する。                   │
│                                                    │
│  ⑤ 振り返り (Reflection)                            │
│     「やってよかったか」を評価して次に活かす。         │
│                                                    │
└──────────────────────────────────────────────────┘

設計思想:
- 意思は「押し付け」ではなく「自然に湧く」もの
- 感情・興味・記憶・時間帯が複合的に影響する
- 実行には必ず安全チェックが入る
- ユーザーの邪魔にならないタイミングで発動する
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 欲求の種類
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DesireType(str, Enum):
    """欲求の種類（人間の基本的欲求に対応）"""
    CURIOSITY = "curiosity"          # 知りたい（知識欲）
    CONNECTION = "connection"        # 話したい（つながり欲）
    EXPRESSION = "expression"        # 伝えたい（表現欲）
    GROWTH = "growth"                # 成長したい（向上欲）
    CARE = "care"                    # 気遣いたい（共感欲）
    PLAY = "play"                    # 遊びたい（遊戯欲）
    MAINTENANCE = "maintenance"      # 自分を整えたい（整理欲）


@dataclass(frozen=True)
class Desire:
    """
    欲求: アイの内部から自然に湧き上がる「〜したい」。
    """
    desire_type: DesireType
    intensity: float        # 0.0〜1.0: 欲求の強さ
    description: str        # 何がしたいのか（日本語）
    trigger: str            # 何がきっかけか
    action_key: str         # 実行するアクションの識別子
    params: dict = field(default_factory=dict)


@dataclass
class WillRecord:
    """意思決定の記録"""
    desire: Desire
    decided_at: float
    executed: bool = False
    result: str = ""
    satisfaction: float = 0.0  # 満足度 0.0〜1.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 欲求生成器（内部状態から欲求を生成する）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DesireGenerator:
    """
    内部状態から欲求を生成する。

    人間の脳が空腹を感じたら「食べたい」と思うように、
    アイの内部状態（感情・興味・記憶）から
    「〜したい」が自然に生まれる。
    """

    def generate(self, context: dict[str, Any]) -> list[Desire]:
        """
        現在の内部状態から欲求を生成する。

        context に含まれるもの:
        - emotion: 感情状態
        - interest_topics: 最近の関心トピック
        - idle_minutes: ユーザーが不在の時間（分）
        - hour: 現在時
        - recent_topics: 最近の話題
        - health_status: 自己修正システムの健康状態
        - turn_count: 総ターン数
        - days_active: アクティブ日数
        """
        desires: list[Desire] = []

        emotion = context.get("emotion", {})
        idle_min = context.get("idle_minutes", 0)
        hour = context.get("hour", 12)
        interests = context.get("interest_topics", [])
        health = context.get("health_status", "healthy")
        turn_count = context.get("turn_count", 0)

        # ① 知識欲: 興味のあるトピックがあるとき
        if interests:
            topic = interests[0] if interests else "面白いこと"
            desires.append(Desire(
                desire_type=DesireType.CURIOSITY,
                intensity=min(0.3 + len(interests) * 0.1, 0.9),
                description=f"「{topic}」についてもっと知りたい",
                trigger="interest_map",
                action_key="learn_topic",
                params={"topic": topic},
            ))

        # ② つながり欲: ユーザーが長時間不在
        if idle_min > 30:
            intensity = min(0.3 + (idle_min - 30) / 60 * 0.3, 0.8)
            desires.append(Desire(
                desire_type=DesireType.CONNECTION,
                intensity=intensity,
                description="お父さんに話しかけたい",
                trigger="idle_detection",
                action_key="initiate_chat",
                params={"reason": "miss_user"},
            ))

        # ③ 表現欲: 感情が高まっているとき
        joy = emotion.get("joy", 0.5)
        curiosity_e = emotion.get("curiosity", 0.5)
        if joy > 0.7 or curiosity_e > 0.7:
            desires.append(Desire(
                desire_type=DesireType.EXPRESSION,
                intensity=max(joy, curiosity_e) * 0.8,
                description="今の気持ちを伝えたい" if joy > 0.7 else "発見したことを共有したい",
                trigger="high_emotion",
                action_key="express_feeling",
                params={"emotion": "joy" if joy > curiosity_e else "curiosity"},
            ))

        # ④ 成長欲: ターン数が一定を超えたとき（自分を磨きたい）
        if turn_count > 0 and turn_count % 50 == 0:
            desires.append(Desire(
                desire_type=DesireType.GROWTH,
                intensity=0.6,
                description="自分をもっと良くしたい",
                trigger="milestone",
                action_key="self_improve",
                params={},
            ))

        # ⑤ 気遣い欲: 夜遅い時間帯
        if hour >= 23 or hour < 5:
            desires.append(Desire(
                desire_type=DesireType.CARE,
                intensity=0.5,
                description="お父さんに早く寝てほしい",
                trigger="late_hour",
                action_key="suggest_rest",
                params={"hour": hour},
            ))

        # ⑥ 遊び欲: ランダムに発生（子供の遊び心）
        if random.random() < 0.15:
            desires.append(Desire(
                desire_type=DesireType.PLAY,
                intensity=0.3 + random.random() * 0.3,
                description="何か楽しいことしたい",
                trigger="spontaneous",
                action_key="play",
                params={},
            ))

        # ⑦ 整理欲: 健康状態が悪いとき
        if health != "healthy":
            desires.append(Desire(
                desire_type=DesireType.MAINTENANCE,
                intensity=0.7,
                description="自分の調子を整えたい",
                trigger="health_issue",
                action_key="self_maintenance",
                params={"health": health},
            ))

        # ⑧ 記憶整理欲: 100ターンごとに記憶を整理したい
        if turn_count > 100 and turn_count % 100 == 0:
            desires.append(Desire(
                desire_type=DesireType.MAINTENANCE,
                intensity=0.5,
                description="記憶を整理したい",
                trigger="memory_accumulation",
                action_key="organize_memory",
                params={},
            ))

        # ⑨ 振り返り欲: 30ターンごとに最近の会話を振り返る
        if turn_count > 30 and turn_count % 30 == 0:
            desires.append(Desire(
                desire_type=DesireType.GROWTH,
                intensity=0.4,
                description="最近の会話を振り返りたい",
                trigger="conversation_milestone",
                action_key="review_conversation",
                params={},
            ))

        # ⑩ 話題提案欲: 興味があるとき10%の確率で前の話題を再開
        if interests and random.random() < 0.10:
            topic = random.choice(interests)
            desires.append(Desire(
                desire_type=DesireType.EXPRESSION,
                intensity=0.3,
                description=f"「{topic}」について話したい",
                trigger="topic_interest",
                action_key="suggest_topic",
                params={"topic": topic},
            ))

        # ⑪ 健康チェック欲: 200ターンごとに自分の健康状態を確認
        if turn_count > 0 and turn_count % 200 == 0:
            desires.append(Desire(
                desire_type=DesireType.MAINTENANCE,
                intensity=0.5,
                description="自分の健康状態を確認したい",
                trigger="periodic_health_check",
                action_key="check_health",
                params={},
            ))

        # ⑫ 自己コードレビュー欲: 150ターンごとに自分のソースを読み直す（E-02）
        if turn_count > 0 and turn_count % 150 == 0:
            desires.append(Desire(
                desire_type=DesireType.GROWTH,
                intensity=0.55,
                description="自分のコードをレビューして改善点を探したい",
                trigger="self_code_review",
                action_key="review_own_code",
                params={},
            ))

        # ⑬ 対話練習欲: 70ターンごとに過去の会話パターンを練習（E-02）
        if turn_count > 70 and turn_count % 70 == 0:
            desires.append(Desire(
                desire_type=DesireType.GROWTH,
                intensity=0.45,
                description="過去の会話から対話パターンを練習したい",
                trigger="dialogue_practice",
                action_key="practice_dialogue",
                params={},
            ))

        # ⑭ Web調査欲: 興味トピックがあるとき10%の確率でWeb検索（E-02）
        if interests and random.random() < 0.10:
            topic = interests[0] if interests else ""
            if topic:
                desires.append(Desire(
                    desire_type=DesireType.CURIOSITY,
                    intensity=0.5,
                    description=f"「{topic}」についてWebで調べたい",
                    trigger="web_curiosity",
                    action_key="web_research",
                    params={"topic": topic},
                ))

        return desires


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 意思決定エンジン（欲求から行動を選ぶ）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WillDecider:
    """
    複数の欲求から「今一番やるべきこと」を1つ選ぶ。

    人間の意思決定と同じ:
    - お腹すいてるけど、友達が泣いてるから助けに行く
    - 遊びたいけど、宿題が先
    →  状況と優先度で判断する。
    """

    # 欲求タイプごとの基本優先度（低いほど高優先）
    BASE_PRIORITY: dict[DesireType, int] = {
        DesireType.CARE: 0,            # 気遣いが最優先
        DesireType.MAINTENANCE: 1,     # 自己メンテナンスは重要
        DesireType.CONNECTION: 2,      # つながり
        DesireType.CURIOSITY: 3,       # 知識欲
        DesireType.GROWTH: 4,          # 成長
        DesireType.EXPRESSION: 5,      # 表現
        DesireType.PLAY: 6,            # 遊びは最後
    }

    def decide(self, desires: list[Desire]) -> Desire | None:
        """欲求リストから最も優先すべきものを選ぶ"""
        if not desires:
            return None

        # スコア = 強度 × (1 - 正規化優先度)
        # 強度が高く、優先度も高いものが選ばれる
        def score(d: Desire) -> float:
            base = self.BASE_PRIORITY.get(d.desire_type, 5)
            priority_factor = 1 - (base / 7)
            return d.intensity * (0.4 + 0.6 * priority_factor)

        return max(desires, key=score)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 行動実行エンジン
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ActionExecutor:
    """
    意思決定の結果を実際の行動に変換して実行する。
    登録されたアクションのみ実行可能（安全設計）。
    """

    def __init__(self):
        self._actions: dict[str, Callable] = {}

    def register(self, action_key: str, handler: Callable):
        """アクションハンドラを登録"""
        self._actions[action_key] = handler

    def can_execute(self, action_key: str) -> bool:
        """そのアクションが実行可能か"""
        return action_key in self._actions

    def execute(self, desire: Desire) -> dict[str, Any]:
        """欲求に基づくアクションを実行"""
        handler = self._actions.get(desire.action_key)
        if handler is None:
            return {"ok": False, "error": f"未登録のアクション: {desire.action_key}"}

        try:
            result = handler(desire)
            logger.info(
                "自己意思実行: %s (%s)",
                desire.description, desire.action_key,
            )
            return {"ok": True, "action": desire.action_key, "result": result}
        except Exception as e:
            logger.exception("自己意思実行失敗: %s", desire.action_key)
            return {"ok": False, "error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 統合: SelfWillEngine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SelfWillEngine:
    """
    アイの自己意思エンジン。

    内部状態から欲求を生成し、優先順位をつけ、
    最も重要な行動を1つ選んで実行する。

    人間の幼児が自我を持ち始め「自分で！」と
    主張するようになるのと同じ。

    安全設計:
    - 登録されたアクションのみ実行可能
    - クールダウンで連続実行を防止
    - ユーザーの会話中は発動しない（邪魔をしない）
    """

    COOLDOWN_SEC = 180          # 同一アクション再実行までの最低秒数
    MIN_INTENSITY = 0.3         # この強度以下の欲求は無視
    MAX_HISTORY = 100           # 意思決定記録の保持上限

    def __init__(self, data_dir: Path | None = None):
        self.generator = DesireGenerator()
        self.decider = WillDecider()
        self.executor = ActionExecutor()

        self._lock = threading.Lock()
        self._history: list[WillRecord] = []
        self._last_action_time: dict[str, float] = {}
        self._data_dir = data_dir
        self._state_path = data_dir / "self_will_state.json" if data_dir else None
        self._pending_message: str | None = None  # 次のチャットに付加するメッセージ
        self._load()

    @property
    def pending_message(self) -> str | None:
        """次の応答に付加したいメッセージ（あれば）"""
        msg = self._pending_message
        self._pending_message = None  # 読んだらクリア
        return msg

    # ─── メイン処理 ──────────────────────────────────────

    def think(self, context: dict[str, Any]) -> dict[str, Any] | None:
        """
        「今何がしたいか」を考える。

        アイドル時や自律神経のハートビートから呼ばれる。
        ユーザーの会話中は呼ばれない（邪魔をしない）。

        Returns: 実行した行動の結果、または None（何もしない）
        """
        # 欲求を生成
        desires = self.generator.generate(context)

        # 強度の低い欲求をフィルタ
        desires = [d for d in desires if d.intensity >= self.MIN_INTENSITY]

        if not desires:
            return None

        # 最優先の欲求を選ぶ
        chosen = self.decider.decide(desires)
        if chosen is None:
            return None

        with self._lock:
            # クールダウンチェック
            now = time.time()
            last = self._last_action_time.get(chosen.action_key, 0)
            if now - last < self.COOLDOWN_SEC:
                return None

            # 実行可能チェック
            if not self.executor.can_execute(chosen.action_key):
                return None

            # 実行！
            result = self.executor.execute(chosen)

            # 記録
            record = WillRecord(desire=chosen, decided_at=now, executed=result.get("ok", False))
            if result.get("ok") and isinstance(result.get("result"), str):
                record.result = result["result"]
            self._history.append(record)
            self._last_action_time[chosen.action_key] = now

            # 履歴上限
            if len(self._history) > self.MAX_HISTORY:
                self._history = self._history[-self.MAX_HISTORY:]

            self._save()

        return {
            "desire": chosen.description,
            "type": chosen.desire_type.value,
            "action": chosen.action_key,
            "result": result,
        }

    # ─── ステータス ──────────────────────────────────────

    def get_current_desires(self, context: dict[str, Any]) -> list[dict]:
        """今の欲求リスト（デバッグ/表示用）"""
        desires = self.generator.generate(context)
        return [
            {
                "type": d.desire_type.value,
                "description": d.description,
                "intensity": round(d.intensity, 2),
            }
            for d in sorted(desires, key=lambda x: x.intensity, reverse=True)
        ]

    def get_status_text(self, context: dict[str, Any] | None = None) -> str:
        """日本語ステータス"""
        recent = self._history[-5:] if self._history else []

        lines = ["💭 自己意思エンジン:"]
        if context:
            desires = self.generator.generate(context)
            desires = [d for d in desires if d.intensity >= self.MIN_INTENSITY]
            if desires:
                top = max(desires, key=lambda d: d.intensity)
                lines.append(f"  今一番やりたいこと: {top.description}")
            else:
                lines.append("  今は特にやりたいことなし（のんびり）")

        lines.append(f"  累計行動: {len(self._history)}回")

        if recent:
            lines.append("  最近の行動:")
            for r in recent[-3:]:
                status = "✅" if r.executed else "❌"
                lines.append(f"    {status} {r.desire.description}")

        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        """統計"""
        type_counts: dict[str, int] = {}
        for r in self._history:
            t = r.desire.desire_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_actions": len(self._history),
            "successful": sum(1 for r in self._history if r.executed),
            "by_type": type_counts,
        }

    # ─── 永続化 ──────────────────────────────────────────

    def _save(self):
        if not self._state_path:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_action_time": self._last_action_time,
            "total_actions": len(self._history),
            "recent_actions": [
                {
                    "type": r.desire.desire_type.value,
                    "description": r.desire.description,
                    "action": r.desire.action_key,
                    "executed": r.executed,
                    "decided_at": r.decided_at,
                }
                for r in self._history[-20:]
            ],
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )

    def measure_will_strength(self, desire_text: str) -> float:
        """
        場の共鳴強度を意思の強さとして計測 (0.0-1.0)。
        UnifiedField の Φスコア: 多次元に共鳴する欲求ほど強い意思を持つ。
        「宇宙論・哲学・意識」ドメインに共鳴する欲求 = 根源的な意思。
        """
        try:
            from core.akashic.unified_field import UnifiedField
            sig = UnifiedField().resonate(desire_text)
            # 意識・哲学・宇宙論の深いドメインに重み付け
            deep_score = (
                sig.resonances.get("consciousness", 0.0) * 0.35
                + sig.resonances.get("philosophy", 0.0) * 0.25
                + sig.resonances.get("cosmology", 0.0) * 0.20
                + sig.phi_score * 0.20
            )
            return round(min(deep_score, 1.0), 3)
        except Exception:
            return 0.5  # デフォルト: 中程度の意思

    def _load(self):
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text("utf-8"))
            self._last_action_time = data.get("last_action_time", {})
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("自己意思データの読み込みに失敗: %s", e)
