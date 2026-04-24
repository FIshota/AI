#!/usr/bin/env bash
# Kill-Switch 月次ドリル.
#
# VALUES.md の「消す権利」を実装レベルで保証するための自動テスト.
# 隔離 sandbox でダミー tenant を作成 → purge_subject 実行 → 痕跡ゼロを検証.
#
# 毎月 1 日 3:00 JST に launchd で自動実行 (com.aichan.killswitch-drill.plist).
# FAIL 時は logs/killswitch_drills/FAILED-YYYYMMDD.md を残し通知送信.
#
set -euo pipefail

cd "$(dirname "$0")/.."

SANDBOX="$(mktemp -d -t aichan-ks-drill-XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT

LOGDIR="logs/killswitch_drills"
mkdir -p "$LOGDIR"

DATE=$(date +"%Y%m%d_%H%M%S")
REPORT="$LOGDIR/drill-$DATE.md"

echo "# Kill-Switch Drill — $DATE" > "$REPORT"
echo "" >> "$REPORT"
echo "- sandbox: $SANDBOX" >> "$REPORT"
echo "- host: $(hostname)" >> "$REPORT"
echo "" >> "$REPORT"

FAIL=0
pass() { echo "- ✅ $*" >> "$REPORT"; }
fail() { echo "- ❌ $*" >> "$REPORT"; FAIL=1; }

PYTHON="${PYTHON:-python3}"
export PYTHONPATH=.

# --- Phase 1: ダミーデータ作成 ---
"$PYTHON" -c "
import sys, json
from pathlib import Path
sys.path.insert(0, '.')
sandbox = Path('$SANDBOX')
sandbox.mkdir(parents=True, exist_ok=True)
# 疑似 memory / emotion / diary を配置
for name in ('memories.db', 'emotion_history.db', 'diary.db'):
    (sandbox / name).write_bytes(b'dummy-sensitive-data-' + name.encode())
for d in ('anniversaries', 'logs'):
    sub = sandbox / d
    sub.mkdir()
    (sub / 'sample.json').write_text(json.dumps({'pii':'test@example.com'}))
print('[drill] dummy tenant seeded in', sandbox)
" || fail "dummy seeding failed"

# --- Phase 2: subject_rights purge ---
"$PYTHON" -c "
import sys
sys.path.insert(0, '.')
from pathlib import Path
try:
    from core.subject_rights import SubjectRightsManager
    mgr = SubjectRightsManager(base_dir=Path('$SANDBOX'))
    r = mgr.purge_subject(subject_id='self', dry_run=False)
    print('[drill] purge result:', r)
except Exception as e:
    print('[drill] purge FAILED:', e)
    sys.exit(1)
" 2>&1 | tee -a "$REPORT" >/dev/null || fail "purge_subject raised"

# --- Phase 3: 痕跡ゼロ検証 ---
REMAINING=$(find "$SANDBOX" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$REMAINING" = "0" ]; then
  pass "no residual files after purge"
else
  fail "residual files after purge: $REMAINING"
  find "$SANDBOX" -type f >> "$REPORT"
fi

# --- Phase 4: 起動不可検証 (purge 後に ai-chan が壊れずに "空のまま" 起動するか) ---
"$PYTHON" -c "
import sys
sys.path.insert(0, '.')
# import だけで例外出なければ OK (実行はしない)
import core.subject_rights
import core.memory
print('[drill] import ok')
" >/dev/null 2>&1 && pass "post-purge import sanity" || fail "post-purge imports broken"

# --- 結果通知 ---
echo "" >> "$REPORT"
if [ "$FAIL" = "0" ]; then
  echo "## 結論: ✅ PASS" >> "$REPORT"
  mv "$REPORT" "$LOGDIR/PASS-$DATE.md"
  echo "[drill] PASS — $LOGDIR/PASS-$DATE.md"
else
  echo "## 結論: ❌ FAIL — Kill-Switch 契約違反の可能性" >> "$REPORT"
  mv "$REPORT" "$LOGDIR/FAILED-$DATE.md"
  echo "[drill] FAIL — $LOGDIR/FAILED-$DATE.md"
  exit 2
fi
