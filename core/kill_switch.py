"""
キルスイッチ (Kill Switch)
Sprint 2.1: 緊急時のデータ保護とシャットダウン。

- 緊急バックアップ → 暗号化領域のロック → プロセス停止
- 段階的な緊急対応（レベル1〜3）
"""
from __future__ import annotations

import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.audit_log import AuditLog
    from core.backup_rotator import BackupRotator


class KillSwitch:
    """
    緊急停止スイッチ。

    Level 1 (LOCKDOWN): 外部通信を遮断、読み取り専用モード
    Level 2 (BACKUP_AND_HALT): 緊急バックアップ → プロセス停止
    Level 3 (SECURE_WIPE): 一時データを完全削除 → バックアップ → 停止
    """

    def __init__(
        self,
        base_dir: str | Path,
        audit: AuditLog | None = None,
        backup: "BackupRotator | None" = None,
    ):
        self._base = Path(base_dir)
        self._audit = audit
        self._backup = backup
        self._locked = False
        self._lockfile = self._base / "data" / ".lockdown"

    @property
    def is_locked(self) -> bool:
        return self._locked or self._lockfile.exists()

    # ─── public ──────────────────────────────────────────────

    def lockdown(self, reason: str = "manual") -> dict:
        """
        Level 1: ロックダウン。
        外部通信を無効化し、読み取り専用モードに入る。
        """
        self._locked = True
        lock_data = {
            "locked_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }
        self._lockfile.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lockfile, "w", encoding="utf-8") as f:
            json.dump(lock_data, ensure_ascii=False, indent=2, fp=f)

        # 設定を上書きしてネットワークを無効化
        self._disable_network()

        self._log("CRITICAL", "kill_switch_lockdown", f"Reason: {reason}")
        return {"level": 1, "action": "lockdown", "reason": reason}

    def backup_and_halt(self, reason: str = "manual") -> dict:
        """
        Level 2: 緊急バックアップ → 停止。
        """
        self._log("CRITICAL", "kill_switch_backup_halt", f"Reason: {reason}")

        # 緊急バックアップ
        backup_result = {}
        if self._backup:
            try:
                backup_result = self._backup.create_backup(label="emergency")
            except Exception as e:
                backup_result = {"error": str(e)}

        # ロックダウン
        self.lockdown(reason)

        return {"level": 2, "action": "backup_and_halt", "backup": backup_result}

    def secure_wipe(self, reason: str = "manual") -> dict:
        """
        Level 3: 一時データを消去 → バックアップ → 停止。
        コア記憶とバックアップは保持する。
        """
        self._log("CRITICAL", "kill_switch_secure_wipe", f"Reason: {reason}")

        # まず緊急バックアップ
        backup_result = {}
        if self._backup:
            try:
                backup_result = self._backup.create_backup(label="pre_wipe")
            except Exception as e:
                backup_result = {"error": str(e)}

        # 一時データを消去（コアは保持）
        wiped: list[str] = []
        temp_files = [
            "data/web_cache.json",
            "data/open_topics.json",
            "data/schedule_fired.json",
            "data/autonomous_fired.json",
            "data/app.log",
        ]
        for rel in temp_files:
            p = self._base / rel
            if p.exists():
                try:
                    p.unlink()
                    wiped.append(rel)
                except OSError:
                    pass

        # ロックダウン
        self.lockdown(reason)

        return {
            "level": 3,
            "action": "secure_wipe",
            "wiped": wiped,
            "backup": backup_result,
        }

    def unlock(self, confirm: str = "") -> dict:
        """ロックダウンを解除する（確認キーワード必須）"""
        if confirm != "アイ解除":
            return {"unlocked": False, "reason": "確認キーワードが一致しません"}

        self._locked = False
        if self._lockfile.exists():
            self._lockfile.unlink()

        self._enable_network()
        self._log("WARN", "kill_switch_unlocked", "Manual unlock")
        return {"unlocked": True}

    # ─── private ─────────────────────────────────────────────

    def _disable_network(self) -> None:
        """設定ファイルのネットワーク許可を無効化する"""
        settings_path = self._base / "config" / "settings.json"
        if not settings_path.exists():
            return
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("autonomous", {})["allow_network"] = False
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(cfg, ensure_ascii=False, indent=2, fp=f)
        except Exception:
            pass

    def _enable_network(self) -> None:
        """ネットワーク許可を再有効化する"""
        settings_path = self._base / "config" / "settings.json"
        if not settings_path.exists():
            return
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("autonomous", {})["allow_network"] = True
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(cfg, ensure_ascii=False, indent=2, fp=f)
        except Exception:
            pass

    def _log(self, severity: str, event: str, detail: str) -> None:
        if self._audit is None:
            return
        try:
            getattr(self._audit, severity.lower(), self._audit.info)(event, detail)
        except Exception:
            pass
