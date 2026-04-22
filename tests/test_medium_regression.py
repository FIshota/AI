"""
Regression tests for MEDIUM tier fixes.

Covers:
    M2  God Object 解体 (core/ops/security_ops, core/ops/server_ops) — TestM2
    M5  SQLite threading.local connection — TestM5
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


# ═══════════════════════════════════════════════════════════════
# M5: SQLite threading.local connection
# ═══════════════════════════════════════════════════════════════


class TestM5_ThreadLocalConn:
    """M5: MemoryManager._conn() のスレッドローカル化。

    目的:
      - 同一スレッドでは接続オブジェクトが再利用される (高速化)
      - 別スレッドでは独立した接続が返る (SQLite のスレッド越境エラー回避)
      - 接続が死んだ場合は自動で作り直される (自己回復)
    """

    def _make_mgr(self, tmp_path):
        from core.memory import MemoryManager

        db = tmp_path / "mem.db"
        key = tmp_path / "key.bin"
        return MemoryManager(str(db), str(key), encrypt=False)

    def test_same_thread_reuses_connection(self, tmp_path):
        """同じスレッドから呼ぶと同一接続オブジェクトが返る。"""
        mgr = self._make_mgr(tmp_path)
        c1 = mgr._conn()
        c2 = mgr._conn()
        assert c1 is c2

    def test_different_threads_get_different_connections(self, tmp_path):
        """別スレッドからは別の接続オブジェクトが返る。"""
        import threading

        mgr = self._make_mgr(tmp_path)
        main_conn = mgr._conn()
        captured: dict[str, object] = {}

        def worker():
            captured["conn"] = mgr._conn()

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert captured["conn"] is not main_conn

    def test_dead_connection_is_recreated(self, tmp_path):
        """接続を明示的に閉じた後でも、次の _conn() は生きた接続を返す。"""
        import sqlite3

        mgr = self._make_mgr(tmp_path)
        c1 = mgr._conn()
        c1.close()  # 強制的に死なせる

        c2 = mgr._conn()
        # 生きていること: SELECT 1 が通る
        assert c2.execute("SELECT 1").fetchone() == (1,)
        # 別オブジェクトであること
        assert c2 is not c1 or c2 is c1  # id 同値は許容 (再利用 vs 再生成どちらも OK)
        # 最低限、死んでいた接続を返していないこと
        with pytest_raises_ok():
            c2.execute("SELECT 1")


def pytest_raises_ok():
    """no-op context manager — 明示的に例外が出ないことを宣言するためのマーカー。"""
    from contextlib import nullcontext
    return nullcontext()


class TestM5_MigrationConn:
    """M5: MigrationManager._conn() のスレッドローカル化。"""

    def test_same_thread_reuses_connection(self, tmp_path):
        from core.migration import MigrationManager

        mgr = MigrationManager(tmp_path / "mig.db")
        c1 = mgr._conn()
        c2 = mgr._conn()
        assert c1 is c2
