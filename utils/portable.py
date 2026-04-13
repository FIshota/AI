"""
ポータビリティユーティリティ
USB/SSD へのアイの完全なコピー・移行を管理します
"""
from __future__ import annotations
import shutil
import json
import hashlib
from pathlib import Path
from datetime import datetime


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
