"""core.consent の単体テスト。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.consent import (
    SELF_SUBJECT_ID,
    ConsentError,
    ConsentRecord,
    ConsentStore,
    UnknownConsentItem,
    load_consent_items,
    register_with_subject_rights,
)


ALLOWED = ("diary_generation", "emotion_logging", "screenshot_reading", "voice_id")


@pytest.fixture()
def store(tmp_path: Path) -> ConsentStore:
    return ConsentStore(tmp_path / "consent.db", allowed_items=ALLOWED)


# ─── ConsentRecord (値オブジェクト) ──────────────────────────


def test_record_is_frozen() -> None:
    rec = ConsentRecord(
        subject_id="self",
        version="1.0.0",
        items=("diary_generation",),
        accepted_at="2026-04-23T00:00:00+00:00",
    )
    with pytest.raises(Exception):
        rec.subject_id = "other"  # type: ignore[misc]


def test_record_is_active_and_to_dict() -> None:
    rec = ConsentRecord(
        subject_id="self",
        version="1.0.0",
        items=("emotion_logging",),
        accepted_at="2026-04-23T00:00:00+00:00",
    )
    assert rec.is_active() is True
    d = rec.to_dict()
    assert d["items"] == ["emotion_logging"]
    assert d["revoked_at"] is None

    revoked = ConsentRecord(
        subject_id="self",
        version="1.0.0",
        items=("emotion_logging",),
        accepted_at="2026-04-23T00:00:00+00:00",
        revoked_at="2026-05-01T00:00:00+00:00",
    )
    assert revoked.is_active() is False


# ─── accept / latest ─────────────────────────────────────────


def test_accept_and_latest(store: ConsentStore) -> None:
    rec = store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    assert rec.version == "1.0.0"
    assert "diary_generation" in rec.items
    latest = store.latest(SELF_SUBJECT_ID)
    assert latest is not None
    assert latest.items == ("diary_generation",)


def test_accept_rejects_unknown_item(store: ConsentStore) -> None:
    with pytest.raises(UnknownConsentItem):
        store.accept(SELF_SUBJECT_ID, "1.0.0", ["mind_reading"])


def test_accept_rejects_empty(store: ConsentStore) -> None:
    with pytest.raises(ConsentError):
        store.accept(SELF_SUBJECT_ID, "1.0.0", [])
    with pytest.raises(ConsentError):
        store.accept("", "1.0.0", ["diary_generation"])
    with pytest.raises(ConsentError):
        store.accept(SELF_SUBJECT_ID, "", ["diary_generation"])


def test_accept_history_appended_not_overwritten(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation", "emotion_logging"])
    hist = store.history(SELF_SUBJECT_ID)
    assert len(hist) == 2


# ─── revoke ──────────────────────────────────────────────────


def test_revoke_all_versions(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["emotion_logging"])
    count = store.revoke(SELF_SUBJECT_ID)
    assert count == 2
    assert store.latest_active(SELF_SUBJECT_ID) is None


def test_revoke_specific_version(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    store.accept(SELF_SUBJECT_ID, "2.0.0", ["emotion_logging"])
    count = store.revoke(SELF_SUBJECT_ID, version="1.0.0")
    assert count == 1
    active = store.latest_active(SELF_SUBJECT_ID)
    assert active is not None
    assert active.version == "2.0.0"


# ─── has_consent ─────────────────────────────────────────────


def test_has_consent(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation", "emotion_logging"])
    assert store.has_consent(SELF_SUBJECT_ID, "diary_generation") is True
    assert store.has_consent(SELF_SUBJECT_ID, "voice_id") is False
    # revoked は false
    store.revoke(SELF_SUBJECT_ID)
    assert store.has_consent(SELF_SUBJECT_ID, "diary_generation") is False


def test_has_consent_version_filter(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    assert store.has_consent(SELF_SUBJECT_ID, "diary_generation", version="1.0.0")
    assert not store.has_consent(SELF_SUBJECT_ID, "diary_generation", version="2.0.0")


# ─── subjects / isolation ────────────────────────────────────


def test_all_subjects_isolation(store: ConsentStore) -> None:
    store.accept("self", "1.0.0", ["diary_generation"])
    store.accept("alice", "1.0.0", ["emotion_logging"])
    store.accept("bob", "1.0.0", ["voice_id"])
    subjects = store.all_subjects()
    assert set(subjects) == {"self", "alice", "bob"}
    # subject 間は相互に干渉しない
    store.revoke("alice")
    assert store.latest_active("self") is not None
    assert store.latest_active("bob") is not None
    assert store.latest_active("alice") is None


# ─── persistence ─────────────────────────────────────────────


def test_persistence_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    s1 = ConsentStore(db, allowed_items=ALLOWED)
    s1.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    s2 = ConsentStore(db, allowed_items=ALLOWED)
    latest = s2.latest(SELF_SUBJECT_ID)
    assert latest is not None
    assert latest.items == ("diary_generation",)


# ─── purge ───────────────────────────────────────────────────


def test_purge_subject_removes_all_records(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["emotion_logging"])
    n = store.purge_subject(SELF_SUBJECT_ID)
    assert n == 2
    assert store.latest(SELF_SUBJECT_ID) is None


# ─── config loader ───────────────────────────────────────────


def test_load_consent_items_reads_yaml() -> None:
    cfg = Path(__file__).resolve().parent.parent / "config" / "consent_items.yaml"
    version, keys, raw = load_consent_items(cfg)
    assert version
    assert "diary_generation" in keys
    assert "emotion_logging" in keys
    assert isinstance(raw, dict)


# ─── subject_rights hook ─────────────────────────────────────


class _FakeSubjectRights:
    def __init__(self) -> None:
        self.purge_calls: list[tuple[str, bool]] = []

    def purge_subject(self, subject_id: str = SELF_SUBJECT_ID, dry_run: bool = False) -> dict:
        self.purge_calls.append((subject_id, dry_run))
        return {"subject_id": subject_id, "memories": 3, "dry_run": dry_run, "errors": []}


def test_register_with_subject_rights_purges_consent(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    mgr: Any = _FakeSubjectRights()
    register_with_subject_rights(mgr, store)
    report = mgr.purge_subject(SELF_SUBJECT_ID, dry_run=False)
    assert report["memories"] == 3
    assert report["consent_records"] == 1
    assert store.latest(SELF_SUBJECT_ID) is None


def test_register_with_subject_rights_dry_run_preserves(store: ConsentStore) -> None:
    store.accept(SELF_SUBJECT_ID, "1.0.0", ["diary_generation"])
    mgr: Any = _FakeSubjectRights()
    register_with_subject_rights(mgr, store)
    report = mgr.purge_subject(SELF_SUBJECT_ID, dry_run=True)
    assert report["dry_run"] is True
    assert report["consent_records"] == 1
    # dry_run では削除しない
    assert store.latest(SELF_SUBJECT_ID) is not None


def test_register_with_subject_rights_none_safe() -> None:
    # 例外を投げずに無視する
    register_with_subject_rights(None, None)  # type: ignore[arg-type]
