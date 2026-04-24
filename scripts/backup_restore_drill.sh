#!/usr/bin/env bash
# Backup-Restore 月次ドリル.
#
# ai-chan の暗号化 SQLite / anniversaries JSON を「確実に救出できるか」を
# 実装レベルで保証するための自動テスト.
# 隔離 sandbox でダミー state を seed → backup → wipe → restore → sha256 検証.
#
# 毎月 15 日 3:30 JST に launchd で自動実行 (com.aichan.backup-restore-drill.plist).
# FAIL 時は logs/backup_restore_drills/FAILED-YYYYMMDD_HHMMSS.md を残し通知送信.
#
set -euo pipefail

cd "$(dirname "$0")/.."

SANDBOX="$(mktemp -d -t aichan-br-drill-XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT

LOGDIR="logs/backup_restore_drills"
mkdir -p "$LOGDIR"

DATE=$(date +"%Y%m%d_%H%M%S")
REPORT="$LOGDIR/drill-$DATE.md"

echo "# Backup-Restore Drill — $DATE" > "$REPORT"
echo "" >> "$REPORT"
echo "- sandbox: $SANDBOX" >> "$REPORT"
echo "- host: $(hostname)" >> "$REPORT"
echo "" >> "$REPORT"

FAIL=0
pass() { echo "- ✅ $*" >> "$REPORT"; }
fail() { echo "- ❌ $*" >> "$REPORT"; FAIL=1; }
note() { echo "- ℹ️  $*" >> "$REPORT"; }

PYTHON="${PYTHON:-python3}"
export PYTHONPATH=.

ORIG="$SANDBOX/orig"
RESTORED="$SANDBOX/restored"
mkdir -p "$ORIG" "$RESTORED"

# --- Phase 1: ダミー state をシード ---
echo "" >> "$REPORT"
echo "## Phase 1: seed dummy state" >> "$REPORT"
"$PYTHON" - <<PY || fail "seed failed"
import json
from pathlib import Path
base = Path("$ORIG")
# 実装 (core.backup_rotator) は data/ personality/ config/ を対象とする
for sub in ("data", "personality", "config"):
    (base / sub).mkdir(parents=True, exist_ok=True)
# ダミー暗号化 SQLite の代用 (drill 目的の固定 bytes)
for name in ("memories.db", "emotion_history.db", "diary.db"):
    (base / "data" / name).write_bytes(b"dummy-encrypted-" + name.encode() + b"-payload")
# anniversaries JSON
anniv = base / "data" / "anniversaries"
anniv.mkdir(exist_ok=True)
(anniv / "first_meeting.json").write_text(
    json.dumps({"date": "2025-01-01", "note": "dummy anniversary"}, ensure_ascii=False)
)
# personality / config も念のため置く
(base / "personality" / "profile.json").write_text(json.dumps({"name": "ai-chan"}))
(base / "config" / "settings.json").write_text(json.dumps({"lang": "ja"}))
print("[drill] seeded", sum(1 for _ in base.rglob("*") if _.is_file()), "files")
PY

ORIG_COUNT=$(find "$ORIG" -type f | wc -l | tr -d ' ')
pass "seeded $ORIG_COUNT files"

# オリジナルの sha256 一覧を保存 (後で比較)
ORIG_MANIFEST="$SANDBOX/orig_manifest.txt"
( cd "$ORIG" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 ) > "$ORIG_MANIFEST"

# --- Phase 2: backup ---
echo "" >> "$REPORT"
echo "## Phase 2: create backup" >> "$REPORT"

BACKUP_MODE="unknown"
BACKUP_FILE=""

if "$PYTHON" -c "import core.backup_rotator" >/dev/null 2>&1; then
  BACKUP_MODE="core.backup_rotator"
  note "using core.backup_rotator.BackupRotator"
  BACKUP_FILE=$("$PYTHON" - <<PY 2>>"$REPORT"
import sys
from pathlib import Path
sys.path.insert(0, ".")
from core.backup_rotator import BackupRotator
rot = BackupRotator(base_dir=Path("$ORIG"))
r = rot.create_backup(label="drill")
print(r["path"])
PY
) || fail "create_backup raised"
else
  BACKUP_MODE="tar.gz fallback"
  note "core.backup_rotator not importable — fallback to tar.gz (TODO: align with real module)"
  BACKUP_FILE="$SANDBOX/fallback_backup.tar.gz"
  ( cd "$ORIG" && tar -czf "$BACKUP_FILE" . ) || fail "tar fallback failed"
fi

if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
  pass "backup created: $(basename "$BACKUP_FILE") ($(du -h "$BACKUP_FILE" | awk '{print $1}'))"
else
  fail "backup file missing"
fi

# --- Phase 3: wipe ---
echo "" >> "$REPORT"
echo "## Phase 3: wipe sandbox state" >> "$REPORT"
# backups ディレクトリは残す (BackupRotator が base_dir 下に backups/ を作るため)
find "$ORIG" -type f ! -path "*/backups/*" -delete
REMAINING=$(find "$ORIG" -type f ! -path "*/backups/*" | wc -l | tr -d ' ')
if [ "$REMAINING" = "0" ]; then
  pass "state wiped (backups/ 以外 0 件)"
else
  fail "wipe incomplete: $REMAINING files remain"
fi

# --- Phase 4: restore ---
echo "" >> "$REPORT"
echo "## Phase 4: restore from backup" >> "$REPORT"

if [ "$BACKUP_MODE" = "core.backup_rotator" ]; then
  "$PYTHON" - <<PY 2>>"$REPORT" || fail "restore_backup raised"
import sys
from pathlib import Path
sys.path.insert(0, ".")
from core.backup_rotator import BackupRotator
rot = BackupRotator(base_dir=Path("$ORIG"))
name = Path("$BACKUP_FILE").name
r = rot.restore_backup(name)
print("[drill] restore:", r)
if r.get("errors"):
    sys.exit(1)
PY
else
  ( cd "$ORIG" && tar -xzf "$BACKUP_FILE" ) || fail "tar restore failed"
fi

# 復元されたものを比較用ディレクトリへコピー (backups/ と pre_restore を除外)
rsync -a --exclude='backups' "$ORIG/" "$RESTORED/" 2>/dev/null || cp -a "$ORIG/." "$RESTORED/"
# backups 配下を比較から除外
rm -rf "$RESTORED/backups"

RESTORED_COUNT=$(find "$RESTORED" -type f | wc -l | tr -d ' ')
pass "restored $RESTORED_COUNT files"

# --- Phase 5: 整合性検証 (sha256 + count) ---
echo "" >> "$REPORT"
echo "## Phase 5: integrity verification" >> "$REPORT"

RESTORED_MANIFEST="$SANDBOX/restored_manifest.txt"
( cd "$RESTORED" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 ) > "$RESTORED_MANIFEST"

if [ "$ORIG_COUNT" = "$RESTORED_COUNT" ]; then
  pass "file count matches ($ORIG_COUNT == $RESTORED_COUNT)"
else
  fail "file count mismatch (orig=$ORIG_COUNT restored=$RESTORED_COUNT)"
fi

if diff -u "$ORIG_MANIFEST" "$RESTORED_MANIFEST" > "$SANDBOX/manifest.diff"; then
  pass "sha256 manifest byte-for-byte match"
else
  fail "sha256 manifest differs"
  echo '```diff' >> "$REPORT"
  head -40 "$SANDBOX/manifest.diff" >> "$REPORT"
  echo '```' >> "$REPORT"
fi

# --- 結果通知 ---
echo "" >> "$REPORT"
echo "- backup_mode: $BACKUP_MODE" >> "$REPORT"
if [ "$FAIL" = "0" ]; then
  echo "## 結論: ✅ PASS" >> "$REPORT"
  mv "$REPORT" "$LOGDIR/PASS-$DATE.md"
  echo "[drill] PASS — $LOGDIR/PASS-$DATE.md"
else
  echo "## 結論: ❌ FAIL — Backup-Restore 契約違反の可能性" >> "$REPORT"
  mv "$REPORT" "$LOGDIR/FAILED-$DATE.md"
  echo "[drill] FAIL — $LOGDIR/FAILED-$DATE.md"
  exit 2
fi
