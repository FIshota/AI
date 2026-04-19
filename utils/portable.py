"""
ポータビリティユーティリティ
USB/SSD へのアイの完全なコピー・移行を管理します

機能:
  - copy_to_portable: 完全コピー
  - incremental_backup: 差分バックアップ（変更ファイルのみコピー）
  - export_portable_package: ZIP パッケージエクスポート
  - import_portable_package: ZIP パッケージインポート
  - export_encrypted_backup: 暗号化バックアップ
"""
from __future__ import annotations

import logging
import shutil
import json
import hashlib
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# コピーすべき必須ディレクトリ・ファイル
COPY_TARGETS = [
    "core",
    "utils",
    "ui",
    "config",
    "data",
    "models",
    "main.py",
    "requirements.txt",
    "scripts",
]

# コピー不要なパターン
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    ".DS_Store",
    "*.tmp",
]


def compute_checksum(path: Path) -> str:
    """ファイルのSHA256チェックサムを計算します"""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def copy_to_portable(source_dir: str | Path, dest_dir: str | Path, verify: bool = True) -> dict:
    """
    アイ全体を dest_dir にコピーします。
    戻り値: コピー結果レポート
    """
    source = Path(source_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "source": str(source),
        "destination": str(dest),
        "files_copied": [],
        "errors": [],
        "total_size_bytes": 0,
    }

    for target in COPY_TARGETS:
        src_path = source / target
        if not src_path.exists():
            continue

        dst_path = dest / target

        try:
            if src_path.is_dir():
                if dst_path.exists():
                    shutil.rmtree(dst_path)
                shutil.copytree(
                    src_path,
                    dst_path,
                    ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS),
                )
                for f in dst_path.rglob("*"):
                    if f.is_file():
                        size = f.stat().st_size
                        report["files_copied"].append(str(f.relative_to(dest)))
                        report["total_size_bytes"] += size
            else:
                shutil.copy2(src_path, dst_path)
                size = dst_path.stat().st_size
                report["files_copied"].append(str(dst_path.relative_to(dest)))
                report["total_size_bytes"] += size

        except Exception as e:
            report["errors"].append(f"{target}: {e}")

    # コピー完了メタデータを保存
    meta = {
        "copied_at": report["timestamp"],
        "source": str(source),
        "files_count": len(report["files_copied"]),
        "total_mb": round(report["total_size_bytes"] / 1024 / 1024, 2),
    }
    (dest / ".ai_chan_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    report["success"] = len(report["errors"]) == 0
    report["total_mb"] = round(report["total_size_bytes"] / 1024 / 1024, 2)
    return report


def is_ai_chan_dir(path: str | Path) -> bool:
    """指定パスがアイのディレクトリかどうか確認します"""
    p = Path(path)
    return (p / ".ai_chan_meta.json").exists() or (p / "main.py").exists()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 差分バックアップ (#25)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_MANIFEST_NAME = ".backup_manifest.json"


def _compute_file_hashes(directory: str | Path) -> dict[str, str]:
    """
    ディレクトリ内の全ファイルの SHA-256 ハッシュを計算する。

    Returns:
        {相対パス文字列: SHA-256 ハッシュ文字列}
    """
    base = Path(directory)
    hashes: dict[str, str] = {}
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        # 除外パターンをスキップ
        rel = str(f.relative_to(base))
        if any(part in rel for part in ("__pycache__", ".git", ".DS_Store")):
            continue
        if rel.endswith((".pyc", ".tmp")):
            continue
        hashes[rel] = compute_checksum(f)
    return hashes


def incremental_backup(
    source_dir: str | Path,
    dest_dir: str | Path,
) -> dict:
    """
    差分バックアップ: 前回のマニフェストと比較し、変更されたファイルのみコピーする。

    初回実行時は全ファイルをコピーする（フルバックアップ）。

    Returns:
        バックアップ結果レポート
    """
    source = Path(source_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    manifest_path = dest / _MANIFEST_NAME

    # 前回のマニフェストを読み込み
    old_manifest: dict[str, str] = {}
    if manifest_path.exists():
        try:
            old_manifest = json.loads(manifest_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            old_manifest = {}

    # 現在のハッシュを計算
    current_hashes = _compute_file_hashes(source)

    # 変更されたファイルを特定
    changed_files: list[str] = []
    for rel_path, current_hash in current_hashes.items():
        if old_manifest.get(rel_path) != current_hash:
            changed_files.append(rel_path)

    # 削除されたファイルを特定
    deleted_files = [
        rel for rel in old_manifest if rel not in current_hashes
    ]

    report = {
        "timestamp": datetime.now().isoformat(),
        "source": str(source),
        "destination": str(dest),
        "files_copied": [],
        "files_deleted": deleted_files,
        "errors": [],
        "is_full_backup": len(old_manifest) == 0,
    }

    # 変更ファイルをコピー
    for rel_path in changed_files:
        src_file = source / rel_path
        dst_file = dest / rel_path
        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            report["files_copied"].append(rel_path)
        except Exception as e:
            report["errors"].append(f"{rel_path}: {e}")

    # 新しいマニフェストを保存
    manifest_path.write_text(
        json.dumps(current_hashes, ensure_ascii=False, indent=2), "utf-8"
    )

    report["success"] = len(report["errors"]) == 0
    report["total_changed"] = len(changed_files)
    logger.info(
        "差分バックアップ完了: %d ファイルコピー, %d ファイル削除検出",
        len(report["files_copied"]),
        len(deleted_files),
    )
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ポータブル ZIP パッケージ (#46)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ZIP に含めるディレクトリ・ファイル
_ZIP_TARGETS = ["data", "config", "models", "core", "ui", "utils", "main.py"]

# ZIP から除外するパターン
_ZIP_EXCLUDE_PARTS = {"__pycache__", ".git", "logs"}
_ZIP_EXCLUDE_SUFFIXES = {".pyc", ".log", ".tmp"}


def _should_exclude_from_zip(rel_path: str) -> bool:
    """ZIP パッケージから除外すべきパスか判定する"""
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        if part in _ZIP_EXCLUDE_PARTS:
            return True
    for suffix in _ZIP_EXCLUDE_SUFFIXES:
        if rel_path.endswith(suffix):
            return True
    return False


def export_portable_package(
    base_dir: str | Path,
    output: str | Path,
) -> str:
    """
    アイのポータブル ZIP パッケージを作成する。

    含むもの: data, config, models, core, ui, utils, main.py
    除外: __pycache__, .git, logs, *.pyc, *.log, *.tmp

    Args:
        base_dir: アイのベースディレクトリ
        output: 出力 ZIP ファイルパス

    Returns:
        作成された ZIP ファイルのパス文字列
    """
    base = Path(base_dir)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for target in _ZIP_TARGETS:
            target_path = base / target
            if not target_path.exists():
                continue

            if target_path.is_file():
                zf.write(target_path, target)
            else:
                for f in sorted(target_path.rglob("*")):
                    if not f.is_file():
                        continue
                    rel = str(f.relative_to(base))
                    if _should_exclude_from_zip(rel):
                        continue
                    zf.write(f, rel)

        # メタデータを追加
        meta = {
            "exported_at": datetime.now().isoformat(),
            "source": str(base),
            "version": "portable-v1",
        }
        zf.writestr(
            ".ai_chan_portable.json",
            json.dumps(meta, ensure_ascii=False, indent=2),
        )

    logger.info("ポータブルパッケージ作成: %s", out)
    return str(out)


def import_portable_package(
    zip_path: str | Path,
    target: str | Path,
) -> dict:
    """
    ポータブル ZIP パッケージを展開してインポートする。

    Args:
        zip_path: ZIP ファイルパス
        target: 展開先ディレクトリ

    Returns:
        インポート結果レポート
    """
    zp = Path(zip_path)
    tgt = Path(target)
    tgt.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "timestamp": datetime.now().isoformat(),
        "zip_path": str(zp),
        "target": str(tgt),
        "files_extracted": [],
        "errors": [],
    }

    if not zp.exists():
        report["errors"].append(f"ZIP ファイルが見つかりません: {zp}")
        report["success"] = False
        return report

    try:
        with zipfile.ZipFile(zp, "r") as zf:
            for member in zf.namelist():
                # パストラバーサル防止
                if ".." in member or member.startswith("/"):
                    report["errors"].append(f"安全でないパス: {member}")
                    continue
                zf.extract(member, tgt)
                report["files_extracted"].append(member)
    except Exception as e:
        report["errors"].append(f"展開失敗: {e}")

    report["success"] = len(report["errors"]) == 0
    logger.info(
        "ポータブルパッケージインポート: %d ファイル展開",
        len(report["files_extracted"]),
    )
    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 暗号化バックアップ (#99)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def export_encrypted_backup(
    base_dir: str | Path,
    output: str | Path,
    passphrase: str,
) -> str:
    """
    暗号化バックアップを作成する。

    1. ポータブル ZIP パッケージを作成（一時ファイル）
    2. パスフレーズから暗号化キーを導出
    3. ZIP を AES-256-GCM で暗号化
    4. 出力: salt(16bytes) + encrypted_zip

    Args:
        base_dir: アイのベースディレクトリ
        output: 出力暗号化ファイルパス
        passphrase: 暗号化パスフレーズ

    Returns:
        作成された暗号化ファイルのパス文字列
    """
    from utils.crypto import derive_key_from_passphrase, encrypt

    base = Path(base_dir)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 一時 ZIP を作成
    tmp_zip = out.with_suffix(".tmp.zip")
    try:
        export_portable_package(base, tmp_zip)

        # 暗号化
        key, salt = derive_key_from_passphrase(passphrase)
        zip_data = tmp_zip.read_bytes()
        encrypted_data = encrypt(zip_data, key)

        # salt + 暗号化データを保存
        out.write_bytes(salt + encrypted_data)

    finally:
        # 一時ファイル削除
        if tmp_zip.exists():
            tmp_zip.unlink()

    logger.info("暗号化バックアップ作成: %s", out)
    return str(out)
