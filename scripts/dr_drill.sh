#!/usr/bin/env bash
# Disaster Recovery 四半期ドリル.
#
# docs/ops/DR_RUNBOOK.md のシナリオ 2 (SQLite DB 破損) と
# シナリオ 3 (launchd ジョブ暴走) を sandbox で自動再現 → 復旧を検証する.
# その他のシナリオ (1, 4, 5, 6, 7, 8) は echo TODO のスケルトンのみ.
#
# 1 / 4 / 7 / 10 月 1 日 04:00 JST に launchd で自動実行
# (launchd/com.aichan.dr-drill.plist).
#
# 出力: logs/dr/drill-YYYYMMDD_HHMMSS.md
#
set -euo pipefail

cd "$(dirname "$0")/.."

SANDBOX="$(mktemp -d -t aichan-dr-drill-XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT

LOGDIR="logs/dr"
mkdir -p "$LOGDIR"

DATE=$(date +"%Y%m%d_%H%M%S")
REPORT="$LOGDIR/drill-$DATE.md"

FAIL=0

log()  { echo "$*" | tee -a "$REPORT"; }
pass() { log "- PASS: $*"; }
fail() { log "- FAIL: $*"; FAIL=1; }
note() { log "- NOTE: $*"; }
section() { log ""; log "## $*"; log ""; }

log "# DR Drill — $DATE"
log ""
log "- sandbox: \`$SANDBOX\`"
log "- host: \`$(hostname)\`"
log "- runbook: docs/ops/DR_RUNBOOK.md"
log ""

############################
# シナリオ 2: SQLite DB 破損
############################
drill_scenario_2_sqlite_corruption() {
  section "Scenario 2 — SQLite DB corruption & recovery"

  local work="$SANDBOX/s2"
  mkdir -p "$work"
  local db="$work/memory.db"

  # seed
  if ! sqlite3 "$db" "CREATE TABLE memories(id INTEGER PRIMARY KEY, content TEXT);
                      INSERT INTO memories(content) VALUES('hello'),('world'),('ai-chan');"; then
    fail "seed db failed"
    return
  fi
  pass "seed db created (3 rows)"

  # integrity baseline
  if [[ "$(sqlite3 "$db" 'PRAGMA integrity_check;')" != "ok" ]]; then
    fail "baseline integrity_check not ok"
    return
  fi
  pass "baseline integrity_check ok"

  # backup (健全スナップショット)
  cp "$db" "$work/memory.db.bak"
  pass "healthy backup created"

  # 破損注入: ファイル中央をゼロ埋め
  local size
  size=$(wc -c < "$db" | tr -d ' ')
  if [[ "$size" -lt 2048 ]]; then
    note "db too small to corrupt deterministically, padding"
    dd if=/dev/urandom of="$db" bs=1024 count=4 conv=notrunc >/dev/null 2>&1 || true
    size=$(wc -c < "$db" | tr -d ' ')
  fi
  local mid=$(( size / 2 ))
  dd if=/dev/zero of="$db" bs=1 seek="$mid" count=512 conv=notrunc >/dev/null 2>&1 || true
  pass "corruption injected at offset $mid"

  # 破損確認
  if sqlite3 "$db" "PRAGMA integrity_check;" 2>/dev/null | grep -q "^ok$"; then
    note "integrity_check still ok — corruption not severe enough (non-fatal)"
  else
    pass "integrity_check now reports corruption"
  fi

  # .recover 試行
  local recovered_sql="$work/recovered.sql"
  sqlite3 "$db" ".recover" > "$recovered_sql" 2>/dev/null || true
  if [[ -s "$recovered_sql" ]]; then
    pass ".recover produced SQL dump ($(wc -l < "$recovered_sql") lines)"
  else
    note ".recover produced empty output"
  fi

  # バックアップからの復元
  cp "$work/memory.db.bak" "$db"
  if [[ "$(sqlite3 "$db" 'PRAGMA integrity_check;')" == "ok" ]]; then
    pass "restore from backup succeeded (integrity_check ok)"
  else
    fail "restore from backup failed"
  fi

  # 行数検証
  local rows
  rows=$(sqlite3 "$db" "SELECT COUNT(*) FROM memories;")
  if [[ "$rows" == "3" ]]; then
    pass "row count preserved (3)"
  else
    fail "row count mismatch: expected 3 got $rows"
  fi
}

############################
# シナリオ 3: launchd 暴走
############################
drill_scenario_3_launchd_runaway() {
  section "Scenario 3 — launchd runaway detection & quarantine"

  local work="$SANDBOX/s3"
  mkdir -p "$work" "$work/logs"

  # 擬似暴走: 即死するスクリプトを繰り返し起動するループを bash で擬似再現
  #   (実際の launchd を触ると本番に影響するため、挙動を模する)
  local victim="$work/victim.sh"
  cat > "$victim" <<'EOF'
#!/usr/bin/env bash
echo "[$(date +%s)] runaway start" >> "$LOG"
exit 1
EOF
  chmod +x "$victim"

  local log="$work/logs/runaway.err"
  LOG="$log"
  export LOG

  # 10 回の即死リスタートを模倣
  local i
  for i in $(seq 1 10); do
    "$victim" || true
  done

  local lines
  lines=$(wc -l < "$log" | tr -d ' ')
  if [[ "$lines" -ge 10 ]]; then
    pass "simulated runaway produced $lines log lines"
  else
    fail "expected >=10 lines got $lines"
  fi

  # ログ退避動作確認
  local stamp
  stamp=$(date +%Y%m%d_%H%M%S)
  local quarantine="$work/logs/runaway-$stamp"
  mkdir -p "$quarantine"
  find "$work/logs" -maxdepth 1 -type f -name '*.err' -exec mv {} "$quarantine/" \;

  if [[ -f "$quarantine/runaway.err" ]]; then
    pass "log quarantine moved *.err to $(basename "$quarantine")"
  else
    fail "log quarantine failed"
  fi

  # 末尾採取の動作確認
  local tail_bytes
  tail_bytes=$(tail -200 "$quarantine/runaway.err" | wc -c | tr -d ' ')
  if [[ "$tail_bytes" -gt 0 ]]; then
    pass "tail inspection succeeded ($tail_bytes bytes)"
  else
    fail "tail inspection empty"
  fi

  note "real launchctl unload/load is not performed in drill (production safety)"
}

############################
# 未実装シナリオ (TODO)
############################
drill_scenario_1_machine_loss()      { section "Scenario 1 — dev machine loss";         echo "TODO: manual procedure, see DR_RUNBOOK.md §1"      | tee -a "$REPORT"; }
drill_scenario_4_keychain_loss()     { section "Scenario 4 — keychain loss";             echo "TODO: manual procedure, see DR_RUNBOOK.md §4"      | tee -a "$REPORT"; }
drill_scenario_5_backup_corruption() { section "Scenario 5 — backup corruption";         echo "TODO: manual procedure, see DR_RUNBOOK.md §5"      | tee -a "$REPORT"; }
drill_scenario_6_process_hang()      { section "Scenario 6 — process hang / OOM";        echo "TODO: manual procedure, see DR_RUNBOOK.md §6"      | tee -a "$REPORT"; }
drill_scenario_7_purge_regret()      { section "Scenario 7 — purge regret";              echo "TODO: manual procedure, see DR_RUNBOOK.md §7"      | tee -a "$REPORT"; }
drill_scenario_8_takedown()          { section "Scenario 8 — takedown request";          echo "TODO: manual procedure, see DR_RUNBOOK.md §8"      | tee -a "$REPORT"; }

############################
# main
############################
main() {
  drill_scenario_1_machine_loss
  drill_scenario_2_sqlite_corruption
  drill_scenario_3_launchd_runaway
  drill_scenario_4_keychain_loss
  drill_scenario_5_backup_corruption
  drill_scenario_6_process_hang
  drill_scenario_7_purge_regret
  drill_scenario_8_takedown

  section "Summary"
  if [[ "$FAIL" -eq 0 ]]; then
    log "- Result: PASS"
  else
    log "- Result: FAIL"
    mv "$REPORT" "$LOGDIR/FAILED-drill-$DATE.md"
    REPORT="$LOGDIR/FAILED-drill-$DATE.md"
  fi
  log ""
  log "Report: $REPORT"

  return "$FAIL"
}

main "$@"
