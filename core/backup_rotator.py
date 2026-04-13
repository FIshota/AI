"""
バックアップローテーター (Backup Rotator)
Sprint 2.1: データの定期バックアップと世代管理。

- 日次バックアップ: data/ と personality/ を tar.gz で圧縮
- 世代管理: 最新 N 世代を保持、古いものを自動削除
- 整合性: バックアップ後にチェックサムを記録
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import threading
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.audit_log import AuditLog

# バックアップ対象
_BACKUP_DIRS = ["data", "personality", "config"]

# 除外パターン
_EXCLUDE = {
    "__pycache__",
    ".DS_Store",
    "*.pyc",
    "*.tmp",
    ".key",          # 暗号鍵はバックアップに含めない
    "aichan.lock",
}


def _should_exclude(path: Path) -> bool:
    name = path.name
    for pat in _EXCLUDE:
        if pat.startswith("*"):
            if name.endswith(pat[1:]):
                return True
        elif name == pat:
            return True
    return False


class BackupRotator:
    """
    データのバックアップと世代ローテーション。
    """

    def __init__(
        self,
        base_dir: str | Path,
        audit: AuditLog | None = None,
        max_generations: int = 7,
    ):
        self._base = Path(base_dir)
        self._audit = audit
        self._max_gen = max_generations
        self._backup_dir = self._base / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    # ─── public ──────────────────────────────────────────────

    def create_backup(self, label: str = "") -> dict:
        """
        バックアップを作成する。
        戻り値: {"path": str, "size_mb": float, "checksum": str, "files": int}
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        filename = f"aichan_backup_{ts}{suffix}.tar.gz"
        backup_path = self._backup_dir / filename

        file_count = 0
        with tarfile.open(backup_path, "w:gz") as tar:
            for dir_name in _BACKUP_DIRS:
                src = self._base / dir_name
                if not src.exists():
                    continue
                for item in src.rglob("*"):
                    if not item.is_file():
                        continue
                    if _should_exclude(item):
                        continue
                    arcname = str(item.relative_to(self._base))
                    tar.add(item, arcname=arcname)
                    file_count += 1

        size_mb = round(backup_path.stat().st_size / 1024 / 1024, 2)
        checksum = self._sha256(backup_path)

        # メタデータを保存
        meta = {
            "filename": filename,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "size_mb": size_mb,
            "checksum": checksum,
            "files": file_count,
            "label": label,
        }
        meta_path = backup_path.with_suffix(".json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, ensure_ascii=False, indent=2, fp=f)

        self._log("INFO", "backup_created", f"{filename} ({size_mb}MB, {file_count}files)")

        # ローテーション
        self._rotate()

        return {
            "path": str(backup_path),
            "size_mb": size_mb,
            "checksum": checksum,
            "files": file_count,
        }

    def restore_backup(self, backup_name: str) -> dict:
        """
        指定バックアップからリストアする。
        戻り値: {"restored": int, "errors": list[str]}
        """
        backup_path = self._backup_dir / backup_name
        if not backup_path.exists():
            return {"restored": 0, "errors": [f"Not found: {backup_name}"]}

        # リストア前のバックアップを作成
        self.create_backup(label="pre_restore")

        errors: list[str] = []
        restored = 0
        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                # セキュリティ: パストラバーサルチェック
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        errors.append(f"Skipped unsafe path: {member.name}")
                        continue
                    tar.extract(member, path=self._base)
                    restored += 1
        except Exception as e:
            errors.append(str(e))

        self._log(
            "WARN" if errors else "INFO",
            "backup_restored",
            f"{backup_name}: {restored} files, {len(errors)} errors",
        )
        return {"restored": restored, "errors": errors}

    def list_backups(self) -> list[dict]:
        """利用可能なバックアップ一覧を返す"""
        backups: list[dict] = []
        for meta_path in sorted(self._backup_dir.glob("*.json")):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                backups.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
        return backups

    def verify_backup(self, backup_name: str) -> bool:
        """バックアップのチェックサムを検証する"""
        backup_path = self._backup_dir / backup_name
        meta_path = backup_path.with_suffix(".json")
        if not backup_path.exists() or not meta_path.exists():
            return False
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return self._sha256(backup_path) == meta.get("checksum", "")
        except Exception:
            return False

    # ─── ジョブ登録用 ────────────────────────────────────────

    def daily_job(self) -> dict:
        """AutonomousEngine の daily ジョブとして登録用"""
        result = self.create_backup(label="daily")
        return {"action": "backup_daily", "result": result}

    # ─── private ─────────────────────────────────────────────

    def _rotate(self) -> None:
        """最大世代数を超えたバックアップを削除する"""
        archives = sorted(
            self._backup_dir.glob("aichan_backup_*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in archives[self._max_gen:]:
            try:
                old.unlink()
                meta = old.with_suffix(".json")
                if meta.exists():
                    meta.unlink()
                self._log("INFO", "backup_rotated", f"Deleted: {old.name}")
            except OSError:
                pass

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _log(self, severity: str, event: str, detail: str) -> None:
        if self._audit is None:
            return
        try:
            getattr(self._audit, severity.lower(), self._audit.info)(event, detail)
        except Exception:
            pass
