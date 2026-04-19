#!/usr/bin/env python3
"""ai-chan 記憶切り離し Phase A — 非破壊アーカイブ.

本スクリプトは ai-chan 本体から記憶・運用痕跡を "コピー" してアーカイブする。
本体ファイルは一切変更しない (Phase B で初めて削除)。

出力先:
  - ローカル: ~/ai-chan-archive/<stamp>/
  - SSD:      /Volumes/backup/ai-chan-archive/<stamp>/

暗号化:
  - 機微ディレクトリ (data/, logs/, personality/, yamato_dna/) は Fernet 暗号化
  - 公開・軽量ディレクトリ (models/, output/, reports/) は平文 tar.gz
  - transport key は keys/transport.key に両方保存

検証:
  - 各アーカイブの SHA256 を manifest.json に記録
  - スクリプト末尾で transport key によるテスト復号を実施
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/fujihiranoborudai/Downloads/agent/ai-chan")
STAMP = datetime.now(timezone.utc).strftime("%Y-%m-%d-phase0-detach")
LOCAL_ARCH = Path.home() / "ai-chan-archive" / STAMP
SSD_ARCH = Path("/Volumes/backup/ai-chan-archive") / STAMP

# (dir_name, encrypt?)
TARGETS: list[tuple[str, bool]] = [
    ("data",        True),
    ("logs",        True),
    ("personality", True),
    ("yamato_dna",  True),
    ("models",      False),
    ("output",      False),
    ("reports",     False),
    # backups/ は空なのでスキップ
]


def _ensure_cryptography() -> None:
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print("[detach] cryptography が見つかりません。pip install cryptography")
        sys.exit(2)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_tar_bytes(src: Path) -> bytes:
    """ディレクトリを tar.gz の bytes にする (メモリ上で)。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(src, arcname=src.name)
    return buf.getvalue()


def _write_both(rel_path: str, data: bytes) -> dict:
    """ローカルと SSD の両方に同じバイト列を書き込み、サイズと SHA256 を返す。"""
    sha = _sha256(data)
    for base in (LOCAL_ARCH, SSD_ARCH):
        dst = base / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    return {"path": rel_path, "size": len(data), "sha256": sha}


def main() -> int:
    _ensure_cryptography()
    from cryptography.fernet import Fernet

    if not ROOT.exists():
        print(f"[detach] project root not found: {ROOT}", file=sys.stderr)
        return 1
    if not Path("/Volumes/backup").exists():
        print("[detach] SSD (/Volumes/backup) が見つかりません。", file=sys.stderr)
        return 1

    LOCAL_ARCH.mkdir(parents=True, exist_ok=True)
    SSD_ARCH.mkdir(parents=True, exist_ok=True)
    print(f"[detach] local: {LOCAL_ARCH}")
    print(f"[detach] ssd  : {SSD_ARCH}")

    # 1) transport key を生成 (両方の場所に保存)
    transport_key = Fernet.generate_key()
    cipher = Fernet(transport_key)
    for base in (LOCAL_ARCH, SSD_ARCH):
        kdir = base / "keys"
        kdir.mkdir(parents=True, exist_ok=True)
        kp = kdir / "transport.key"
        kp.write_bytes(transport_key)
        kp.chmod(0o400)
    print(f"[detach] transport key 生成・保存完了 ({len(transport_key)} bytes)")

    manifest = {
        "stamp": STAMP,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "local_archive": str(LOCAL_ARCH),
        "ssd_archive": str(SSD_ARCH),
        "transport_key_file": "keys/transport.key",
        "entries": [],
    }

    # 2) 各ディレクトリをアーカイブ
    for name, encrypt in TARGETS:
        src = ROOT / name
        if not src.exists():
            print(f"[detach] skip {name} (not present)")
            continue
        print(f"[detach] archiving {name} (encrypt={encrypt}) ...")
        raw = _make_tar_bytes(src)
        raw_sha = _sha256(raw)
        if encrypt:
            payload = cipher.encrypt(raw)
            fname = f"{name}.tar.gz.enc"
        else:
            payload = raw
            fname = f"{name}.tar.gz"
        entry = _write_both(fname, payload)
        entry.update({
            "source": name,
            "encrypted": encrypt,
            "plain_sha256": raw_sha,
            "plain_size": len(raw),
        })
        manifest["entries"].append(entry)
        print(
            f"  ✓ {fname}  plain={len(raw)/1024/1024:.1f}MB  "
            f"out={len(payload)/1024/1024:.1f}MB  sha256={entry['sha256'][:16]}..."
        )

    # 3) manifest.json 書き込み
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    for base in (LOCAL_ARCH, SSD_ARCH):
        (base / "manifest.json").write_bytes(manifest_bytes)
    print(f"[detach] manifest.json 書き込み完了 ({len(manifest_bytes)} bytes)")

    # 4) 検証: transport key で暗号化アーカイブを 1 件試し復号
    print("[detach] 検証中: transport key による復号 + tar 展開テスト ...")
    for entry in manifest["entries"]:
        if not entry["encrypted"]:
            continue
        enc = (LOCAL_ARCH / entry["path"]).read_bytes()
        plain = cipher.decrypt(enc)
        assert _sha256(plain) == entry["plain_sha256"], \
            f"checksum mismatch on decrypt: {entry['path']}"
        # tar 構造の妥当性も検証
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as t:
            names = t.getnames()[:3]
        print(f"  ✓ {entry['path']}  decrypt OK  top={names}")

    print()
    print("=" * 60)
    print("[detach] Phase A 完了 (非破壊). 本体は一切変更されていません.")
    print("=" * 60)
    print(f"local : {LOCAL_ARCH}")
    print(f"ssd   : {SSD_ARCH}")
    print()
    print("次のステップ:")
    print("  1) /Volumes/backup/ai-chan-archive/ の中身を目視確認")
    print("  2) 1Password 等に transport.key を追加退避 (推奨)")
    print("  3) Phase B (本体から物理削除) の承認をください")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
