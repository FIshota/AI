"""
kill_switch_policy — Kill-Switch 深化層 (5.7).

Sprint 2.1 の ``core.kill_switch.KillSwitch`` が「プロセス停止 + 緊急バックアップ」
に焦点を当てているのに対し、本モジュールは **家族価値観** の原則に則った
不可変 (frozen) かつテナント単位のシール (封印) ポリシーを提供する。

設計原則 (絶対):
    * **原本は絶対に動かさない**: シールは「読んでコピーして zip+sha256」のみ。
      .sealed マーカーを横に置くが、元ファイルは一切上書き/削除しない。
    * frozen dataclass で状態遷移を明示 (arm → trigger → release)。
    * stdlib + utils.crypto のみ。外部依存を持たない。

公開 API:
    * ``KillSwitchState`` — 現在の状態 (frozen)
    * ``SealVerification`` — 検証結果 (frozen)
    * ``KillSwitchPolicy`` — 振る舞い。状態はメソッド呼び出しで差し替える。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Tuple

__all__ = [
    "KillSwitchState",
    "SealVerification",
    "KillSwitchPolicy",
    "KillSwitchError",
    "KillSwitchArmedError",
    "KillSwitchReleaseError",
]

# シール対象のサブディレクトリ (tenant_root 配下)
_SEAL_SUBDIRS: Tuple[str, ...] = ("memory", "logs", "artifacts", "data", "audit")

# パスフレーズハッシュ置き場 (base/config/kill_switch.passphrase.hash)
_PASSPHRASE_HASH_REL = Path("config") / "kill_switch.passphrase.hash"

# シール置き場 (base/artifacts/kill_switch_seals/)
_SEAL_DIR_REL = Path("artifacts") / "kill_switch_seals"

# 書き込みロック (seal 並列実行のレース抑止)
_SEAL_LOCK = threading.Lock()


class KillSwitchError(RuntimeError):
    """Kill-Switch 関連の一般例外。"""


class KillSwitchArmedError(KillSwitchError):
    """armed 状態で禁止された操作 (新規書き込み等) が要求された。"""


class KillSwitchReleaseError(KillSwitchError):
    """release に失敗 (パスフレーズ不一致など)。"""


@dataclass(frozen=True)
class KillSwitchState:
    """Kill-Switch の現在状態 (不変)。"""

    armed: bool = False
    triggered_at: Optional[datetime] = None
    reason: Optional[str] = None
    sealed_paths: Tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SealVerification:
    """シールアーカイブの検証結果 (不変)。"""

    archive: Path
    ok: bool
    expected_sha256: str
    actual_sha256: str
    reason: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class KillSwitchPolicy:
    """テナント単位のシール/解除を司るポリシー。

    状態は immutable。各メソッドは新しい ``KillSwitchState`` を返す副作用を
    起こした上で、内部的に ``self._state`` を差し替える (public な state 参照は
    ``self.state`` プロパティ経由)。
    """

    def __init__(
        self,
        base_dir: os.PathLike | str,
        *,
        passphrase_hash_path: Optional[os.PathLike | str] = None,
    ) -> None:
        self._base = Path(base_dir).resolve()
        self._passphrase_hash_path = (
            Path(passphrase_hash_path)
            if passphrase_hash_path is not None
            else self._base / _PASSPHRASE_HASH_REL
        )
        self._state = KillSwitchState()
        self._mutex = threading.Lock()

    # ─── public properties ────────────────────────────────────

    @property
    def state(self) -> KillSwitchState:
        return self._state

    @property
    def seal_dir(self) -> Path:
        return self._base / _SEAL_DIR_REL

    # ─── state transitions ────────────────────────────────────

    def arm(self, *, reason: Optional[str] = None) -> KillSwitchState:
        """緊急停止モードを ON。新規書き込みは以降拒否される。"""
        with self._mutex:
            if self._state.armed:
                return self._state
            self._state = replace(self._state, armed=True, reason=reason)
            return self._state

    def check_write_allowed(self) -> None:
        """新規ログ/会話/感情更新など、書き込み直前に呼ぶガード。"""
        if self._state.armed:
            raise KillSwitchArmedError(
                "kill-switch is armed; new writes are rejected"
            )

    def trigger(
        self,
        reason: str,
        *,
        tenant_id: Optional[str] = None,
        tenant_root: Optional[os.PathLike | str] = None,
    ) -> KillSwitchState:
        """即時実行: arm → (任意で) テナントシール。

        * 原本は一切動かさない。
        * プロセス kill 自体はここでは行わず、``armed=True`` の状態を記録するだけ。
          (呼び出し側が OS シグナル送出等を行う)
        """
        with self._mutex:
            self._state = replace(
                self._state,
                armed=True,
                triggered_at=_utcnow(),
                reason=reason,
            )

        sealed_archive: Optional[Path] = None
        if tenant_id is not None:
            if tenant_root is None:
                tenant_root = self._base / tenant_id
            sealed_archive = self.seal_tenant(
                tenant_id=tenant_id, tenant_root=tenant_root, reason=reason
            )
        if sealed_archive is not None:
            with self._mutex:
                self._state = replace(
                    self._state,
                    sealed_paths=self._state.sealed_paths + (sealed_archive,),
                )
        return self._state

    def seal_tenant(
        self,
        tenant_id: str,
        tenant_root: os.PathLike | str,
        *,
        reason: Optional[str] = None,
    ) -> Path:
        """指定テナントの ``memory/`` / ``logs/`` / ``artifacts/`` を封印 (複製)。

        Returns:
            作成されたシールアーカイブ (``.zip``) のパス。
        """
        root = Path(tenant_root).resolve()
        if not root.exists():
            raise KillSwitchError(f"tenant root not found: {root}")

        self.seal_dir.mkdir(parents=True, exist_ok=True)
        ts = _utcnow().strftime("%Y%m%dT%H%M%SZ")
        archive = self.seal_dir / f"{tenant_id}_{ts}.seal.zip"
        manifest = {
            "tenant_id": tenant_id,
            "sealed_at": _utcnow().isoformat(),
            "reason": reason,
            "files": [],
        }

        with _SEAL_LOCK:
            # マーカーはテナント毎に別ファイル — 他テナント無影響
            marker = self.seal_dir / f"{tenant_id}.sealed"

            with zipfile.ZipFile(
                archive, "w", compression=zipfile.ZIP_DEFLATED
            ) as zf:
                for sub in _SEAL_SUBDIRS:
                    sub_path = root / sub
                    if not sub_path.exists() or not sub_path.is_dir():
                        continue
                    for p in sorted(sub_path.rglob("*")):
                        if not p.is_file():
                            continue
                        rel = p.relative_to(root)
                        data = p.read_bytes()  # 原本を動かさずコピー
                        zf.writestr(str(rel), data)
                        manifest["files"].append(
                            {
                                "path": str(rel),
                                "sha256": _sha256_bytes(data),
                                "size": len(data),
                            }
                        )
                zf.writestr(
                    "MANIFEST.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )

            # シール全体の sha256 を隣に保存
            archive_sha = _sha256_file(archive)
            (archive.with_suffix(".zip.sha256")).write_text(archive_sha, "utf-8")

            marker.write_text(
                json.dumps(
                    {
                        "tenant_id": tenant_id,
                        "archive": str(archive),
                        "sha256": archive_sha,
                        "sealed_at": manifest["sealed_at"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "utf-8",
            )

        with self._mutex:
            self._state = replace(
                self._state,
                sealed_paths=self._state.sealed_paths + (archive,),
            )
        return archive

    def verify_seal(self, sealed_archive: os.PathLike | str) -> SealVerification:
        """シール zip のハッシュと MANIFEST 内の各ファイルを検証する。"""
        archive = Path(sealed_archive)
        sha_file = archive.with_suffix(".zip.sha256")
        if not archive.exists():
            return SealVerification(
                archive=archive,
                ok=False,
                expected_sha256="",
                actual_sha256="",
                reason="archive not found",
            )
        expected = sha_file.read_text("utf-8").strip() if sha_file.exists() else ""
        actual = _sha256_file(archive)
        if expected and expected != actual:
            return SealVerification(
                archive=archive,
                ok=False,
                expected_sha256=expected,
                actual_sha256=actual,
                reason="outer archive sha256 mismatch",
            )

        # 中身 MANIFEST と個別ファイルの sha256 を照合
        try:
            with zipfile.ZipFile(archive, "r") as zf:
                manifest_raw = zf.read("MANIFEST.json")
                manifest = json.loads(manifest_raw.decode("utf-8"))
                for entry in manifest.get("files", []):
                    data = zf.read(entry["path"])
                    if _sha256_bytes(data) != entry["sha256"]:
                        return SealVerification(
                            archive=archive,
                            ok=False,
                            expected_sha256=expected or actual,
                            actual_sha256=actual,
                            reason=f"inner file sha mismatch: {entry['path']}",
                        )
                    if len(data) != entry["size"]:
                        return SealVerification(
                            archive=archive,
                            ok=False,
                            expected_sha256=expected or actual,
                            actual_sha256=actual,
                            reason=f"inner file size mismatch: {entry['path']}",
                        )
        except (KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            return SealVerification(
                archive=archive,
                ok=False,
                expected_sha256=expected or actual,
                actual_sha256=actual,
                reason=f"manifest read failed: {exc}",
            )

        return SealVerification(
            archive=archive,
            ok=True,
            expected_sha256=expected or actual,
            actual_sha256=actual,
        )

    def set_passphrase(self, passphrase: str) -> Path:
        """パスフレーズの sha256 を保存する (初期セットアップ用)。"""
        digest = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()
        self._passphrase_hash_path.parent.mkdir(parents=True, exist_ok=True)
        self._passphrase_hash_path.write_text(digest, "utf-8")
        try:
            os.chmod(self._passphrase_hash_path, 0o400)
        except OSError:
            pass
        return self._passphrase_hash_path

    def release(self, passphrase: str) -> KillSwitchState:
        """パスフレーズ検証に成功したら armed を解除する。"""
        if not self._passphrase_hash_path.exists():
            raise KillSwitchReleaseError(
                "passphrase hash file is not configured; cannot release"
            )
        expected = self._passphrase_hash_path.read_text("utf-8").strip()
        actual = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()
        if expected != actual:
            raise KillSwitchReleaseError("passphrase mismatch")
        with self._mutex:
            self._state = replace(
                self._state,
                armed=False,
                triggered_at=None,
                reason=None,
            )
        return self._state
