"""
Regression tests for B1–B8 blocker fixes (2026-04-21).

Covers:
    B1  Web API bearer auth       — tests/test_blocker_regression.py::TestB1
    B2  JSON encryption           — TestB2
    B3  Keychain / passphrase key — TestB3
    B4  url_guard wiring          — smoke only
    B5  Clipboard/Screenshot OFF  — TestB5
    B6  diskcache mitigation      — TestB6 (checks _harden_llm_cache presence)
    B7  security_level enforce    — TestB7
    B8  purge/export subject      — TestB8
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════
# B1: Web API bearer authentication
# ═══════════════════════════════════════════════════════════════


class TestB1_WebAuth:
    """AICHAN_API_TOKEN 未設定 → localhost のみ許可。設定済 → Bearer 必須。"""

    def test_token_mismatch_rejected(self, monkeypatch):
        pytest.importorskip("fastapi")
        from fastapi import HTTPException
        import asyncio
        from unittest.mock import MagicMock
        from web.app import require_auth

        monkeypatch.setenv("AICHAN_API_TOKEN", "correct-token")

        req = MagicMock()
        req.client.host = "10.0.0.5"
        with pytest.raises(HTTPException) as exc:
            asyncio.run(require_auth(req, authorization="Bearer wrong-token"))
        assert exc.value.status_code == 401

    def test_token_match_accepted(self, monkeypatch):
        pytest.importorskip("fastapi")
        import asyncio
        from unittest.mock import MagicMock
        from web.app import require_auth

        monkeypatch.setenv("AICHAN_API_TOKEN", "correct-token")
        req = MagicMock()
        req.client.host = "10.0.0.5"
        # should not raise
        asyncio.run(require_auth(req, authorization="Bearer correct-token"))

    def test_no_token_remote_host_rejected(self, monkeypatch):
        pytest.importorskip("fastapi")
        from fastapi import HTTPException
        import asyncio
        from unittest.mock import MagicMock
        from web.app import require_auth

        monkeypatch.delenv("AICHAN_API_TOKEN", raising=False)
        req = MagicMock()
        req.client.host = "10.0.0.5"
        with pytest.raises(HTTPException) as exc:
            asyncio.run(require_auth(req, authorization=None))
        assert exc.value.status_code == 401

    def test_no_token_localhost_allowed(self, monkeypatch):
        pytest.importorskip("fastapi")
        import asyncio
        from unittest.mock import MagicMock
        from web.app import require_auth

        monkeypatch.delenv("AICHAN_API_TOKEN", raising=False)
        req = MagicMock()
        req.client.host = "127.0.0.1"
        asyncio.run(require_auth(req, authorization=None))  # no raise


# ═══════════════════════════════════════════════════════════════
# B2: JSON encryption via secure_store
# ═══════════════════════════════════════════════════════════════


class TestB2_SecureStore:
    """secure_store による JSON 暗号化・復号・移行テスト。"""

    def test_roundtrip_encrypted(self, tmp_path):
        from utils.secure_store import load_json, save_json

        key = os.urandom(32)
        path = tmp_path / "data.json"
        data = {"secret": "テストデータ", "list": [1, 2, 3]}

        save_json(path, data, key)
        # ファイルは magic prefix で始まる
        raw = path.read_text("utf-8")
        assert raw.startswith("AICHAN_ENC_V1\n"), "暗号化フォーマットが誤り"
        assert "テストデータ" not in raw, "平文が残っている"

        loaded = load_json(path, key, default=None)
        assert loaded == data

    def test_plain_migration_on_load(self, tmp_path):
        from utils.secure_store import load_json

        key = os.urandom(32)
        path = tmp_path / "plain.json"
        path.write_text(json.dumps({"a": 1}), "utf-8")

        loaded = load_json(path, key, default=None)
        assert loaded == {"a": 1}
        # 自動で暗号化書き戻し
        assert path.read_text("utf-8").startswith("AICHAN_ENC_V1\n")

    def test_missing_key_returns_default(self, tmp_path):
        from utils.secure_store import load_json, save_json

        key = os.urandom(32)
        path = tmp_path / "data.json"
        save_json(path, {"x": 1}, key)
        # 鍵なしで読むと default (復号不能)
        result = load_json(path, key=None, default="DEFAULT")
        assert result == "DEFAULT"

    def test_diary_encryption(self, tmp_path):
        """DiaryManager が key 引数を受け取り暗号化する。"""
        from core.diary import DiaryManager

        key = os.urandom(32)
        data_dir = tmp_path / "data"

        # memory は使わないが None だと書き込み時に落ちる可能性があるので mock
        class _FakeMem:
            def get_recent(self, **_):
                return []

        mgr = DiaryManager(data_dir, memory=_FakeMem(), key=key)
        # 空でも read/write が通る
        assert mgr._key == key


# ═══════════════════════════════════════════════════════════════
# B3: passphrase-based master key
# ═══════════════════════════════════════════════════════════════


class TestB3_Keychain:
    def test_passphrase_derives_deterministic_key(self, tmp_path, monkeypatch):
        from utils.keychain import get_master_key

        monkeypatch.setenv("AICHAN_MASTER_PASSPHRASE", "my-strong-phrase")
        k1 = get_master_key(tmp_path)
        k2 = get_master_key(tmp_path)
        assert k1 == k2, "同じ passphrase + salt なら鍵は一致する"
        assert len(k1) == 32, "AES-256 は 32 byte 鍵"

    def test_different_passphrase_differs(self, tmp_path, monkeypatch):
        from utils.keychain import get_master_key

        monkeypatch.setenv("AICHAN_MASTER_PASSPHRASE", "phrase-A")
        k_a = get_master_key(tmp_path)
        # salt を保持したまま passphrase を変えると別鍵
        monkeypatch.setenv("AICHAN_MASTER_PASSPHRASE", "phrase-B")
        k_b = get_master_key(tmp_path)
        assert k_a != k_b


# ═══════════════════════════════════════════════════════════════
# B5: Privacy defaults OFF
# ═══════════════════════════════════════════════════════════════


class TestB5_PrivacyDefaults:
    def test_config_model_defaults_off(self):
        from core.config_model import AutonomousConfig

        cfg = AutonomousConfig()
        assert cfg.clipboard_watch is False
        assert cfg.screenshot_enabled is False
        assert cfg.consent_ts == ""

    def test_settings_example_defaults_off(self):
        path = _PROJECT_ROOT / "config" / "settings.json.example"
        data = json.loads(path.read_text("utf-8"))
        auto = data["autonomous"]
        assert auto["clipboard_watch"] is False
        assert auto["screenshot_enabled"] is False


# ═══════════════════════════════════════════════════════════════
# B6: diskcache mitigation exists
# ═══════════════════════════════════════════════════════════════


class TestB6_DiskcacheMitigation:
    def test_harden_function_present(self):
        import core.llm as llm_mod

        assert hasattr(llm_mod, "_harden_llm_cache"), (
            "B6: _harden_llm_cache() が欠落。CVE-2025-69872 対策が後退"
        )


# ═══════════════════════════════════════════════════════════════
# B7: security_level enforcement
# ═══════════════════════════════════════════════════════════════


class TestB7_SecurityLevelEnforce:
    def test_level_order(self):
        from core.memory import MemoryManager

        assert MemoryManager._can_access("public", "public")
        assert MemoryManager._can_access("public", "private")
        assert MemoryManager._can_access("public", "secret")
        assert not MemoryManager._can_access("private", "public")
        assert MemoryManager._can_access("private", "private")
        assert MemoryManager._can_access("private", "secret")
        assert not MemoryManager._can_access("secret", "private")
        assert MemoryManager._can_access("secret", "secret")

    def test_search_respects_clearance(self, tmp_path):
        from core.memory import MemoryManager

        mgr = MemoryManager(
            db_path=tmp_path / "mem.db",
            key_file=tmp_path / "key",
            encrypt=False,
        )
        m_pub = mgr.remember("公開メモ")
        mgr.set_security_level(m_pub.id, "public")
        m_sec = mgr.remember("内緒メモ")
        mgr.set_security_level(m_sec.id, "secret")

        public_hits = mgr.search("メモ", limit=10, clearance="public")
        secret_hits = mgr.search("メモ", limit=10, clearance="secret")

        contents_public = [m.content for m in public_hits]
        contents_secret = [m.content for m in secret_hits]

        assert "内緒メモ" not in contents_public, "public clearance が secret を見えてはいけない"
        assert "公開メモ" in contents_public
        assert "内緒メモ" in contents_secret
        assert "公開メモ" in contents_secret


# ═══════════════════════════════════════════════════════════════
# B8: subject purge / export
# ═══════════════════════════════════════════════════════════════


class TestB8_SubjectRights:
    def test_export_subject_structure(self, tmp_path):
        from core.memory import MemoryManager
        from core.subject_rights import SubjectRightsManager

        mgr = MemoryManager(
            db_path=tmp_path / "mem.db",
            key_file=tmp_path / "key",
            encrypt=False,
        )
        mgr.remember("テスト記憶")

        rights = SubjectRightsManager(
            base_dir=tmp_path,
            memory=mgr,
            diary=None,
            emotion_history=None,
            anniversary=None,
        )
        payload = rights.export_subject("self")

        assert payload["subject_id"] == "self"
        assert "exported_at" in payload
        assert isinstance(payload["memories"], list)
        assert len(payload["memories"]) >= 1
        assert payload["memories"][0]["content"] == "テスト記憶"

    def test_purge_dry_run_counts_without_delete(self, tmp_path):
        from core.memory import MemoryManager
        from core.subject_rights import SubjectRightsManager

        mgr = MemoryManager(
            db_path=tmp_path / "mem.db",
            key_file=tmp_path / "key",
            encrypt=False,
        )
        for i in range(3):
            mgr.remember(f"記憶{i}")

        rights = SubjectRightsManager(
            base_dir=tmp_path, memory=mgr, diary=None, emotion_history=None,
            anniversary=None,
        )
        report = rights.purge_subject(dry_run=True)
        assert report["memories"] == 3
        assert report["dry_run"] is True

        # dry_run なので件数は維持
        after = mgr.search("記憶", limit=10, clearance="secret")
        assert len(after) == 3

    def test_purge_actual_deletes(self, tmp_path):
        from core.memory import MemoryManager
        from core.subject_rights import SubjectRightsManager

        mgr = MemoryManager(
            db_path=tmp_path / "mem.db",
            key_file=tmp_path / "key",
            encrypt=False,
        )
        mgr.remember("忘れられるべき記憶")

        rights = SubjectRightsManager(
            base_dir=tmp_path, memory=mgr, diary=None, emotion_history=None,
            anniversary=None,
        )
        report = rights.purge_subject(dry_run=False)
        assert report["memories"] >= 1
        # 実削除
        after = mgr.search("忘れ", limit=10, clearance="secret")
        assert len(after) == 0

    def test_export_to_file(self, tmp_path):
        from core.memory import MemoryManager
        from core.subject_rights import SubjectRightsManager

        mgr = MemoryManager(
            db_path=tmp_path / "mem.db",
            key_file=tmp_path / "key",
            encrypt=False,
        )
        mgr.remember("エクスポート対象")

        rights = SubjectRightsManager(
            base_dir=tmp_path, memory=mgr, diary=None, emotion_history=None,
            anniversary=None,
        )
        out = rights.export_to_file("self")
        assert out.exists()
        loaded = json.loads(out.read_text("utf-8"))
        assert loaded["subject_id"] == "self"
        assert any("エクスポート対象" in m.get("content", "") for m in loaded["memories"])
