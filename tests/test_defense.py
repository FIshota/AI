"""
Sprint 2.1: 防御システムのテスト
- AuditLog: チェーン整合性、追記、改ざん検知
- IntegrityMonitor: マニフェスト作成、変更検知
- BackupRotator: バックアップ作成、ローテーション
- AnomalyDetector: 記憶急変、汚染検知
- KillSwitch: ロックダウン、解除
- HostGuardian: スコア計算
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path


# ── AuditLog ─────────────────────────────────────────────

class TestAuditLog:
    def test_log_creates_entry(self, tmp_path: Path):
        from core.audit_log import AuditLog
        audit = AuditLog(tmp_path)
        entry = audit.info("test_event", "test detail")
        assert entry["event"] == "test_event"
        assert entry["sev"] == "INFO"
        assert entry["hash"] != ""
        assert (tmp_path / "audit.jsonl").exists()

    def test_chain_is_valid(self, tmp_path: Path):
        from core.audit_log import AuditLog
        audit = AuditLog(tmp_path)
        audit.info("event1", "detail1")
        audit.warn("event2", "detail2")
        audit.critical("event3", "detail3")
        result = audit.verify_chain()
        assert result["valid"] is True
        assert result["total"] == 3

    def test_chain_detects_tamper(self, tmp_path: Path):
        from core.audit_log import AuditLog
        audit = AuditLog(tmp_path)
        audit.info("event1")
        audit.info("event2")

        # 改ざん: 2行目のイベント名を書き換え
        log_path = tmp_path / "audit.jsonl"
        lines = log_path.read_text("utf-8").splitlines()
        entry = json.loads(lines[1])
        entry["event"] = "TAMPERED"
        lines[1] = json.dumps(entry, ensure_ascii=False)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = audit.verify_chain()
        assert result["valid"] is False
        assert result["broken_at"] == 2

    def test_get_recent(self, tmp_path: Path):
        from core.audit_log import AuditLog
        audit = AuditLog(tmp_path)
        for i in range(5):
            audit.info(f"event_{i}")
        recent = audit.get_recent(limit=3)
        assert len(recent) == 3
        assert recent[-1]["event"] == "event_4"

    def test_get_recent_by_severity(self, tmp_path: Path):
        from core.audit_log import AuditLog
        audit = AuditLog(tmp_path)
        audit.info("info1")
        audit.warn("warn1")
        audit.critical("crit1")
        warns = audit.get_recent(severity="WARN")
        assert len(warns) == 1
        assert warns[0]["event"] == "warn1"


# ── IntegrityMonitor ─────────────────────────────────────

class TestIntegrityMonitor:
    def _setup_project(self, tmp_path: Path) -> Path:
        (tmp_path / "data").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "personality").mkdir()
        (tmp_path / "data" / "emotion_state.json").write_text("{}")
        (tmp_path / "config" / "settings.json").write_text("{}")
        return tmp_path

    def test_first_run_creates_manifest(self, tmp_path: Path):
        from core.integrity_monitor import IntegrityMonitor
        base = self._setup_project(tmp_path)
        mon = IntegrityMonitor(base)
        result = mon.startup_check()
        assert result["status"] == "new"
        assert (base / "data" / ".integrity_manifest.json").exists()

    def test_detect_modification(self, tmp_path: Path):
        from core.integrity_monitor import IntegrityMonitor
        base = self._setup_project(tmp_path)
        mon = IntegrityMonitor(base)
        mon.refresh()

        # ファイルを変更
        (base / "data" / "emotion_state.json").write_text('{"joy": 1.0}')
        result = mon.verify()
        assert result["status"] == "warn"
        assert "data/emotion_state.json" in result["modified"]

    def test_detect_missing_file(self, tmp_path: Path):
        from core.integrity_monitor import IntegrityMonitor
        base = self._setup_project(tmp_path)
        mon = IntegrityMonitor(base)
        mon.refresh()

        # ファイルを削除
        (base / "data" / "emotion_state.json").unlink()
        result = mon.verify()
        assert "data/emotion_state.json" in result["missing"]

    def test_detect_added_file(self, tmp_path: Path):
        from core.integrity_monitor import IntegrityMonitor
        base = self._setup_project(tmp_path)
        mon = IntegrityMonitor(base)
        mon.refresh()

        # 新しいファイルを追加
        (base / "data" / "new_file.json").write_text("{}")
        result = mon.verify()
        assert "data/new_file.json" in result["added"]


# ── BackupRotator ────────────────────────────────────────

class TestBackupRotator:
    def _setup_project(self, tmp_path: Path) -> Path:
        (tmp_path / "data").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "personality").mkdir()
        (tmp_path / "data" / "test.json").write_text('{"test": true}')
        (tmp_path / "config" / "settings.json").write_text('{}')
        return tmp_path

    def test_create_backup(self, tmp_path: Path):
        from core.backup_rotator import BackupRotator
        base = self._setup_project(tmp_path)
        rotator = BackupRotator(base, max_generations=3)
        result = rotator.create_backup(label="test")
        assert result["files"] > 0
        assert result["size_mb"] >= 0
        assert Path(result["path"]).exists()

    def test_list_backups(self, tmp_path: Path):
        from core.backup_rotator import BackupRotator
        base = self._setup_project(tmp_path)
        rotator = BackupRotator(base)
        rotator.create_backup(label="a")
        rotator.create_backup(label="b")
        backups = rotator.list_backups()
        assert len(backups) == 2

    def test_rotation(self, tmp_path: Path):
        from core.backup_rotator import BackupRotator
        base = self._setup_project(tmp_path)
        rotator = BackupRotator(base, max_generations=2)
        rotator.create_backup(label="1")
        rotator.create_backup(label="2")
        rotator.create_backup(label="3")
        # max_generations=2 なので最古の1個は削除される
        backups = rotator.list_backups()
        assert len(backups) <= 2

    def test_verify_backup(self, tmp_path: Path):
        from core.backup_rotator import BackupRotator
        base = self._setup_project(tmp_path)
        rotator = BackupRotator(base)
        result = rotator.create_backup()
        name = Path(result["path"]).name
        assert rotator.verify_backup(name) is True


# ── AnomalyDetector ──────────────────────────────────────

class TestAnomalyDetector:
    def test_no_alerts_on_clean_state(self, tmp_path: Path):
        from core.anomaly_detector import AnomalyDetector
        (tmp_path / "data").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(
            '{"security": {"encrypt_database": true}, "llm": {"context_length": 4096}}'
        )
        detector = AnomalyDetector(tmp_path)
        alerts = detector.run_checks()
        # 初回は基準値が無いのでアラートなし
        critical = [a for a in alerts if a.severity == "CRITICAL"]
        assert len(critical) == 0

    def test_detect_learning_poison(self, tmp_path: Path):
        from core.anomaly_detector import AnomalyDetector
        (tmp_path / "data" / "learning").mkdir(parents=True)
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text("{}")
        # 汚染データを仕込む
        learned = tmp_path / "data" / "learning" / "learned.jsonl"
        learned.write_text(
            '{"user": "test", "ai": "アルベロです"}\n'
            '{"user": "test2", "ai": "正常な回答"}\n'
        )
        detector = AnomalyDetector(tmp_path)
        alerts = detector.run_checks()
        poison = [a for a in alerts if a.category == "learning"]
        assert len(poison) >= 1

    def test_detect_disabled_encryption(self, tmp_path: Path):
        from core.anomaly_detector import AnomalyDetector
        (tmp_path / "data").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(
            '{"security": {"encrypt_database": false}}'
        )
        detector = AnomalyDetector(tmp_path)
        alerts = detector.run_checks()
        config_alerts = [a for a in alerts if a.category == "config"]
        assert len(config_alerts) >= 1


# ── KillSwitch ───────────────────────────────────────────

class TestKillSwitch:
    def test_lockdown_and_unlock(self, tmp_path: Path):
        from core.kill_switch import KillSwitch
        (tmp_path / "data").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(
            '{"autonomous": {"allow_network": true}}'
        )
        ks = KillSwitch(tmp_path)
        assert ks.is_locked is False

        ks.lockdown("test")
        assert ks.is_locked is True

        # ネットワークが無効化されているか
        with open(tmp_path / "config" / "settings.json") as f:
            cfg = json.load(f)
        assert cfg["autonomous"]["allow_network"] is False

        # 解除（正しいキーワード）
        result = ks.unlock(confirm="アイ解除")
        assert result["unlocked"] is True
        assert ks.is_locked is False

    def test_unlock_wrong_keyword(self, tmp_path: Path):
        from core.kill_switch import KillSwitch
        (tmp_path / "data").mkdir()
        ks = KillSwitch(tmp_path)
        ks.lockdown("test")
        result = ks.unlock(confirm="wrong")
        assert result["unlocked"] is False


# ── HostGuardian ─────────────────────────────────────────

class TestHostGuardian:
    def test_score_returns_dict(self, tmp_path: Path):
        from core.host_guardian import HostGuardian
        (tmp_path / "data").mkdir()
        guardian = HostGuardian(tmp_path)
        result = guardian.get_security_score()
        assert "score" in result
        assert 0 <= result["score"] <= 100

    def test_summary_text(self, tmp_path: Path):
        from core.host_guardian import HostGuardian
        (tmp_path / "data").mkdir()
        guardian = HostGuardian(tmp_path)
        text = guardian.get_summary_text()
        assert "セキュリティスコア" in text
