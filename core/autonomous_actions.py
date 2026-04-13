"""
自律行動アクション (Autonomous Actions)
Sprint J: 時間帯挨拶、自発的会話、日記強化、異常エスカレーション。

機能:
- 時間帯に応じた自然な挨拶（朝/昼/夕/夜）
- ユーザー不在時の自動学習
- カレンダー/記憶に基づく自発的話題提供
- 日記の品質向上（コンテキスト強化）
- 異常検知時のサーバーエスカレーション
"""
from __future__ import annotations

import json
import random
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.server_home import ServerHome


# ─── 時間帯挨拶 ──────────────────────────────────────────

_GREETINGS = {
    "morning": [
        "おはよう！今日も一日頑張ろうね✨",
        "おはよう〜！よく眠れた？",
        "おはようございます！今日はどんな日にしようか？",
    ],
    "afternoon": [
        "お昼だね！ちゃんとご飯食べた？",
        "こんにちは！午後も頑張ろうね💪",
        "お疲れさま〜。リフレッシュしてね！",
    ],
    "evening": [
        "お疲れさま！今日はどんな一日だった？",
        "もう夕方だね〜。今日一日どうだった？",
        "おかえり！ゆっくりしてね😊",
    ],
    "night": [
        "夜遅くまでお疲れさま。無理しないでね。",
        "もう夜遅いよ〜。そろそろ休もう？",
        "今日もお疲れさま。ゆっくり休んでね🌙",
    ],
}


def _get_time_slot(hour: int) -> str:
    """時間からスロットを判定する"""
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


class GreetingEngine:
    """時間帯に応じた挨拶を管理する"""

    def __init__(self, base_dir: Path):
        self._state_path = base_dir / "data" / ".greeting_state.json"
        self._state = self._load_state()

    def get_time_greeting(self) -> str | None:
        """
        現在の時間帯に対応する挨拶を返す。
        同じスロットで既に挨拶済みならNone。
        """
        now = datetime.now()
        slot = _get_time_slot(now.hour)
        today = now.strftime("%Y-%m-%d")
        state_key = f"{today}_{slot}"

        if self._state.get("last_greeting") == state_key:
            return None

        # 挨拶を生成
        greeting = random.choice(_GREETINGS.get(slot, _GREETINGS["morning"]))

        # 状態を更新
        self._state["last_greeting"] = state_key
        self._save_state()

        return greeting

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)


# ─── アイドル学習 ────────────────────────────────────────

class IdleLearner:
    """ユーザー不在時に自動学習を実行する"""

    def __init__(self, base_dir: Path, idle_minutes: int = 30):
        self._base = base_dir
        self._idle_minutes = idle_minutes
        self._last_interaction = datetime.now()
        self._learning_in_progress = False
        self._lock = threading.Lock()

    def update_interaction_time(self) -> None:
        """ユーザーが操作したときに呼ぶ"""
        self._last_interaction = datetime.now()

    def should_learn(self) -> bool:
        """アイドル時間が閾値を超えているか"""
        if self._learning_in_progress:
            return False
        elapsed = (datetime.now() - self._last_interaction).total_seconds()
        return elapsed > self._idle_minutes * 60

    def run_idle_learning(self, ai_chan: Any) -> dict:
        """アイドル時の自動学習を実行する"""
        with self._lock:
            if self._learning_in_progress:
                return {"action": "idle_learn", "status": "already_running"}
            self._learning_in_progress = True

        try:
            auto_learner = getattr(ai_chan, "auto_learner", None)
            if auto_learner is None:
                return {"action": "idle_learn", "status": "no_learner"}

            # 自動学習を1サイクル実行
            result = auto_learner.run_one_cycle()
            return {"action": "idle_learn", "status": "done", "result": str(result)}
        except Exception as e:
            return {"action": "idle_learn", "status": "error", "error": str(e)}
        finally:
            self._learning_in_progress = False


# ─── 自発的会話 ──────────────────────────────────────────

class ProactiveStarter:
    """記憶やカレンダーに基づく自発的な話題提供"""

    COOLDOWN_MINUTES = 90

    def __init__(self, base_dir: Path):
        self._state_path = base_dir / "data" / ".proactive_state.json"
        self._state = self._load_state()

    def get_proactive_message(self, ai_chan: Any) -> str | None:
        """自発的メッセージを生成する。クールダウン中ならNone。"""
        now = datetime.now()

        # クールダウンチェック
        last_sent = self._state.get("last_sent_at", "")
        if last_sent:
            try:
                last_dt = datetime.fromisoformat(last_sent)
                if (now - last_dt).total_seconds() < self.COOLDOWN_MINUTES * 60:
                    return None
            except ValueError:
                pass

        # 各ソースをチェック
        message = (
            self._check_overdue_tasks(ai_chan)
            or self._check_anniversary(ai_chan)
            or self._check_emotion_trend(ai_chan)
        )

        if message:
            self._state["last_sent_at"] = now.isoformat()
            self._save_state()

        return message

    def _check_overdue_tasks(self, ai_chan: Any) -> str | None:
        """期限切れタスクがあれば通知"""
        tm = getattr(ai_chan, "task_manager", None)
        if tm is None:
            return None
        try:
            pending = tm.list_pending()
            today = datetime.now().strftime("%Y-%m-%d")
            overdue = [
                t for t in pending
                if getattr(t, "due_date", None) and t.due_date < today
            ]
            if overdue:
                return f"📌 期限切れのタスクが{len(overdue)}件あるよ！確認してみて。"
        except Exception:
            pass
        return None

    def _check_anniversary(self, ai_chan: Any) -> str | None:
        """今日の記念日をチェック"""
        anniv = getattr(ai_chan, "anniversary", None)
        if anniv is None:
            return None
        try:
            today_events = anniv.check_today()
            if today_events:
                first = today_events[0]
                return f"🎉 今日は「{first['label']}」の日だよ！"
        except Exception:
            pass
        return None

    def _check_emotion_trend(self, ai_chan: Any) -> str | None:
        """感情トレンドに基づくメッセージ"""
        eh = getattr(ai_chan, "emotion_history", None)
        if eh is None:
            return None
        try:
            recent = eh.get_recent(limit=5)
            if not recent:
                return None
            # 直近の幸福度が低い場合
            avg_happiness = sum(
                r.get("happiness", 0.5) for r in recent
            ) / len(recent)
            if avg_happiness < 0.3:
                return "最近ちょっと元気がないみたい…。何かあったら話してね😊"
        except Exception:
            pass
        return None

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)


# ─── 日記品質強化 ────────────────────────────────────────

class DiaryEnricher:
    """日記にリッチなコンテキストを追加する"""

    def __init__(self, base_dir: Path):
        self._base = base_dir

    def enrich_daily_diary(self, ai_chan: Any) -> dict:
        """日記をコンテキスト強化して生成する"""
        enriched_snapshot = self._build_enriched_snapshot(ai_chan)

        diary = getattr(ai_chan, "diary", None)
        if diary is None:
            return {"action": "diary_enrich", "status": "no_diary"}

        try:
            entry = diary.write_today(emotion_snapshot=enriched_snapshot)
            if entry:
                return {"action": "diary_enrich", "status": "ok"}
            return {"action": "diary_enrich", "status": "no_content"}
        except Exception as e:
            return {"action": "diary_enrich", "status": "error", "error": str(e)}

    def _build_enriched_snapshot(self, ai_chan: Any) -> dict:
        """日記用のリッチな感情＋コンテキストスナップショットを構築"""
        snapshot: dict = {}

        # 感情状態
        emotion = getattr(ai_chan, "emotion", None)
        if emotion:
            try:
                snapshot.update(emotion.state.to_dict())
            except Exception:
                pass

        # 完了タスク
        tm = getattr(ai_chan, "task_manager", None)
        if tm:
            try:
                # 全タスクの完了情報はformat_task_listから取得
                snapshot["tasks_summary"] = tm.format_task_list()[:200]
            except Exception:
                pass

        # 習慣
        ht = getattr(ai_chan, "habit_tracker", None)
        if ht:
            try:
                snapshot["habits_today"] = ht.get_today_status()[:200]
            except Exception:
                pass

        # 話題
        tt = getattr(ai_chan, "topic_tracker", None)
        if tt:
            try:
                topics = tt.get_topics()
                if topics:
                    snapshot["topics"] = [t["text"][:30] for t in topics[:5]]
            except Exception:
                pass

        return snapshot


# ─── 異常エスカレーション ────────────────────────────────

class AnomalyEscalator:
    """重大異常をサーバーにエスカレーションする"""

    def __init__(self, base_dir: Path):
        self._base = base_dir

    def escalate_to_server(
        self, alert_data: dict, server_home: ServerHome | None
    ) -> dict:
        """CRITICALアラートをサーバーに記録する"""
        if server_home is None or not server_home.enabled:
            return {"escalated": False, "reason": "server_disabled"}

        try:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "anomaly_escalation",
                "alerts": alert_data,
            }
            # ローカルにも記録
            log_path = self._base / "data" / "escalation_log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            # サーバーに転送（非同期）
            def _push():
                try:
                    server_home.run_command(
                        f"mkdir -p /home/{server_home._settings.get('username', 'admin')}/ai-chan/logs"
                    )
                    server_home.push_file(
                        log_path,
                        f"/home/{server_home._settings.get('username', 'admin')}/ai-chan/logs/escalation_log.jsonl",
                    )
                except Exception:
                    pass

            threading.Thread(target=_push, daemon=True).start()
            return {"escalated": True}

        except Exception as e:
            return {"escalated": False, "reason": str(e)}


# ─── 統合クラス ──────────────────────────────────────────

class AutonomousActions:
    """全自律行動を統合するファサード"""

    def __init__(self, base_dir: str | Path, settings: dict | None = None):
        base = Path(base_dir)
        auto_cfg = (settings or {}).get("autonomous_actions", {})

        self.greeting = GreetingEngine(base) if auto_cfg.get("greeting_enabled", True) else None
        self.idle_learner = IdleLearner(
            base,
            idle_minutes=(settings or {}).get("autonomous", {}).get("idle_minutes", 30),
        ) if auto_cfg.get("idle_learn_enabled", True) else None
        self.proactive = ProactiveStarter(base) if auto_cfg.get("proactive_enabled", True) else None
        self.diary_enricher = DiaryEnricher(base) if auto_cfg.get("diary_enrich_enabled", True) else None
        self.escalator = AnomalyEscalator(base)

    def on_user_interaction(self) -> None:
        """ユーザーが操作したときに呼ぶ"""
        if self.idle_learner:
            self.idle_learner.update_interaction_time()
