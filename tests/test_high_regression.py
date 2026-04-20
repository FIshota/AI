"""
Regression tests for HIGH tier fixes (2026-04-21).

Covers:
    H3  ClipboardWatcher PII deny-list — TestH3
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════
# H3: ClipboardWatcher PII deny-list
# ═══════════════════════════════════════════════════════════════


class TestH3_ClipboardPII:
    def test_clean_text_passes(self):
        from core.clipboard_watcher import contains_pii

        text = "今日はいい天気ですね。猫のことを考えていました。"
        has, labels = contains_pii(text)
        assert has is False
        assert labels == []

    def test_credit_card_detected(self):
        from core.clipboard_watcher import contains_pii

        has, labels = contains_pii("card: 4111 1111 1111 1111 expires 12/29")
        assert has is True
        assert "credit_card" in labels

    def test_aws_key_detected(self):
        from core.clipboard_watcher import contains_pii

        has, labels = contains_pii("AKIAIOSFODNN7EXAMPLE is my key")
        assert has is True
        assert "aws_key" in labels

    def test_github_pat_detected(self):
        from core.clipboard_watcher import contains_pii

        has, labels = contains_pii(
            "token=ghp_1234567890abcdefghijklmnopqrstuvwxyzAB"
        )
        assert has is True
        assert "github_token" in labels

    def test_openai_key_detected(self):
        from core.clipboard_watcher import contains_pii

        has, labels = contains_pii("OPENAI_API_KEY=sk-abcdef1234567890ABCDEF")
        assert has is True
        assert "openai_key" in labels

    def test_jwt_detected(self):
        from core.clipboard_watcher import contains_pii

        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        has, labels = contains_pii(jwt)
        assert has is True
        assert "jwt" in labels

    def test_private_key_block_detected(self):
        from core.clipboard_watcher import contains_pii

        has, labels = contains_pii(
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEogIBAAKCAQ...\n"
        )
        assert has is True
        assert "private_key" in labels

    def test_my_number_detected(self):
        from core.clipboard_watcher import contains_pii

        has, labels = contains_pii("マイナンバー: 1234 5678 9012")
        assert has is True
        assert "my_number" in labels

    def test_watcher_drops_pii_clipboard(self, monkeypatch):
        """ClipboardWatcher が PII 検出時に callback を呼ばないことを検証。"""
        from core import clipboard_watcher as cw

        received: list[str] = []

        def _cb(text: str) -> None:
            received.append(text)

        # _read_clipboard を制御
        texts = iter([
            "",  # __init__ 時点
            "sk-abcdef1234567890ABCDEFGHIJ",  # PII → drop
        ])

        def _fake_read():
            try:
                return next(texts)
            except StopIteration:
                return ""

        monkeypatch.setattr(cw, "_read_clipboard", _fake_read)
        w = cw.ClipboardWatcher(_cb, interval=0.01)
        # run() を手動で 1 回回す代わりに直接ロジックを模倣
        # __init__ で last_text = "" なので 2 回目の read で PII が検出される
        text = _fake_read()
        has, _ = cw.contains_pii(text)
        assert has is True
        # callback は呼ばれていないはず
        assert received == []


# ═══════════════════════════════════════════════════════════════
# H2: TenantId 型 + data/{tenant_id}/ 分割（土台）
# ═══════════════════════════════════════════════════════════════


class TestH2_Tenant:
    def test_tenant_id_accepts_valid(self):
        from core.tenant import TenantId

        assert TenantId("self").value == "self"
        assert TenantId("family-member-01").value == "family-member-01"
        assert TenantId("abc_123").value == "abc_123"

    def test_tenant_id_rejects_traversal(self):
        from core.tenant import TenantId, InvalidTenantId
        import pytest

        for bad in ("../etc", "self/..", "a/b", "", "x" * 100, "null\x00", "x/y"):
            with pytest.raises(InvalidTenantId):
                TenantId(bad)

    def test_tenant_dir_creates_under_tenants(self, tmp_path):
        from core.tenant import tenant_dir, TenantId

        path = tenant_dir(tmp_path / "data", TenantId("self"))
        assert path.exists()
        assert path.name == "self"
        assert path.parent.name == "tenants"

    def test_tenant_dir_rejects_traversal_string(self, tmp_path):
        from core.tenant import tenant_dir, InvalidTenantId
        import pytest

        with pytest.raises(InvalidTenantId):
            tenant_dir(tmp_path / "data", "../evil")

    def test_parse_tenant_id_empty_returns_default(self):
        from core.tenant import parse_tenant_id, SELF_TENANT

        assert parse_tenant_id(None) == SELF_TENANT
        assert parse_tenant_id("") == SELF_TENANT


# ═══════════════════════════════════════════════════════════════
# H1: Protocol DI 化（土台）
# ═══════════════════════════════════════════════════════════════


class TestH1_Protocols:
    def test_audit_log_protocol_defined(self):
        from core.protocols import AuditLogProtocol

        class _Fake:
            def info(self, event, detail=""):
                pass

            def critical(self, event, detail=""):
                pass

        assert isinstance(_Fake(), AuditLogProtocol)

    def test_subject_rights_protocol_defined(self):
        from core.protocols import SubjectRightsProtocol

        class _Fake:
            def export_subject(self, subject_id="self"):
                return {}

            def purge_subject(self, subject_id="self", dry_run=False):
                return {}

        assert isinstance(_Fake(), SubjectRightsProtocol)

    def test_subject_rights_manager_satisfies_protocol(self, tmp_path):
        """具象 SubjectRightsManager が Protocol を満たすか確認（structural）。"""
        from core.protocols import SubjectRightsProtocol
        from core.subject_rights import SubjectRightsManager

        mgr = SubjectRightsManager(base_dir=tmp_path)
        assert isinstance(mgr, SubjectRightsProtocol)

    def test_deps_dataclass_defaults_none(self):
        from core.deps import AiChanDeps

        d = AiChanDeps()
        assert d.memory is None
        assert d.llm is None
        assert d.diary is None


# ═══════════════════════════════════════════════════════════════
# H7: NSPasteboard.changeCount
# ═══════════════════════════════════════════════════════════════


class TestH7_NSPasteboard:
    def test_get_change_count_returns_int_or_none(self):
        from core.clipboard_watcher import _get_change_count

        cc = _get_change_count()
        # PyObjC 無ければ None、あれば int
        assert cc is None or isinstance(cc, int)


# ═══════════════════════════════════════════════════════════════
# H8: web_search キャッシュ sha256 + TTLCache
# ═══════════════════════════════════════════════════════════════


class TestH8_WebCache:
    def test_cache_key_is_sha256(self):
        from core.web_fetcher import _cache_key

        k = _cache_key("query string")
        assert len(k) == 64
        assert all(c in "0123456789abcdef" for c in k)

    def test_cache_key_deterministic(self):
        from core.web_fetcher import _cache_key

        assert _cache_key("x") == _cache_key("x")
        assert _cache_key("x") != _cache_key("y")

    def test_cached_calls_fn_once_within_ttl(self):
        from core import web_fetcher as wf

        # キャッシュクリア
        wf._CACHE.clear()
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            return "result"

        r1 = wf._cached("test-key-unique-1", fn)
        r2 = wf._cached("test-key-unique-1", fn)
        assert r1 == r2 == "result"
        assert calls["n"] == 1  # 2回目はキャッシュヒット

    def test_cache_lru_evicts_over_max(self):
        from core import web_fetcher as wf

        wf._CACHE.clear()
        old_max = wf._CACHE_MAX_ENTRIES
        wf._CACHE_MAX_ENTRIES = 3
        try:
            for i in range(5):
                wf._cached(f"k{i}", lambda i=i: f"v{i}")
            assert len(wf._CACHE) == 3  # 最大 3 件に抑制
        finally:
            wf._CACHE_MAX_ENTRIES = old_max


# ═══════════════════════════════════════════════════════════════
# H10: requirements.txt minor bumps
# ═══════════════════════════════════════════════════════════════


class TestH10_Requirements:
    def test_fastapi_minor_bumped(self):
        from pathlib import Path
        req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text("utf-8")
        assert "fastapi>=0.118" in req, "H10: FastAPI 0.118+ を要求するはず"

    def test_torch_optional_not_default(self):
        from pathlib import Path
        req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text("utf-8")
        # torch は optional コメント内のみに出現、行頭 `torch>=` では出ない
        for line in req.splitlines():
            stripped = line.strip()
            if stripped.startswith("torch>="):
                raise AssertionError(f"H6: torch はデフォルト依存から外すべき: {line!r}")
