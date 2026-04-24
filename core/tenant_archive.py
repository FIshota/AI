"""
tenant_archive — テナント単位の完全バックアップ/エクスポート/インポート基盤 (5.7).

CLI (``scripts/tenant_export.py`` / ``scripts/tenant_import.py``) の中核ロジック。

設計:
    * tar.gz を基本フォーマットとする (POSIX 相互運用性優先)。
    * 各ファイルの相対パス + sha256 + size を ``MANIFEST.json`` に記録。
    * ``--encrypt`` 時は tar.gz を作った後に utils.crypto.encrypt でラップ。
      (後置き暗号化により MANIFEST 検証 → 暗号化の分離が単純)
    * 原本は一切動かさない。エクスポートは読み取りのみ。

stdlib + utils.crypto のみ。全 dataclass は frozen。
"""
from __future__ import annotations

import getpass
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from utils import crypto as _crypto

__all__ = [
    "ExportOptions",
    "ExportResult",
    "ImportOptions",
    "ImportResult",
    "ManifestEntry",
    "export_tenant",
    "import_tenant",
    "verify_archive",
]

_DEFAULT_CONFIG_SUBDIR = "config"
_DEFAULT_LOGS_SUBDIR = "logs"
_DEFAULT_MEMORY_SUBDIR = "memory"
_DEFAULT_ARTIFACTS_SUBDIR = "artifacts"

# 既定の除外パターン (再生成可能)
_EXCLUDE_ALWAYS = (
    "artifacts/golden",
    "artifacts/golden/",
)


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ExportOptions:
    tenant_id: str
    source_root: Path
    output_path: Path
    include_memory: bool = False
    include_logs: bool = True
    include_artifacts: bool = True
    include_config: bool = True
    encrypt: bool = False
    passphrase: Optional[str] = None
    verify: bool = False


@dataclass(frozen=True)
class ExportResult:
    archive: Path
    manifest: Tuple[ManifestEntry, ...]
    encrypted: bool
    archive_sha256: str
    verified: bool


@dataclass(frozen=True)
class ImportOptions:
    archive: Path
    base_dir: Path
    target_tenant: Optional[str] = None
    passphrase: Optional[str] = None
    force: bool = False


@dataclass(frozen=True)
class ImportResult:
    target_root: Path
    files_restored: int
    verified: bool


# ── internal helpers ────────────────────────────────────────────


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


def _collect_files(opts: ExportOptions) -> List[Tuple[Path, str]]:
    """エクスポート対象ファイルを (絶対パス, テナント root からの相対パス) で列挙。"""
    root = opts.source_root
    selected: List[Tuple[Path, str]] = []
    subs: List[str] = []
    if opts.include_config:
        subs.append(_DEFAULT_CONFIG_SUBDIR)
    if opts.include_memory:
        subs.append(_DEFAULT_MEMORY_SUBDIR)
    if opts.include_logs:
        subs.append(_DEFAULT_LOGS_SUBDIR)
    if opts.include_artifacts:
        subs.append(_DEFAULT_ARTIFACTS_SUBDIR)

    for sub in subs:
        sub_path = root / sub
        if not sub_path.exists() or not sub_path.is_dir():
            continue
        for p in sorted(sub_path.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if any(rel.startswith(ex) for ex in _EXCLUDE_ALWAYS):
                continue
            selected.append((p, rel))
    return selected


def _build_manifest(files: Iterable[Tuple[Path, str]]) -> Tuple[ManifestEntry, ...]:
    return tuple(
        ManifestEntry(
            path=rel,
            sha256=_sha256_file(p),
            size=p.stat().st_size,
        )
        for p, rel in files
    )


def _write_tar_gz(
    tar_path: Path,
    files: Sequence[Tuple[Path, str]],
    manifest: Tuple[ManifestEntry, ...],
    tenant_id: str,
) -> None:
    manifest_data = {
        "tenant_id": tenant_id,
        "created_at": _utcnow().isoformat(),
        "files": [
            {"path": e.path, "sha256": e.sha256, "size": e.size}
            for e in manifest
        ],
    }
    manifest_bytes = json.dumps(
        manifest_data, ensure_ascii=False, indent=2
    ).encode("utf-8")

    tar_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "w:gz") as tf:
        info = tarfile.TarInfo("MANIFEST.json")
        info.size = len(manifest_bytes)
        info.mtime = int(_utcnow().timestamp())
        tf.addfile(info, io.BytesIO(manifest_bytes))
        for p, rel in files:
            tf.add(p, arcname=rel, recursive=False)


def _read_manifest_from_tar(tar_path: Path) -> dict:
    with tarfile.open(tar_path, "r:gz") as tf:
        member = tf.getmember("MANIFEST.json")
        f = tf.extractfile(member)
        if f is None:
            raise ValueError("MANIFEST.json is unreadable")
        return json.loads(f.read().decode("utf-8"))


def _resolve_passphrase(passphrase: Optional[str], *, prompt: str) -> str:
    if passphrase:
        return passphrase
    env = os.environ.get("AICHAN_EXPORT_KEY")
    if env:
        return env
    return getpass.getpass(prompt)


def _encrypt_file(src: Path, dst: Path, passphrase: str) -> None:
    key, salt = _crypto.derive_key_from_passphrase(passphrase)
    data = src.read_bytes()
    ciphertext = _crypto.encrypt(data, key)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # フォーマット: magic(8) + salt_len(1) + salt + ciphertext
    with dst.open("wb") as f:
        f.write(b"AICHANE1")
        f.write(bytes([len(salt)]))
        f.write(salt)
        f.write(ciphertext)


def _decrypt_file(src: Path, dst: Path, passphrase: str) -> None:
    raw = src.read_bytes()
    if not raw.startswith(b"AICHANE1"):
        raise ValueError("not an aichan encrypted export")
    salt_len = raw[8]
    salt = raw[9 : 9 + salt_len]
    ciphertext = raw[9 + salt_len :]
    key, _ = _crypto.derive_key_from_passphrase(passphrase, salt=salt)
    plaintext = _crypto.decrypt(ciphertext, key)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(plaintext)


# ── public API ──────────────────────────────────────────────────


def export_tenant(opts: ExportOptions) -> ExportResult:
    """テナントの完全エクスポートを生成する。"""
    if not opts.source_root.exists():
        raise FileNotFoundError(f"source root not found: {opts.source_root}")

    files = _collect_files(opts)
    manifest = _build_manifest(files)

    opts.output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tar_tmp = Path(tmp) / "export.tar.gz"
        _write_tar_gz(tar_tmp, files, manifest, opts.tenant_id)

        if opts.encrypt:
            pw = _resolve_passphrase(
                opts.passphrase, prompt="エクスポート暗号化パスフレーズ: "
            )
            _encrypt_file(tar_tmp, opts.output_path, pw)
        else:
            shutil.copy2(tar_tmp, opts.output_path)

    archive_sha = _sha256_file(opts.output_path)

    verified = False
    if opts.verify:
        verified = _round_trip_verify(
            opts.output_path,
            manifest,
            encrypt=opts.encrypt,
            passphrase=opts.passphrase,
        )

    return ExportResult(
        archive=opts.output_path,
        manifest=manifest,
        encrypted=opts.encrypt,
        archive_sha256=archive_sha,
        verified=verified,
    )


def _round_trip_verify(
    archive: Path,
    manifest: Tuple[ManifestEntry, ...],
    *,
    encrypt: bool,
    passphrase: Optional[str],
) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "verify.tar.gz"
        if encrypt:
            pw = _resolve_passphrase(
                passphrase, prompt="検証用パスフレーズ再入力: "
            )
            _decrypt_file(archive, tar_path, pw)
        else:
            shutil.copy2(archive, tar_path)
        got = _read_manifest_from_tar(tar_path)
        got_files = {e["path"]: (e["sha256"], e["size"]) for e in got["files"]}
        for entry in manifest:
            ref = got_files.get(entry.path)
            if ref is None:
                return False
            if ref != (entry.sha256, entry.size):
                return False
        return True


def verify_archive(
    archive: Path,
    *,
    encrypt: bool = False,
    passphrase: Optional[str] = None,
) -> bool:
    """アーカイブ内 MANIFEST の sha256 と実ファイルを突合する。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "verify.tar.gz"
        if encrypt:
            pw = _resolve_passphrase(
                passphrase, prompt="検証用パスフレーズ: "
            )
            _decrypt_file(archive, tar_path, pw)
        else:
            shutil.copy2(archive, tar_path)
        manifest = _read_manifest_from_tar(tar_path)
        with tarfile.open(tar_path, "r:gz") as tf:
            for entry in manifest["files"]:
                member = tf.getmember(entry["path"])
                f = tf.extractfile(member)
                if f is None:
                    return False
                data = f.read()
                if _sha256_bytes(data) != entry["sha256"]:
                    return False
                if len(data) != entry["size"]:
                    return False
    return True


def import_tenant(opts: ImportOptions) -> ImportResult:
    """エクスポートアーカイブを展開してテナントを復元する。"""
    if not opts.archive.exists():
        raise FileNotFoundError(f"archive not found: {opts.archive}")

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "import.tar.gz"
        # 暗号化判定 (magic)
        magic = opts.archive.open("rb").read(8)
        is_encrypted = magic == b"AICHANE1"
        if is_encrypted:
            pw = _resolve_passphrase(
                opts.passphrase, prompt="復号パスフレーズ: "
            )
            _decrypt_file(opts.archive, tar_path, pw)
        else:
            shutil.copy2(opts.archive, tar_path)

        manifest = _read_manifest_from_tar(tar_path)
        orig_tenant = manifest.get("tenant_id", "unknown")
        target_tenant = opts.target_tenant or orig_tenant

        target_root = opts.base_dir / target_tenant
        if target_root.exists() and not opts.force:
            raise FileExistsError(
                f"target tenant already exists: {target_root} (use force=True)"
            )
        if target_root.exists() and opts.force:
            shutil.rmtree(target_root)

        target_root.mkdir(parents=True, exist_ok=True)

        with tarfile.open(tar_path, "r:gz") as tf:
            verified = 0
            for entry in manifest["files"]:
                member = tf.getmember(entry["path"])
                f = tf.extractfile(member)
                if f is None:
                    raise ValueError(f"cannot extract {entry['path']}")
                data = f.read()
                if _sha256_bytes(data) != entry["sha256"]:
                    raise ValueError(
                        f"manifest sha mismatch for {entry['path']}"
                    )
                dst = target_root / entry["path"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
                verified += 1

    return ImportResult(
        target_root=target_root,
        files_restored=verified,
        verified=True,
    )
