#!/usr/bin/env python3
"""ai-chan 記憶復元ツール (家族モード).

使い方:
    python3 scripts/restore_memory.py --from /Volumes/backup/ai-chan-archive/2026-04-20-phase0-detach
    python3 scripts/restore_memory.py --from ~/ai-chan-archive/2026-04-20-phase0-detach --only data logs

Phase B で本体から切り離された記憶を、アーカイブから本体へ復元する。
transport.key は --from で指定したディレクトリ内の keys/transport.key を使う。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path("/Users/fujihiranoborudai/Downloads/agent/ai-chan")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="src", required=True, help="archive directory")
    p.add_argument("--only", nargs="*", default=None, help="restrict to these source names")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    src = Path(args.src).expanduser()
    manifest_path = src / "manifest.json"
    key_path = src / "keys" / "transport.key"

    if not manifest_path.exists():
        print(f"[restore] manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    if not key_path.exists():
        print(f"[restore] transport.key not found: {key_path}", file=sys.stderr)
        return 1

    from cryptography.fernet import Fernet

    manifest = json.loads(manifest_path.read_text())
    cipher = Fernet(key_path.read_bytes())
    entries = manifest["entries"]
    if args.only:
        entries = [e for e in entries if e["source"] in set(args.only)]
        if not entries:
            print(f"[restore] no entries match --only {args.only}", file=sys.stderr)
            return 1

    for e in entries:
        payload = (src / e["path"]).read_bytes()
        if e["encrypted"]:
            raw = cipher.decrypt(payload)
        else:
            raw = payload
        if _sha256(raw) != e["plain_sha256"]:
            print(f"[restore] ✗ checksum mismatch: {e['path']}", file=sys.stderr)
            return 2
        target = ROOT / e["source"]
        if target.exists() and not args.dry_run:
            print(f"[restore] ⚠ {target} は既に存在します。スキップ (手動で rm してください)")
            continue
        print(f"[restore] {'DRY ' if args.dry_run else ''}extract → {target}")
        if not args.dry_run:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as t:
                # Security: tar slip 対策
                # Py3.12+ の data filter を優先 (絶対パス / 親参照 / デバイスファイルを拒否)
                # それ以前は手動で member を検証
                root_resolved = ROOT.resolve()
                for m in t.getmembers():
                    # 絶対パス禁止
                    if m.name.startswith("/") or m.name.startswith("\\"):
                        raise RuntimeError(f"[restore] absolute path in tar: {m.name!r}")
                    # デバイス/シンボリックリンクを拒否 (attack surface 縮小)
                    if m.isdev() or m.issym() or m.islnk():
                        raise RuntimeError(f"[restore] disallowed member type in tar: {m.name!r}")
                    # パス正規化後に ROOT 配下に留まるか確認
                    dest = (ROOT / m.name).resolve()
                    try:
                        dest.relative_to(root_resolved)
                    except ValueError as ve:
                        raise RuntimeError(
                            f"[restore] tar slip detected: {m.name!r} escapes {root_resolved}"
                        ) from ve
                # Py3.12+ の filter="data" で二重に防御 (旧版は手動チェック済みなので無視)
                try:
                    t.extractall(path=ROOT, filter="data")  # type: ignore[call-arg]
                except TypeError:
                    t.extractall(path=ROOT)  # nosec B202: members validated above

    print("[restore] 完了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
