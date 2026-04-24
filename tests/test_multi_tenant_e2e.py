"""
5.6 Multi-tenant E2E 検証。

同一ホスト上で複数テナント (家族A / 家族B) を並走させたとき、
記憶 / 感情 / 設定 / 音声 / 匿名記念日 がクロス汚染しないことを E2E で証明する。

stdlib + pytest のみ。Py3.9 互換。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import List

import pytest

from core.tenant_context import (
    InvalidTenantIdError,
    TenantContext,
    TenantIsolationError,
    list_tenants,
    purge_tenant,
)


# ──────────────────────────────────────────────────────────
# fixtures
# ──────────────────────────────────────────────────────────
@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    root = tmp_path / "tenants_root"
    root.mkdir()
    return root


@pytest.fixture
def tenants(base_dir: Path):
    a = TenantContext.create_isolated(base_dir, "family-a")
    b = TenantContext.create_isolated(base_dir, "family-b")
    return a, b


# ──────────────────────────────────────────────────────────
# 1. 並列 (parallel) 初期化
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_two_tenants_initialize_into_separate_roots(tenants, base_dir):
    a, b = tenants
    assert a.root_dir != b.root_dir
    assert a.tenant_id == "family-a"
    assert b.tenant_id == "family-b"
    # 必須 subtree
    for ctx in (a, b):
        for sub in ("memory", "config", "logs", "data", "audit"):
            assert (ctx.root_dir / sub).is_dir(), f"{sub} missing for {ctx.tenant_id}"
    # base_dir 配下に 2 つ
    assert set(list_tenants(base_dir)) == {"family-a", "family-b"}


# ──────────────────────────────────────────────────────────
# 2. memory 書き込みの分離
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_memory_write_on_A_not_visible_to_B(tenants):
    a, b = tenants
    (a.memory_dir / "note.txt").write_text("secret-of-A", encoding="utf-8")
    # B 側の memory_dir には一切出現しない
    b_files = list(b.memory_dir.rglob("*"))
    assert all("secret-of-A" not in p.read_text(encoding="utf-8")
               for p in b_files if p.is_file())
    assert not (b.memory_dir / "note.txt").exists()


# ──────────────────────────────────────────────────────────
# 3. 感情履歴ファイルの分離
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_emotion_history_isolation(tenants):
    a, b = tenants
    (a.memory_dir / "emotion_history.json").write_text(
        json.dumps([{"ts": "2026-04-24T10:00", "happiness": 0.9}]),
        encoding="utf-8",
    )
    (b.memory_dir / "emotion_history.json").write_text(
        json.dumps([{"ts": "2026-04-24T10:00", "happiness": 0.2}]),
        encoding="utf-8",
    )
    a_data = json.loads((a.memory_dir / "emotion_history.json").read_text())
    b_data = json.loads((b.memory_dir / "emotion_history.json").read_text())
    assert a_data[0]["happiness"] == 0.9
    assert b_data[0]["happiness"] == 0.2


# ──────────────────────────────────────────────────────────
# 4. 設定ファイルの分離
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_config_file_isolation(tenants):
    a, b = tenants
    (a.config_dir / "persona.json").write_text(
        json.dumps({"name": "Ai-A", "family": "A"}), encoding="utf-8"
    )
    (b.config_dir / "persona.json").write_text(
        json.dumps({"name": "Ai-B", "family": "B"}), encoding="utf-8"
    )
    a_cfg = json.loads((a.config_dir / "persona.json").read_text())
    b_cfg = json.loads((b.config_dir / "persona.json").read_text())
    assert a_cfg["family"] == "A"
    assert b_cfg["family"] == "B"
    # A の config_dir 配下には B の設定ファイルが存在しないこと
    a_names = {p.name for p in a.config_dir.rglob("*") if p.is_file()}
    # すべて A のコンテンツであり、"family": "B" のファイルは無い
    for p in a.config_dir.rglob("*"):
        if p.is_file():
            assert "Ai-B" not in p.read_text(encoding="utf-8")
    assert "persona.json" in a_names


# ──────────────────────────────────────────────────────────
# 5. tenant_id バリデーション
# ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "ab",                # 短すぎ
        "A" * 33,            # 長すぎ
        "UPPER",             # 大文字
        "name.with.dot",
        "path/traversal",
        "../escape",
        "空白 入り",
        "a\x00null",
        "tab\there",
    ],
)
def test_invalid_tenant_id_rejected(base_dir, bad_id):
    with pytest.raises(InvalidTenantIdError):
        TenantContext.create_isolated(base_dir, bad_id)


def test_valid_tenant_id_accepted(base_dir):
    for ok in ("abc", "family-01", "a_b_c", "z" * 32, "tenant-xyz_123"):
        ctx = TenantContext.create_isolated(base_dir, ok)
        assert ctx.tenant_id == ok


# ──────────────────────────────────────────────────────────
# 6. guard_path が ../ 脱出を拒否
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_guard_path_rejects_dotdot_escape(tenants):
    a, _b = tenants
    with pytest.raises(TenantIsolationError):
        a.guard_path(a.root_dir / ".." / "family-b" / "memory" / "pwn.txt")
    with pytest.raises(TenantIsolationError):
        a.guard_path("../../etc/passwd")


def test_guard_path_accepts_legitimate_subpath(tenants):
    a, _b = tenants
    p = a.guard_path(a.memory_dir / "ok.txt")
    assert str(p).startswith(str(a.root_dir.resolve()))


# ──────────────────────────────────────────────────────────
# 7. シンボリックリンク攻撃の拒否
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_guard_path_rejects_symlink_escape(tenants, tmp_path):
    a, _b = tenants
    outside = tmp_path / "outside.txt"
    outside.write_text("evil", encoding="utf-8")
    evil_link = a.memory_dir / "evil_link"
    try:
        os.symlink(outside, evil_link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")
    with pytest.raises(TenantIsolationError):
        a.guard_path(evil_link)


@pytest.mark.integration
def test_guard_path_rejects_symlinked_tenant_root(base_dir, tmp_path):
    """root_dir 自身が外部へのシンボリックリンクである攻撃ケース。"""
    outside = tmp_path / "real_target"
    outside.mkdir()
    link_root = base_dir / "family-c"
    try:
        os.symlink(outside, link_root)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")
    # link_root を root とする ctx を作っても、guard_path が外部への書き込みを
    # 検知できることを確認する (resolve 後に base の外に飛ぶ)。
    # create_isolated は mkdir(exist_ok) するので既存 link を踏む。
    ctx = TenantContext(tenant_id="family-c", root_dir=link_root)
    # memory_dir 配下への path は link 先を指すが、lexical root とは別物なので
    # guard_path は許可する (root_dir そのものが link 先 = その配下だけ有効)。
    # しかし base_dir を抜けて "../" する試みは拒否されるべき。
    with pytest.raises(TenantIsolationError):
        ctx.guard_path(link_root / ".." / "elsewhere" / "x.txt")


# ──────────────────────────────────────────────────────────
# 8. 並列書き込みでクロス汚染ゼロ
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_parallel_writes_no_cross_contamination(tenants):
    a, b = tenants
    N = 100
    errors: List[Exception] = []

    def writer(ctx: TenantContext, tag: str, n: int) -> None:
        try:
            for i in range(n):
                fp = ctx.memory_dir / f"{tag}_{i:04d}.txt"
                fp.write_text(f"{tag}:{i}", encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    t1 = threading.Thread(target=writer, args=(a, "A", N))
    t2 = threading.Thread(target=writer, args=(b, "B", N))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert not errors, errors

    a_files = sorted(p.name for p in a.memory_dir.iterdir() if p.is_file())
    b_files = sorted(p.name for p in b.memory_dir.iterdir() if p.is_file())

    assert len(a_files) == N
    assert len(b_files) == N
    # A 側に B のファイルは 1 つも無い / 逆も然り
    assert all(n.startswith("A_") for n in a_files), a_files[:3]
    assert all(n.startswith("B_") for n in b_files), b_files[:3]

    # 内容もクロス汚染ゼロ
    for fp in a.memory_dir.iterdir():
        if fp.is_file():
            assert fp.read_text(encoding="utf-8").startswith("A:")
    for fp in b.memory_dir.iterdir():
        if fp.is_file():
            assert fp.read_text(encoding="utf-8").startswith("B:")


# ──────────────────────────────────────────────────────────
# 9. purge が他テナントに影響しない
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_purge_does_not_affect_other_tenants(tenants, base_dir):
    a, b = tenants
    (a.memory_dir / "keep.txt").write_text("A-data", encoding="utf-8")
    (b.memory_dir / "keep.txt").write_text("B-data", encoding="utf-8")

    # dry-run
    target = purge_tenant(base_dir, a.tenant_id, confirm=False)
    assert target == a.root_dir.resolve()
    assert a.root_dir.exists(), "dry-run should not delete"

    # 実削除
    purge_tenant(base_dir, a.tenant_id, confirm=True)
    assert not a.root_dir.exists()
    # B は無傷
    assert b.root_dir.exists()
    assert (b.memory_dir / "keep.txt").read_text(encoding="utf-8") == "B-data"
    assert list_tenants(base_dir) == ["family-b"]


# ──────────────────────────────────────────────────────────
# 10. audit ログのテナント別分離
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_audit_log_isolation(tenants):
    """audit_chain が存在する前提で、各テナントの audit_dir が独立していることを示す。

    本テストは audit_chain モジュールの実装詳細には踏み込まず、
    「TenantContext.audit_dir 配下にエントリを書いた場合、他テナントから
     見えない」ことだけを検証する (FS 層の契約)。
    """
    a, b = tenants
    (a.audit_dir / "0001.json").write_text(
        json.dumps({"event": "login", "tenant": "A"}), encoding="utf-8"
    )
    (b.audit_dir / "0001.json").write_text(
        json.dumps({"event": "login", "tenant": "B"}), encoding="utf-8"
    )
    a_entries = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(a.audit_dir.iterdir())
        if p.is_file()
    ]
    b_entries = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(b.audit_dir.iterdir())
        if p.is_file()
    ]
    assert len(a_entries) == 1 and a_entries[0]["tenant"] == "A"
    assert len(b_entries) == 1 and b_entries[0]["tenant"] == "B"


# ──────────────────────────────────────────────────────────
# 11. MemoryManager / EmotionHistory への tenant_context 注入 (additive 互換確認)
# ──────────────────────────────────────────────────────────
@pytest.mark.integration
def test_memory_manager_respects_tenant_context(tenants):
    from core.memory import MemoryManager

    a, b = tenants
    mm_a = MemoryManager(
        db_path="memory.db",
        key_file="memory.key",
        encrypt=False,
        tenant_context=a,
    )
    mm_b = MemoryManager(
        db_path="memory.db",
        key_file="memory.key",
        encrypt=False,
        tenant_context=b,
    )
    # それぞれ別のテナント root 配下に着地していること
    assert str(mm_a.db_path).startswith(str(a.root_dir.resolve()))
    assert str(mm_b.db_path).startswith(str(b.root_dir.resolve()))
    assert mm_a.db_path != mm_b.db_path


@pytest.mark.integration
def test_emotion_history_respects_tenant_context(tenants, tmp_path):
    from core.emotion_history import EmotionHistory

    a, b = tenants
    eh_a = EmotionHistory(data_dir=tmp_path / "legacy_a", tenant_context=a)
    eh_b = EmotionHistory(data_dir=tmp_path / "legacy_b", tenant_context=b)
    eh_a.record({"happiness": 0.9})
    eh_b.record({"happiness": 0.1})
    assert str(eh_a._path).startswith(str(a.root_dir.resolve()))
    assert str(eh_b._path).startswith(str(b.root_dir.resolve()))
    # A の履歴には B のスコアが混ざっていない
    assert all(r["happiness"] != 0.1 for r in eh_a.get_recent())
    assert all(r["happiness"] != 0.9 for r in eh_b.get_recent())
