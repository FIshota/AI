"""
consent — ai-chan 利用同意（consent string）管理。

10 年単位で「誰が・いつ・どの機能に同意したか」を証跡として保持する。
外部送信は一切行わず、ローカル SQLite に永続化する。

設計方針:
    - ConsentRecord は ``@dataclass(frozen=True)`` の不変値オブジェクト
    - ConsentStore は SQLite 永続化レイヤ（スキーマは v1）
    - 利用可能なら ``utils.crypto`` 由来の鍵で DB ファイルを暗号化するが、
      鍵が無い場合は平文 SQLite に fallback（データポータビリティ優先）
    - ``core.subject_rights.SubjectRightsManager`` と疎結合に連携するための
      ``purge_subject()`` フック (register_with_subject_rights) を提供

SQLite スキーマ (consent_records):
    id            INTEGER PRIMARY KEY AUTOINCREMENT
    subject_id    TEXT NOT NULL
    version       TEXT NOT NULL
    items         TEXT NOT NULL     -- JSON array
    accepted_at   TEXT NOT NULL     -- ISO 8601 UTC
    revoked_at    TEXT              -- ISO 8601 UTC / NULL

インデックス:
    idx_consent_subject (subject_id, accepted_at DESC)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


SELF_SUBJECT_ID = "self"
SCHEMA_VERSION = 1


def _utcnow_iso() -> str:
    """ISO 8601 UTC の現在時刻（秒精度）を返す。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ConsentRecord:
    """1 件の同意証跡。

    Attributes:
        subject_id: 同意主体の識別子（'self' または family member UUID）
        version: ``consent_items.yaml`` のバージョン
        items: 同意した項目名のタプル（順序非依存だが記録用に保持）
        accepted_at: 同意した UTC 時刻（ISO 8601）
        revoked_at: 撤回した UTC 時刻（ISO 8601）。撤回していなければ None
    """

    subject_id: str
    version: str
    items: Tuple[str, ...]
    accepted_at: str
    revoked_at: Optional[str] = None
    id: Optional[int] = field(default=None, compare=False)

    def is_active(self) -> bool:
        """撤回されていなければ True。"""
        return self.revoked_at is None

    def to_dict(self) -> dict:
        """JSON シリアライズ可能な dict に変換する。"""
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "version": self.version,
            "items": list(self.items),
            "accepted_at": self.accepted_at,
            "revoked_at": self.revoked_at,
        }


class ConsentError(Exception):
    """Consent 関連の基底例外。"""


class UnknownConsentItem(ConsentError):
    """consent_items.yaml に定義されていない項目が指定された。"""


class ConsentStore:
    """SQLite ベースの同意証跡ストア。"""

    def __init__(
        self,
        db_path: Path,
        allowed_items: Optional[Iterable[str]] = None,
    ) -> None:
        """Args:
            db_path: SQLite ファイルパス
            allowed_items: 受理する項目名の allowlist。None なら検証しない。
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._allowed_items = (
            frozenset(allowed_items) if allowed_items is not None else None
        )
        self._lock = threading.RLock()
        self._init_schema()

    # ─── schema ──────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consent_records (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id   TEXT NOT NULL,
                    version      TEXT NOT NULL,
                    items        TEXT NOT NULL,
                    accepted_at  TEXT NOT NULL,
                    revoked_at   TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_consent_subject "
                "ON consent_records (subject_id, accepted_at DESC)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS consent_schema ("
                "  key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO consent_schema(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    # ─── validation ──────────────────────────────────────────

    def _validate_items(self, items: Iterable[str]) -> Tuple[str, ...]:
        normalized = tuple(sorted({str(i) for i in items}))
        if not normalized:
            raise ConsentError("items must be non-empty")
        if self._allowed_items is not None:
            unknown = [i for i in normalized if i not in self._allowed_items]
            if unknown:
                raise UnknownConsentItem(
                    f"unknown consent items: {unknown!r}"
                )
        return normalized

    # ─── write ───────────────────────────────────────────────

    def accept(
        self,
        subject_id: str,
        version: str,
        items: Iterable[str],
        accepted_at: Optional[str] = None,
    ) -> ConsentRecord:
        """新しい同意を記録する。

        同一 subject の過去レコードがあっても上書きせず、履歴として追記する。
        """
        if not subject_id:
            raise ConsentError("subject_id must be non-empty")
        if not version:
            raise ConsentError("version must be non-empty")
        validated = self._validate_items(items)
        ts = accepted_at or _utcnow_iso()

        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO consent_records "
                "(subject_id, version, items, accepted_at, revoked_at) "
                "VALUES (?, ?, ?, ?, NULL)",
                (subject_id, version, json.dumps(list(validated)), ts),
            )
            row_id = cur.lastrowid
        logger.info(
            "consent accepted: subject=%s version=%s items=%s",
            subject_id,
            version,
            validated,
        )
        return ConsentRecord(
            subject_id=subject_id,
            version=version,
            items=validated,
            accepted_at=ts,
            revoked_at=None,
            id=row_id,
        )

    def revoke(
        self,
        subject_id: str,
        version: Optional[str] = None,
        revoked_at: Optional[str] = None,
    ) -> int:
        """同意を撤回する。

        Args:
            subject_id: 対象
            version: 指定があればそのバージョンのみ、None なら当該 subject の
                全アクティブレコードを撤回
            revoked_at: ISO 8601。None なら現在時刻

        Returns:
            撤回したレコード数
        """
        ts = revoked_at or _utcnow_iso()
        with self._lock, self._conn() as conn:
            if version is None:
                cur = conn.execute(
                    "UPDATE consent_records SET revoked_at=? "
                    "WHERE subject_id=? AND revoked_at IS NULL",
                    (ts, subject_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE consent_records SET revoked_at=? "
                    "WHERE subject_id=? AND version=? AND revoked_at IS NULL",
                    (ts, subject_id, version),
                )
            count = cur.rowcount
        logger.info(
            "consent revoked: subject=%s version=%s count=%d",
            subject_id,
            version,
            count,
        )
        return int(count)

    # ─── read ────────────────────────────────────────────────

    def latest(self, subject_id: str) -> Optional[ConsentRecord]:
        """最新の同意レコードを返す（撤回済みも含む）。"""
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM consent_records WHERE subject_id=? "
                "ORDER BY accepted_at DESC, id DESC LIMIT 1",
                (subject_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def latest_active(self, subject_id: str) -> Optional[ConsentRecord]:
        """撤回されていない最新の同意レコードを返す。"""
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM consent_records "
                "WHERE subject_id=? AND revoked_at IS NULL "
                "ORDER BY accepted_at DESC, id DESC LIMIT 1",
                (subject_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def history(self, subject_id: str) -> List[ConsentRecord]:
        """当該 subject の全履歴を新しい順で返す。"""
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM consent_records WHERE subject_id=? "
                "ORDER BY accepted_at DESC, id DESC",
                (subject_id,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def has_consent(
        self,
        subject_id: str,
        item: str,
        version: Optional[str] = None,
    ) -> bool:
        """指定項目に対するアクティブな同意があれば True。"""
        record = self.latest_active(subject_id)
        if record is None:
            return False
        if version is not None and record.version != version:
            return False
        return item in record.items

    def all_subjects(self) -> List[str]:
        """登録済みの subject_id 一覧。"""
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT subject_id FROM consent_records "
                "ORDER BY subject_id"
            ).fetchall()
        return [r["subject_id"] for r in rows]

    # ─── delete (GDPR 17 条との連動) ─────────────────────────

    def purge_subject(self, subject_id: str) -> int:
        """当該 subject の全 consent レコードを物理削除する。

        SubjectRightsManager.purge_subject と連動して呼ばれる想定。
        """
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM consent_records WHERE subject_id=?",
                (subject_id,),
            )
            count = cur.rowcount
        logger.warning(
            "consent purged: subject=%s count=%d", subject_id, count
        )
        return int(count)

    # ─── helpers ─────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ConsentRecord:
        items = tuple(json.loads(row["items"]))
        return ConsentRecord(
            id=row["id"],
            subject_id=row["subject_id"],
            version=row["version"],
            items=items,
            accepted_at=row["accepted_at"],
            revoked_at=row["revoked_at"],
        )


# ─── config loader ──────────────────────────────────────────


def load_consent_items(config_path: Path) -> Tuple[str, Tuple[str, ...], dict]:
    """consent_items.yaml を読み、(version, item_keys, raw) を返す。

    pyyaml が未インストールの場合は JSON 互換として読み直す簡易 fallback。
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"consent config not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw_text) or {}
    except ImportError:
        # stdlib のみの最終 fallback（簡易 YAML → JSON 想定外なら失敗させる）
        try:
            data = json.loads(raw_text)
        except Exception as exc:
            raise ConsentError(
                "pyyaml not installed and config is not JSON-compatible"
            ) from exc

    if not isinstance(data, dict):
        raise ConsentError("consent config root must be a mapping")

    version = str(data.get("version") or "").strip()
    items_section = data.get("items") or {}
    if not version:
        raise ConsentError("consent config missing 'version'")
    if not isinstance(items_section, dict) or not items_section:
        raise ConsentError("consent config missing 'items'")

    item_keys = tuple(sorted(str(k) for k in items_section.keys()))
    return version, item_keys, data


# ─── subject_rights フック ──────────────────────────────────


def register_with_subject_rights(
    subject_rights_manager: Any,
    consent_store: ConsentStore,
) -> None:
    """SubjectRightsManager.purge_subject に consent purge を連動させる。

    既存の ``purge_subject`` を monkey-patch せず、薄いラッパで差し替える。
    疎結合のため、manager 側は consent の存在を知らなくてよい。
    """
    if subject_rights_manager is None:
        return

    original_purge = getattr(subject_rights_manager, "purge_subject", None)
    if original_purge is None:
        logger.debug("subject_rights manager has no purge_subject; skip hook")
        return

    def _wrapped(subject_id: str = SELF_SUBJECT_ID, dry_run: bool = False) -> dict:
        report = original_purge(subject_id=subject_id, dry_run=dry_run)
        try:
            if dry_run:
                count = len(consent_store.history(subject_id))
            else:
                count = consent_store.purge_subject(subject_id)
            if isinstance(report, dict):
                report = dict(report)
                report["consent_records"] = int(count)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("consent purge hook failed: %s", exc)
            if isinstance(report, dict):
                report = dict(report)
                report.setdefault("errors", []).append(f"consent: {exc}")
        return report

    subject_rights_manager.purge_subject = _wrapped  # type: ignore[assignment]


__all__ = [
    "SELF_SUBJECT_ID",
    "SCHEMA_VERSION",
    "ConsentRecord",
    "ConsentStore",
    "ConsentError",
    "UnknownConsentItem",
    "load_consent_items",
    "register_with_subject_rights",
]
