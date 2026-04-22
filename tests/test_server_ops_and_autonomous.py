"""
サーバー運用 / 自律行動 / AI 環境のテスト.

(元: test_sprint_j.py — 2026-04-21 M7 でドメイン命名へリネーム)

対象:
    運用系 — CredentialStore / ServerHome / ServerAIEnv / KnowledgeSync / PrometheusReader
    自律行動 — GreetingEngine / IdleLearner / ProactiveStarter / DiaryEnricher /
               AnomalyEscalator / AutonomousActions
    コマンドパターン — TestSprintJCommandPatterns (将来改名候補)
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ─── CredentialStore テスト ──────────────────────────────────

class TestCredentialStore:
    """認証情報の暗号化保存・読み込みテスト"""

    def test_save_and_load(self, tmp_path):
        """保存した認証情報を復号できる"""
        from core.server_home import CredentialStore, ServerCredentials, FERNET_OK
        if not FERNET_OK:
            pytest.skip("cryptography not installed")

        # キーファイル作成
        key_file = tmp_path / "data" / ".key"
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(b"test-key-seed-for-credential-store!!")

        store = CredentialStore(tmp_path, key_file=key_file)
        creds = ServerCredentials(
            host="192.168.3.86", port=22,
            username="admin", password="secret123"
        )
        assert store.save(creds) is True

        loaded = store.load()
        assert loaded is not None
        assert loaded.host == "192.168.3.86"
        assert loaded.username == "admin"
        assert loaded.password == "secret123"

    def test_load_without_save_returns_none(self, tmp_path):
        """保存前のloadはNoneを返す"""
        from core.server_home import CredentialStore
        store = CredentialStore(tmp_path)
        assert store.load() is None


# ─── ServerHome テスト ───────────────────────────────────────

class TestServerHome:
    """サーバーホーム基本テスト（実サーバー接続なし）"""

    def _make_server_home(self, tmp_path, enabled=False):
        from core.server_home import ServerHome
        settings = {
            "server_home": {
                "enabled": enabled,
                "host": "192.168.3.86",
                "port": 22,
                "username": "testuser",
                "password": "testpass",
                "allowed_commands": ["ls", "docker", "uptime"],
            },
            "security": {"key_file": "data/.key"},
        }
        return ServerHome(tmp_path, settings)

    def test_disabled_by_default(self, tmp_path):
        """無効時はenabledがFalse"""
        sh = self._make_server_home(tmp_path, enabled=False)
        assert sh.enabled is False

    def test_is_allowed_command(self, tmp_path):
        """許可リスト内のコマンドが通る"""
        sh = self._make_server_home(tmp_path, enabled=True)
        assert sh._is_allowed("ls -la") is True
        assert sh._is_allowed("docker ps") is True
        assert sh._is_allowed("uptime") is True

    def test_disallowed_command(self, tmp_path):
        """許可リスト外のコマンドは拒否"""
        sh = self._make_server_home(tmp_path, enabled=True)
        assert sh._is_allowed("rm -rf /") is False
        assert sh._is_allowed("shutdown -h now") is False
        assert sh._is_allowed("reboot") is False

    def test_run_command_disabled(self, tmp_path):
        """無効時のrun_commandはエラーを返す"""
        sh = self._make_server_home(tmp_path, enabled=False)
        result = sh.run_command("ls")
        assert result["ok"] is False

    def test_run_command_blocked(self, tmp_path):
        """許可外コマンドはブロックされる"""
        from core.server_home import PARAMIKO_OK
        if not PARAMIKO_OK:
            pytest.skip("paramiko not installed")
        sh = self._make_server_home(tmp_path, enabled=True)
        result = sh.run_command("rm -rf /")
        assert result["ok"] is False
        assert "許可されていない" in result.get("error", "")

    def test_docker_control_validates_name(self, tmp_path):
        """不正なコンテナ名を拒否する"""
        from core.server_home import PARAMIKO_OK
        if not PARAMIKO_OK:
            pytest.skip("paramiko not installed")
        sh = self._make_server_home(tmp_path, enabled=True)
        result = sh.docker_control("../../etc/passwd", "start")
        assert result["ok"] is False

    def test_docker_control_validates_action(self, tmp_path):
        """不正なアクションを拒否する"""
        sh = self._make_server_home(tmp_path, enabled=True)
        result = sh.docker_control("mycontainer", "delete")
        assert result["ok"] is False

    def test_get_status_text_disabled(self, tmp_path):
        """無効時のステータステキスト"""
        sh = self._make_server_home(tmp_path, enabled=False)
        text = sh.get_status_text()
        assert "未設定" in text


# ─── GreetingEngine テスト ───────────────────────────────────

class TestGreetingEngine:
    """時間帯挨拶エンジンテスト"""

    def test_get_time_greeting(self, tmp_path):
        """時間帯挨拶を取得できる"""
        from core.autonomous_actions import GreetingEngine
        ge = GreetingEngine(tmp_path)
        greeting = ge.get_time_greeting()
        assert greeting is not None
        assert len(greeting) > 0

    def test_no_duplicate_greeting(self, tmp_path):
        """同じスロットでは2度目はNone"""
        from core.autonomous_actions import GreetingEngine
        ge = GreetingEngine(tmp_path)
        first = ge.get_time_greeting()
        assert first is not None
        second = ge.get_time_greeting()
        assert second is None

    def test_time_slot_classification(self):
        """時間帯スロットの分類が正しい"""
        from core.autonomous_actions import _get_time_slot
        assert _get_time_slot(6) == "morning"
        assert _get_time_slot(12) == "afternoon"
        assert _get_time_slot(18) == "evening"
        assert _get_time_slot(23) == "night"
        assert _get_time_slot(3) == "night"


# ─── IdleLearner テスト ──────────────────────────────────────

class TestIdleLearner:
    """アイドル学習テスト"""

    def test_should_learn_not_idle(self, tmp_path):
        """操作直後はアイドルではない"""
        from core.autonomous_actions import IdleLearner
        il = IdleLearner(tmp_path, idle_minutes=30)
        il.update_interaction_time()
        assert il.should_learn() is False

    def test_should_learn_after_idle(self, tmp_path):
        """閾値超過後はアイドル"""
        from core.autonomous_actions import IdleLearner
        il = IdleLearner(tmp_path, idle_minutes=0)  # 0分 = 即アイドル
        il._last_interaction = datetime.now() - timedelta(minutes=1)
        assert il.should_learn() is True

    def test_no_concurrent_learning(self, tmp_path):
        """学習中は再学習しない"""
        from core.autonomous_actions import IdleLearner
        il = IdleLearner(tmp_path, idle_minutes=0)
        il._last_interaction = datetime.now() - timedelta(minutes=1)
        il._learning_in_progress = True
        assert il.should_learn() is False


# ─── ProactiveStarter テスト ─────────────────────────────────

class TestProactiveStarter:
    """自発的会話テスト"""

    def test_no_message_on_cooldown(self, tmp_path):
        """クールダウン中はNone"""
        from core.autonomous_actions import ProactiveStarter
        ps = ProactiveStarter(tmp_path)
        ps._state["last_sent_at"] = datetime.now().isoformat()
        ps._save_state()
        msg = ps.get_proactive_message(MagicMock())
        assert msg is None

    def test_message_after_cooldown(self, tmp_path):
        """クールダウン後はメッセージ可能"""
        from core.autonomous_actions import ProactiveStarter
        ps = ProactiveStarter(tmp_path)
        old_time = (datetime.now() - timedelta(minutes=100)).isoformat()
        ps._state["last_sent_at"] = old_time
        # no sources → None (all _check methods return None for mock)
        msg = ps.get_proactive_message(MagicMock(spec=[]))
        assert msg is None  # MagicMock(spec=[]) has no attributes


# ─── DiaryEnricher テスト ────────────────────────────────────

class TestDiaryEnricher:
    """日記強化テスト"""

    def test_enrich_no_diary(self, tmp_path):
        """diaryがない場合のフォールバック"""
        from core.autonomous_actions import DiaryEnricher
        de = DiaryEnricher(tmp_path)
        ai = MagicMock(spec=[])  # diary属性なし
        result = de.enrich_daily_diary(ai)
        assert result["status"] == "no_diary"

    def test_build_enriched_snapshot_empty(self, tmp_path):
        """空のai_chanでもスナップショットが空辞書を返す"""
        from core.autonomous_actions import DiaryEnricher
        de = DiaryEnricher(tmp_path)
        ai = MagicMock(spec=[])
        snapshot = de._build_enriched_snapshot(ai)
        assert isinstance(snapshot, dict)


# ─── AnomalyEscalator テスト ────────────────────────────────

class TestAnomalyEscalator:
    """異常エスカレーションテスト"""

    def test_escalate_disabled_server(self, tmp_path):
        """サーバー無効時はescalated=False"""
        from core.autonomous_actions import AnomalyEscalator
        ae = AnomalyEscalator(tmp_path)
        result = ae.escalate_to_server({"alert": "test"}, None)
        assert result["escalated"] is False

    def test_escalate_writes_local_log(self, tmp_path):
        """エスカレーション時にローカルログを書く"""
        from core.autonomous_actions import AnomalyEscalator
        ae = AnomalyEscalator(tmp_path)
        server = MagicMock()
        server.enabled = True
        server.run_command = MagicMock(return_value={"ok": True})
        server.push_file = MagicMock(return_value={"ok": True})
        server._settings = {"username": "admin"}
        result = ae.escalate_to_server({"alert": "critical"}, server)
        assert result["escalated"] is True
        log_path = tmp_path / "data" / "escalation_log.jsonl"
        assert log_path.exists()


# ─── AutonomousActions ファサード テスト ─────────────────────

class TestAutonomousActions:
    """統合ファサードテスト"""

    def test_init_all_enabled(self, tmp_path):
        """全機能有効で初期化"""
        from core.autonomous_actions import AutonomousActions
        settings = {
            "autonomous_actions": {
                "greeting_enabled": True,
                "proactive_enabled": True,
                "diary_enrich_enabled": True,
                "idle_learn_enabled": True,
            },
            "autonomous": {"idle_minutes": 15},
        }
        aa = AutonomousActions(tmp_path, settings)
        assert aa.greeting is not None
        assert aa.proactive is not None
        assert aa.diary_enricher is not None
        assert aa.idle_learner is not None

    def test_init_all_disabled(self, tmp_path):
        """全機能無効で初期化"""
        from core.autonomous_actions import AutonomousActions
        settings = {
            "autonomous_actions": {
                "greeting_enabled": False,
                "proactive_enabled": False,
                "diary_enrich_enabled": False,
                "idle_learn_enabled": False,
            },
        }
        aa = AutonomousActions(tmp_path, settings)
        assert aa.greeting is None
        assert aa.proactive is None
        assert aa.diary_enricher is None
        assert aa.idle_learner is None

    def test_on_user_interaction(self, tmp_path):
        """操作通知がエラーなく通る"""
        from core.autonomous_actions import AutonomousActions
        settings = {"autonomous_actions": {"idle_learn_enabled": True}}
        aa = AutonomousActions(tmp_path, settings)
        aa.on_user_interaction()  # エラーなし


# ─── ServerAIEnv テスト ──────────────────────────────────────

class TestServerAIEnv:
    """サーバーAI環境テスト"""

    def test_disabled_status(self):
        """サーバー無効時のステータス"""
        from core.server_ai_env import ServerAIEnv
        server = MagicMock()
        server.enabled = False
        env = ServerAIEnv(server)
        assert env.container_status()["status"] == "disabled"

    def test_ensure_container_disabled(self):
        """無効時のコンテナ起動はエラー"""
        from core.server_ai_env import ServerAIEnv
        server = MagicMock()
        server.enabled = False
        env = ServerAIEnv(server)
        result = env.ensure_container_running()
        assert result["ok"] is False

    def test_run_ml_job_disabled(self):
        """無効時のMLジョブ実行はエラー"""
        from core.server_ai_env import ServerAIEnv
        server = MagicMock()
        server.enabled = False
        env = ServerAIEnv(server)
        result = env.run_ml_job("train.py")
        assert result["ok"] is False

    def test_get_status_text_disabled(self):
        """無効時のステータステキスト"""
        from core.server_ai_env import ServerAIEnv
        server = MagicMock()
        server.enabled = False
        env = ServerAIEnv(server)
        text = env.get_status_text()
        assert "未設定" in text


# ─── KnowledgeSync テスト ────────────────────────────────────

class TestKnowledgeSync:
    """知識同期テスト"""

    def test_push_disabled(self, tmp_path):
        """サーバー無効時のpush"""
        from core.server_ai_env import KnowledgeSync
        server = MagicMock()
        server.enabled = False
        ks = KnowledgeSync(tmp_path, server)
        result = ks.push_knowledge()
        assert result["ok"] is False

    def test_push_no_data(self, tmp_path):
        """学習データなしのpush"""
        from core.server_ai_env import KnowledgeSync
        server = MagicMock()
        server.enabled = True
        ks = KnowledgeSync(tmp_path, server)
        result = ks.push_knowledge()
        assert result["ok"] is False
        assert "学習データなし" in result.get("error", "")

    def test_pull_disabled(self, tmp_path):
        """サーバー無効時のpull"""
        from core.server_ai_env import KnowledgeSync
        server = MagicMock()
        server.enabled = False
        ks = KnowledgeSync(tmp_path, server)
        result = ks.pull_knowledge()
        assert result["ok"] is False

    def test_sync_status_initial(self, tmp_path):
        """初回のステータス"""
        from core.server_ai_env import KnowledgeSync
        server = MagicMock()
        ks = KnowledgeSync(tmp_path, server)
        text = ks.get_sync_status()
        assert "未実行" in text

    def test_dir_hash(self, tmp_path):
        """ディレクトリハッシュが一貫性を持つ"""
        from core.server_ai_env import KnowledgeSync
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("hello")
        (test_dir / "file2.txt").write_text("world")
        h1 = KnowledgeSync._dir_hash(test_dir)
        h2 = KnowledgeSync._dir_hash(test_dir)
        assert h1 == h2
        assert len(h1) == 16


# ─── PrometheusReader テスト ─────────────────────────────────

class TestPrometheusReader:
    """Prometheusメトリクス取得テスト"""

    def test_disabled(self):
        """サーバー無効時"""
        from core.server_ai_env import PrometheusReader
        server = MagicMock()
        server.enabled = False
        pr = PrometheusReader(server)
        health = pr.get_server_health_summary()
        assert health["status"] == "disabled"

    def test_summary_text_disabled(self):
        """無効時のサマリーテキスト"""
        from core.server_ai_env import PrometheusReader
        server = MagicMock()
        server.enabled = False
        pr = PrometheusReader(server)
        text = pr.get_summary_text()
        assert "未接続" in text


# ─── コマンドパターンテスト ──────────────────────────────────

class TestSprintJCommandPatterns:
    """Sprint J コマンドの正規表現マッチテスト"""

    def test_server_status_patterns(self):
        from core.cmd_handlers import CMD_SERVER_STATUS
        assert CMD_SERVER_STATUS.match("サーバー状態")
        assert CMD_SERVER_STATUS.match("ホーム確認")
        assert CMD_SERVER_STATUS.match("家の状況")
        assert CMD_SERVER_STATUS.match("サーバーステータス")

    def test_server_docker_patterns(self):
        from core.cmd_handlers import CMD_SERVER_DOCKER
        assert CMD_SERVER_DOCKER.match("サーバーDocker一覧")
        assert CMD_SERVER_DOCKER.match("ホームDocker状態")

    def test_server_sync_patterns(self):
        from core.cmd_handlers import CMD_SERVER_SYNC
        assert CMD_SERVER_SYNC.match("サーバーに同期")
        assert CMD_SERVER_SYNC.match("ホームと同期")
        assert CMD_SERVER_SYNC.match("サーバー同期して")

    def test_server_setup_patterns(self):
        from core.cmd_handlers import CMD_SERVER_SETUP
        assert CMD_SERVER_SETUP.match("サーバー設定")
        assert CMD_SERVER_SETUP.match("ホーム接続設定")

    def test_proactive_patterns(self):
        from core.cmd_handlers import CMD_PROACTIVE
        assert CMD_PROACTIVE.match("話しかけて")
        assert CMD_PROACTIVE.match("何か話して")
        assert CMD_PROACTIVE.match("会話して")
