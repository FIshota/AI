"""
Regression tests for MEDIUM tier fixes.

Covers:
    M2  God Object 解体 (core/ops/security_ops, core/ops/server_ops) — TestM2
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════
# M2: core/ops/security_ops.py 単体
# ═══════════════════════════════════════════════════════════════


class TestM2_SecurityOps:
    def test_run_security_check_with_no_modules(self):
        """全モジュール未初期化時でも文字列が返る。"""
        from core.ops import security_ops

        ai = SimpleNamespace()
        out = security_ops.run_security_check(ai)
        assert "セキュリティ診断" in out

    def test_run_backup_no_module(self):
        from core.ops import security_ops

        ai = SimpleNamespace()
        assert "初期化されていない" in security_ops.run_backup(ai)

    def test_run_backup_success(self):
        from core.ops import security_ops

        class _Bk:
            def create_backup(self, label):
                assert label == "manual"
                return {"size_mb": 12.3, "files": 42}

        ai = SimpleNamespace(backup=_Bk())
        out = security_ops.run_backup(ai)
        assert "バックアップ完了" in out
        assert "12.3MB" in out
        assert "42" in out

    def test_show_backup_list_empty(self):
        from core.ops import security_ops

        class _Bk:
            def list_backups(self):
                return []

        ai = SimpleNamespace(backup=_Bk())
        assert "まだバックアップはない" in security_ops.show_backup_list(ai)

    def test_show_backup_list_truncates_to_5(self):
        from core.ops import security_ops

        class _Bk:
            def list_backups(self):
                return [
                    {"filename": f"bk_{i}.zip", "size_mb": i} for i in range(10)
                ]

        ai = SimpleNamespace(backup=_Bk())
        out = security_ops.show_backup_list(ai)
        # 直近 5 件のみ含まれる
        assert "bk_5.zip" in out
        assert "bk_9.zip" in out
        assert "bk_4.zip" not in out

    def test_run_lockdown_no_killswitch(self):
        from core.ops import security_ops

        ai = SimpleNamespace()
        assert "キルスイッチ" in security_ops.run_lockdown(ai, "test")

    def test_run_unlock_wrong_confirm(self):
        from core.ops import security_ops

        class _Ks:
            def unlock(self, confirm):
                return {"unlocked": False, "reason": "合言葉が違うよ"}

        ai = SimpleNamespace(kill_switch=_Ks())
        out = security_ops.run_unlock(ai)
        assert "解除できなかった" in out


# ═══════════════════════════════════════════════════════════════
# M2: core/ops/server_ops.py 単体
# ═══════════════════════════════════════════════════════════════


class TestM2_ServerOps:
    def test_server_status_disabled(self):
        from core.ops import server_ops

        ai = SimpleNamespace()
        out = server_ops.server_status(ai)
        assert "まだ設定されていない" in out

    def test_server_status_unreachable(self):
        from core.ops import server_ops

        class _Sh:
            enabled = True

            def is_reachable(self):
                return False

        ai = SimpleNamespace(server_home=_Sh())
        out = server_ops.server_status(ai)
        assert "接続できない" in out

    def test_server_docker_empty(self):
        from core.ops import server_ops

        class _Sh:
            enabled = True

            def docker_ps(self):
                return []

        ai = SimpleNamespace(server_home=_Sh())
        out = server_ops.server_docker(ai)
        assert "ないみたい" in out

    def test_server_setup_guide_stateless(self):
        """setup_guide は ai 引数を取らない（純粋文字列）。"""
        from core.ops import server_ops

        out = server_ops.server_setup_guide()
        assert "server_home" in out
        assert "enabled: true" in out

    def test_server_sync_no_ks(self):
        from core.ops import server_ops

        ai = SimpleNamespace()
        assert "まだ設定されていない" in server_ops.server_sync(ai)

    def test_server_sync_full_cycle(self):
        from core.ops import server_ops

        class _Ks:
            def push_knowledge(self):
                return {"ok": True, "action": "pushed"}

            def pull_knowledge(self):
                return {"ok": True, "pulled": 3}

        ai = SimpleNamespace(knowledge_sync=_Ks())
        out = server_ops.server_sync(ai)
        assert "アップロード" in out
        assert "3件取得" in out


# ═══════════════════════════════════════════════════════════════
# M2: AiChan の委譲メソッドが ops モジュールを呼ぶことを確認
# ═══════════════════════════════════════════════════════════════


class TestM2_Delegation:
    def test_ai_chan_method_delegates_to_server_ops(self, monkeypatch):
        """AiChan._server_setup_guide が core.ops.server_ops に委譲されていること。"""
        from core.ops import server_ops

        called = {"n": 0}
        original = server_ops.server_setup_guide

        def _spy():
            called["n"] += 1
            return original()

        monkeypatch.setattr(server_ops, "server_setup_guide", _spy)

        # AiChan インスタンス化は重いので、メソッドバウンドの代わりに
        # unbound function を直接叩く
        from core.ai_chan import AiChan

        # dummy self で呼ぶ（self は未使用のため SimpleNamespace でも可）
        result = AiChan._server_setup_guide(SimpleNamespace())
        assert called["n"] == 1
        assert "server_home" in result
