"""
整合性監視 (Integrity Monitor)
Sprint 2.1: 起動時とランタイムにデータファイルの改ざんを検知する。

SHA-256 チェックサムのマニフェストを保持し、差分を検出する。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.audit_log import AuditLog

# 監視対象ファイルパターン
_WATCH_PATTERNS: list[str] = [
    "data/*.json",
    "data/*.jsonl",
    "data/*.db",
    "data/learning/*.jsonl",
    "data/minutes/*.jsonl",
    "config/*.json",
    "personality/*.yaml",
]

# 除外パターン（一時ファイル、WAL、ロック）
_EXCLUDE_SUFFIXES = {".db-shm", ".db-wal", ".lock", ".tmp", ".bak"}


def _sha256(path: Path) -> str:
    """ファイルの SHA-256 を返す"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class IntegrityMonitor:
    """
    データファイルの整合性を監視する。

    - startup_check(): 起動時にマニフェストと現状を比較
    - refresh(): マニフェストを再構築
    - verify(): 任意のタイミングで検証
    """

    def __init__(
        self,
        base_dir: str | Path,
        audit: AuditLog | None = None,
    ):
        self._base = Path(base_dir)
        self._audit = audit
        self._manifest_path = self._base / "data" / ".integrity_manifest.json"
        self._manifest: dict[str, str] = self._load_manifest()

    # ─── public ──────────────────────────────────────────────

    def startup_check(self) -> dict:
        """
        起動時チェック。マニフェストが無ければ作成、あれば検証。
        戻り値: {"status": "ok"|"warn"|"new", "modified": [...], "missing": [...], "added": [...]}
        """
        if not self._manifest:
            self.refresh()
            self._log("INFO", "integrity_manifest_created", "初回マニフェスト作成")
            return {"status": "new", "modified": [], "missing": [], "added": []}

        return self.verify()

    def verify(self) -> dict:
        """現在のファイル状態とマニフェストを比較する"""
        current = self._scan_files()
        modified: list[str] = []
        missing: list[str] = []
        added: list[str] = []

        # マニフェストにあるが変わった or 消えた
        for rel_path, expected_hash in self._manifest.items():
            if rel_path not in current:
                missing.append(rel_path)
            elif current[rel_path] != expected_hash:
                modified.append(rel_path)

        # 新しく増えたファイル
        for rel_path in current:
            if rel_path not in self._manifest:
                added.append(rel_path)

        status = "ok"
        if modified or missing:
            status = "warn"

        # 監査ログに記録
        if modified:
            self._log("WARN", "integrity_modified", f"改ざん検知: {modified}")
        if missing:
            self._log("WARN", "integrity_missing", f"ファイル消失: {missing}")
        if added:
            self._log("INFO", "integrity_added", f"新規ファイル: {added}")

        return {
            "status": status,
            "modified": modified,
            "missing": missing,
            "added": added,
        }

    def refresh(self) -> int:
        """マニフェストを現在の状態で再構築する。更新したファイル数を返す。"""
        self._manifest = self._scan_files()
        self._save_manifest()
        self._log("INFO", "integrity_refreshed", f"{len(self._manifest)} files")
        return len(self._manifest)

    def get_manifest(self) -> dict[str, str]:
        """現在のマニフェストを返す（読み取り専用コピー）"""
        return dict(self._manifest)

    # ─── ジョブ登録用 ────────────────────────────────────────

    def hourly_job(self) -> dict:
        """AutonomousEngine の hourly ジョブとして登録用"""
        result = self.verify()
        if result["modified"] or result["missing"]:
            return {"action": "integrity_alert", "result": result}
        return {"action": "integrity_ok"}

    # ─── private ─────────────────────────────────────────────

    def _scan_files(self) -> dict[str, str]:
        """監視対象ファイルのハッシュマップを構築する"""
        files: dict[str, str] = {}
        for pattern in _WATCH_PATTERNS:
            for path in self._base.glob(pattern):
                if not path.is_file():
                    continue
                if path.suffix in _EXCLUDE_SUFFIXES:
                    continue
                rel = str(path.relative_to(self._base))
                try:
                    files[rel] = _sha256(path)
                except (OSError, PermissionError):
                    continue
        return files

    def _load_manifest(self) -> dict[str, str]:
        if not self._manifest_path.exists():
            return {}
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("files", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_manifest(self) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._manifest),
            "files": self._manifest,
        }
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _log(self, severity: str, event: str, detail: str) -> None:
        if self._audit is None:
            return
        try:
            getattr(self._audit, severity.lower(), self._audit.info)(event, detail)
        except Exception:
            pass
