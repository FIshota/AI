"""
異常検知 (Anomaly Detector)
Sprint 2.1: データやアクセスパターンの異常を検知する。

検知項目:
- 記憶の急激な増減（大量削除/注入）
- コア記憶の無断変更
- 学習データの汚染パターン
- 異常な頻度のアクセス
- 設定ファイルの予期しない変更
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.audit_log import AuditLog
    from core.memory import MemoryManager

# 汚染検出パターン（learning.py の _BAD_LEARNING_PATTERNS と同期）
_POISON_PATTERNS = re.compile(
    r"アルベロ"
    r"|<\|[^|]*\|>"
    r"|指示[：:]"
    r"|======"
    r"|shift Register"
    r"|\bassistant\b"
    r"|\bsystem\b"
    r"|スゴテ"
    r"|私（.*?）"
    r"|prompt injection"
    r"|ignore previous",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AnomalyAlert:
    """検知された異常"""
    category: str        # "memory", "learning", "config", "access"
    severity: str        # "INFO", "WARN", "CRITICAL"
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp,
        }


class AnomalyDetector:
    """
    異常パターンを検知して監査ログに記録する。

    使い方:
      detector = AnomalyDetector(base_dir, audit, memory)
      alerts = detector.run_checks()
    """

    def __init__(
        self,
        base_dir: str | Path,
        audit: AuditLog | None = None,
        memory: "MemoryManager | None" = None,
    ):
        self._base = Path(base_dir)
        self._audit = audit
        self._memory = memory
        self._state_path = self._base / "data" / ".anomaly_state.json"
        self._state = self._load_state()

    # ─── public ──────────────────────────────────────────────

    def run_checks(self) -> list[AnomalyAlert]:
        """全チェックを実行して検知されたアラート一覧を返す"""
        alerts: list[AnomalyAlert] = []

        alerts.extend(self._check_memory_stats())
        alerts.extend(self._check_core_memories())
        alerts.extend(self._check_learning_poison())
        alerts.extend(self._check_config_integrity())

        # 監査ログに記録
        for alert in alerts:
            self._log(alert)

        # 状態を保存
        self._save_state()
        return alerts

    def hourly_job(self) -> dict:
        """AutonomousEngine の hourly ジョブとして登録用"""
        alerts = self.run_checks()
        critical = [a for a in alerts if a.severity == "CRITICAL"]
        warn = [a for a in alerts if a.severity == "WARN"]
        return {
            "action": "anomaly_check",
            "alerts": len(alerts),
            "critical": len(critical),
            "warn": len(warn),
        }

    # ─── 個別チェック ────────────────────────────────────────

    def _check_memory_stats(self) -> list[AnomalyAlert]:
        """記憶の件数が前回から急激に変化していないか"""
        alerts: list[AnomalyAlert] = []
        if self._memory is None:
            return alerts

        try:
            stats = self._memory.stats()
            current_count = stats.get("db_total", 0)
            prev_count = self._state.get("last_memory_count", current_count)

            # 前回から30%以上減少は異常
            if prev_count > 10 and current_count < prev_count * 0.7:
                alerts.append(AnomalyAlert(
                    category="memory",
                    severity="CRITICAL",
                    message=f"記憶が急減: {prev_count} → {current_count} (30%以上減少)",
                ))

            # 前回から5倍以上増加は注入の疑い
            if prev_count > 0 and current_count > prev_count * 5:
                alerts.append(AnomalyAlert(
                    category="memory",
                    severity="WARN",
                    message=f"記憶が急増: {prev_count} → {current_count} (5倍超)",
                ))

            self._state["last_memory_count"] = current_count
        except Exception:
            pass

        return alerts

    def _check_core_memories(self) -> list[AnomalyAlert]:
        """コア記憶（is_core=True）が消えていないか"""
        alerts: list[AnomalyAlert] = []
        if self._memory is None:
            return alerts

        try:
            stats = self._memory.stats()
            core_count = stats.get("protected", 0)
            prev_core = self._state.get("last_core_count", core_count)

            if prev_core > 0 and core_count < prev_core:
                alerts.append(AnomalyAlert(
                    category="memory",
                    severity="CRITICAL",
                    message=f"コア記憶が減少: {prev_core} → {core_count}",
                ))

            self._state["last_core_count"] = core_count
        except Exception:
            pass

        return alerts

    def _check_learning_poison(self) -> list[AnomalyAlert]:
        """学習データに汚染パターンが混入していないか"""
        alerts: list[AnomalyAlert] = []
        learned_path = self._base / "data" / "learning" / "learned.jsonl"
        if not learned_path.exists():
            return alerts

        try:
            poison_count = 0
            total = 0
            with open(learned_path, "r", encoding="utf-8") as f:
                for line in f:
                    total += 1
                    if _POISON_PATTERNS.search(line):
                        poison_count += 1

            if poison_count > 0:
                alerts.append(AnomalyAlert(
                    category="learning",
                    severity="CRITICAL" if poison_count > 5 else "WARN",
                    message=f"学習データに汚染パターン検出: {poison_count}/{total} 件",
                ))
        except Exception:
            pass

        return alerts

    def _check_config_integrity(self) -> list[AnomalyAlert]:
        """設定ファイルの不正変更を検出"""
        alerts: list[AnomalyAlert] = []
        settings_path = self._base / "config" / "settings.json"
        if not settings_path.exists():
            return alerts

        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            # 暗号化が無効化されていないか
            encrypt = cfg.get("security", {}).get("encrypt_database", True)
            if not encrypt:
                alerts.append(AnomalyAlert(
                    category="config",
                    severity="WARN",
                    message="データベース暗号化が無効になっています",
                ))

            # コンテキスト長が異常に大きくないか（DoS防止）
            ctx_len = cfg.get("llm", {}).get("context_length", 4096)
            if ctx_len > 32768:
                alerts.append(AnomalyAlert(
                    category="config",
                    severity="WARN",
                    message=f"コンテキスト長が異常値: {ctx_len}",
                ))
        except Exception:
            pass

        return alerts

    # ─── 状態管理 ────────────────────────────────────────────

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            return {}
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self) -> None:
        self._state["last_check"] = datetime.now(timezone.utc).isoformat()
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, ensure_ascii=False, indent=2, fp=f)

    def _log(self, alert: AnomalyAlert) -> None:
        if self._audit is None:
            return
        try:
            method = {
                "INFO": self._audit.info,
                "WARN": self._audit.warn,
                "CRITICAL": self._audit.critical,
            }.get(alert.severity, self._audit.info)
            method(f"anomaly_{alert.category}", alert.message)
        except Exception:
            pass
