#!/usr/bin/env bash
# ai-chan 記憶切り離し Phase B — 本体から物理削除 (破壊的).
#
# 前提:
#   - Phase A (非破壊アーカイブ) が両方の場所に成功していること
#   - SSD が /Volumes/backup にマウントされていること
#   - manifest.json が両方で一致していること
#
# 本スクリプトは dry-run がデフォルト。--apply を渡して初めて削除する。

set -euo pipefail

ROOT="/Users/fujihiranoborudai/Downloads/agent/ai-chan"
STAMP=$(date -u +%Y-%m-%d-phase0-detach)
LOCAL="$HOME/ai-chan-archive/$STAMP"
SSD="/Volumes/backup/ai-chan-archive/$STAMP"

APPLY=0
for arg in "$@"; do
  [ "$arg" = "--apply" ] && APPLY=1
done

TARGETS=(data logs personality yamato_dna models output reports backups)

# === 安全チェック ===
echo "[phase-b] 事前検証 ..."
[ -f "$LOCAL/manifest.json" ]  || { echo "✗ local manifest not found: $LOCAL/manifest.json"; exit 1; }
[ -f "$SSD/manifest.json" ]    || { echo "✗ ssd   manifest not found: $SSD/manifest.json"; exit 1; }
diff -q "$LOCAL/manifest.json" "$SSD/manifest.json" >/dev/null \
  || { echo "✗ manifest mismatch between local and SSD"; exit 1; }
[ -f "$LOCAL/keys/transport.key" ] || { echo "✗ local transport.key missing"; exit 1; }
[ -f "$SSD/keys/transport.key" ]   || { echo "✗ ssd transport.key missing"; exit 1; }
echo "  ✓ manifest 両方一致"
echo "  ✓ transport.key 両方存在"

# アーカイブから復元できるかを 1 件テスト (data.tar.gz.enc)
echo "[phase-b] data.tar.gz.enc 復号テスト ..."
python3 - "$LOCAL" <<'PY'
import sys, io, tarfile
from pathlib import Path
from cryptography.fernet import Fernet
base = Path(sys.argv[1])
k = Fernet((base / "keys/transport.key").read_bytes())
enc = (base / "data.tar.gz.enc").read_bytes()
raw = k.decrypt(enc)
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as t:
    names = t.getnames()
print(f"  ✓ data.tar.gz.enc: {len(names)} entries, first={names[:3]}")
PY

cd "$ROOT"

echo ""
echo "=== Phase B 対象 ==="
for t in "${TARGETS[@]}"; do
  if [ -e "$t" ]; then
    size=$(du -sh "$t" 2>/dev/null | awk '{print $1}')
    echo "  - $t  ($size)"
  fi
done
echo ""

if [ $APPLY -eq 0 ]; then
  echo "--- DRY RUN --- (--apply で実削除)"
  for t in "${TARGETS[@]}"; do
    [ -e "$t" ] && echo "  would rm -rf $t"
  done
  exit 0
fi

echo "!!! 実削除モード !!!"
echo "5 秒後に削除を開始します... (Ctrl-C でキャンセル)"
sleep 5

for t in "${TARGETS[@]}"; do
  if [ -e "$t" ]; then
    echo "[phase-b] rm -rf $t"
    rm -rf "$t"
  fi
done

# config/settings.json も本体から消す (既に .example に置換済だが念のため)
if [ -f "config/settings.json" ]; then
  echo "[phase-b] rm config/settings.json"
  rm -f config/settings.json
fi

echo ""
echo "[phase-b] 完了. 本体は記憶を持たない状態になりました."
echo "         起動テスト: python3 main.py --smoke-test"
echo "         復元テスト: python3 scripts/restore_memory.py --from $LOCAL"
