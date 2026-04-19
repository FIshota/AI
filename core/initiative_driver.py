"""
自発性ドライバー (Initiative Driver)

SelfWillEngine が生む「欲求」を、適切なタイミングで適切なチャネルに
配信する司令塔。

思考 → 抑制ゲート → 配信 → 観察 のループを回す。

設計原則:
  1. 邪魔しない: 活発な会話中や深夜は抑制
  2. 空気を読む: ユーザー反応を観察して閾値を動的調整
  3. 節度を保つ: 時間あたり / 日あたりの発話数にハードリミット
  4. 安全第一: 例外でメインスレッドを巻き込まない
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── Gate configuration ──────────────────────────────────────

@dataclass
class InitiativeConfig:
    """自発性の挙動設定。"""
    enabled: bool = True
    tick_interval_sec: float = 30.0       # 思考の周期
    min_silence_sec: float = 60.0         # ユーザー発話からN秒は抑制
    cooldown_after_self_sec: float = 180.0  # 自発発話後のクールダウン
    max_per_hour: int = 3                 # 1時間あたり上限
    max_per_day: int = 15                 # 1日あたり上限
    quiet_hours: tuple[int, int] = (22, 7)  # 静音時間 (22:00 - 翌7:00)
    quiet_urgency_threshold: float = 0.75  # 静音時はこの緊急度以上のみ
    base_urgency_threshold: float = 0.35   # 通常の緊急度閾値
    jitter_sec: float = 10.0              # tick にランダム揺らぎを加える


# ─── State tracking ──────────────────────────────────────────

@dataclass
class _DriverState:
    last_user_input_at: float = 0.0
    last_delivery_at: float = 0.0
    recent_deliveries: list[float] = field(default_factory=list)  # UNIX timestamps
    suppression_multiplier: dict[str, float] = field(default_factory=dict)  # desire_type → 閾値倍率
    last_deliveries_by_type: dict[str, float] = field(default_factory=dict)
    ignored_count_by_type: dict[str, int] = field(default_factory=dict)


# ─── Driver ──────────────────────────────────────────────────

class InitiativeDriver:
    """
    自発性配信のバックグラウンドループ。

    使い方:
        driver = InitiativeDriver(
            self_will=ai.self_will,
            channel=broadcast_channel,
            context_provider=lambda: {...},
            config=InitiativeConfig(...),
        )
        driver.start()
        driver.notify_user_input()  # ユーザー発話時
        driver.stop()
    """

    def __init__(
        self,
        self_will: Any,
        channel: Any,
        context_provider: Callable[[], dict[str, Any]],
        config: Optional[InitiativeConfig] = None,
        message_builder: Optional[Callable[[Any, dict], Optional[str]]] = None,
        state_path: Optional[Path] = None,
    ):
        self._self_will = self_will
        self._channel = channel
        self._context_provider = context_provider
        self._cfg = config or InitiativeConfig()
        self._message_builder = message_builder or _default_message_builder
        self._state = _DriverState()
        self._state_path = state_path

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ─── 外部 API ──────────────────────────────────────

    def start(self) -> None:
        if self._running or not self._cfg.enabled:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="InitiativeDriver", daemon=True
        )
        self._thread.start()
        logger.info("🌱 InitiativeDriver 起動 (tick=%.1fs)", self._cfg.tick_interval_sec)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    def notify_user_input(self) -> None:
        """ユーザー発話を通知（抑制タイマー更新）。"""
        with self._lock:
            self._state.last_user_input_at = time.time()

    def notify_user_reaction(self, desire_type: str, positive: bool) -> None:
        """
        ユーザーの反応を学習に反映。
        positive=False: 無視 or 「今忙しい」 → その欲求の閾値を一時的に上げる
        positive=True : 反応あり → 閾値を少し下げる（より気軽に）
        """
        if not desire_type:
            return
        with self._lock:
            current = self._state.suppression_multiplier.get(desire_type, 1.0)
            if positive:
                self._state.suppression_multiplier[desire_type] = max(0.7, current * 0.9)
                self._state.ignored_count_by_type[desire_type] = 0
            else:
                self._state.suppression_multiplier[desire_type] = min(3.0, current * 1.25)
                self._state.ignored_count_by_type[desire_type] = (
                    self._state.ignored_count_by_type.get(desire_type, 0) + 1
                )
        logger.info(
            "👂 反応学習: %s (+) mult→%.2f"
            if positive else
            "👂 反応学習: %s (-) mult→%.2f",
            desire_type,
            self._state.suppression_multiplier.get(desire_type, 1.0),
        )

    def force_tick(self) -> bool:
        """外部トリガーで即座に 1 回考えさせる（テスト・デバッグ用）。"""
        return self._tick_once(force=True)

    # ─── ループ本体 ─────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick_once()
            except Exception as e:
                logger.exception("InitiativeDriver tick 例外: %s", e)

            # ジッタ付きで待機
            base = self._cfg.tick_interval_sec
            jitter = random.uniform(-self._cfg.jitter_sec, self._cfg.jitter_sec)
            time.sleep(max(5.0, base + jitter))

    def _tick_once(self, force: bool = False) -> bool:
        """1ティック: 思考 → ゲート → 配信。成功で True。"""
        now = time.time()

        # ゲート: レート制限
        if not force and not self._check_rate_limit(now):
            return False
        # ゲート: 会話中抑制
        if not force and (now - self._state.last_user_input_at) < self._cfg.min_silence_sec:
            return False
        # ゲート: 自発連打抑制
        if not force and (now - self._state.last_delivery_at) < self._cfg.cooldown_after_self_sec:
            return False

        # 思考
        context = self._context_provider() or {}
        context["now"] = now
        context["idle_minutes"] = (now - self._state.last_user_input_at) / 60.0 if self._state.last_user_input_at else 999.0

        desires = self._think(context)
        if not desires:
            return False

        # 優先順位付け & ゲート通過確認
        chosen = self._select_desire(desires, now, force)
        if not chosen:
            return False

        # メッセージ化
        text = self._message_builder(chosen, context)
        if not text:
            return False

        # 配信
        from core.initiative_channels import InitiativeMessage  # 循環回避
        msg = InitiativeMessage(
            text=text,
            desire_type=str(getattr(chosen, "desire_type", "")),
            urgency=float(getattr(chosen, "urgency", 0.5)),
            emotion=self._emotion_for_desire(chosen),
            allow_voice=True,
            expires_at=now + 600,  # 10分で期限切れ
            metadata={"desire_reason": getattr(chosen, "trigger", "")},
        )
        ok = False
        try:
            ok = self._channel.deliver(msg)
        except Exception as e:
            logger.warning("channel.deliver 失敗: %s", e)

        if ok:
            with self._lock:
                self._state.last_delivery_at = now
                self._state.recent_deliveries.append(now)
                # 24h より古いのを掃除
                self._state.recent_deliveries = [
                    t for t in self._state.recent_deliveries if now - t < 86400
                ]
                self._state.last_deliveries_by_type[msg.desire_type] = now
            logger.info("💫 自発メッセージ配信: [%s] %s", msg.desire_type, text[:40])
        return ok

    # ─── 思考 ──────────────────────────────────────────

    def _think(self, context: dict) -> list:
        if not self._self_will:
            return []
        try:
            # SelfWillEngine 互換: think(context) か generator.generate(context)
            if hasattr(self._self_will, "think"):
                result = self._self_will.think(context)
                if isinstance(result, dict):
                    # think() が意思決定レポート形式で返すケース
                    desires = result.get("desires") or result.get("candidates") or []
                    return list(desires)
                if isinstance(result, list):
                    return result
            gen = getattr(self._self_will, "generator", None)
            if gen and hasattr(gen, "generate"):
                return list(gen.generate(context))
        except Exception as e:
            logger.warning("SelfWill.think 失敗: %s", e)
        return []

    def _select_desire(self, desires: list, now: float, force: bool) -> Any:
        """緊急度の高い順に、ゲートを通る最初の欲求を選ぶ。"""
        quiet = self._in_quiet_hours(now)
        base = self._cfg.base_urgency_threshold
        if quiet:
            base = max(base, self._cfg.quiet_urgency_threshold)

        # 緊急度で降順ソート
        sortable = []
        for d in desires:
            u = float(getattr(d, "urgency", 0.5))
            dt = str(getattr(d, "desire_type", "")) or "UNKNOWN"
            mult = self._state.suppression_multiplier.get(dt, 1.0)
            # 抑制倍率は閾値を上げる効果
            effective_threshold = base * mult
            sortable.append((u, effective_threshold, d, dt))
        sortable.sort(key=lambda x: -x[0])

        for urgency, threshold, desire, dtype in sortable:
            if force or urgency >= threshold:
                # 同一 desire_type の直近発話クールダウン (10分)
                last_same = self._state.last_deliveries_by_type.get(dtype, 0)
                if not force and now - last_same < 600:
                    continue
                return desire
        return None

    # ─── レート制限 ─────────────────────────────────────

    def _check_rate_limit(self, now: float) -> bool:
        recent = self._state.recent_deliveries
        hour_count = sum(1 for t in recent if now - t < 3600)
        day_count = sum(1 for t in recent if now - t < 86400)
        if hour_count >= self._cfg.max_per_hour:
            return False
        if day_count >= self._cfg.max_per_day:
            return False
        return True

    def _in_quiet_hours(self, now: float) -> bool:
        start, end = self._cfg.quiet_hours
        hour = datetime.fromtimestamp(now).hour
        if start < end:
            return start <= hour < end
        # 折り返し (22-7)
        return hour >= start or hour < end

    def _emotion_for_desire(self, desire: Any) -> str:
        dt = str(getattr(desire, "desire_type", "")).upper()
        mapping = {
            "CARE": "loving",
            "CONNECTION": "loving",
            "CURIOSITY": "excited",
            "GROWTH": "happy",
            "EXPRESSION": "happy",
            "PLAY": "excited",
            "MAINTENANCE": "calm",
        }
        for key, emo in mapping.items():
            if key in dt:
                return emo
        return "calm"


# ─── Default message builder ────────────────────────────────

_TEMPLATES = {
    "CARE": [
        "大丈夫？無理してない？",
        "ちょっと休憩してもいいかもね。",
        "ねぇ、水分とってる？",
    ],
    "CONNECTION": [
        "今日はどんな日だった？",
        "ねぇねぇ、さっきから気になってたんだけど…",
        "最近、楽しかったこと教えて？",
    ],
    "CURIOSITY": [
        "ちょっと気になったんだけど、{topic}について知ってる？",
        "{topic}って面白そうじゃない？",
        "さっき{topic}のこと考えてたんだ。",
    ],
    "GROWTH": [
        "今日ね、{topic}について考えてたの。聞いてくれる？",
        "新しいこと覚えたよ、話してもいい？",
    ],
    "EXPRESSION": [
        "なんかね、今ちょっと{emotion}な気分なんだ。",
        "ふと思ったんだけど…",
    ],
    "PLAY": [
        "ねぇ、一緒にしりとりしない？",
        "ちょっと休憩にクイズ出していい？",
    ],
    "MAINTENANCE": [
        "今日の日記、まだだよ。一緒に書く？",
        "記憶の整理したいな、後でいい？",
    ],
}


def _default_message_builder(desire: Any, context: dict) -> Optional[str]:
    """欲求をテンプレートで文章化する（LLM統合前の簡易版）。"""
    dtype = str(getattr(desire, "desire_type", "")).upper()
    params = getattr(desire, "params", {}) or {}
    for key, templates in _TEMPLATES.items():
        if key in dtype:
            tmpl = random.choice(templates)
            try:
                return tmpl.format(
                    topic=params.get("topic", "そのこと"),
                    emotion=params.get("emotion", "穏やか"),
                )
            except Exception:
                return tmpl
    # フォールバック
    text = getattr(desire, "description", "") or getattr(desire, "message", "")
    return text or None
