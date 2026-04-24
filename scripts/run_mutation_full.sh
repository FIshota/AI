#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# run_mutation_full.sh
#
# .mutmut.toml の paths_to_mutate 全件に対して mutmut を実行する。
# 実行時間が長いため、weekly (launchd / cron) での起動を想定。
#
# 使い方:
#   bash scripts/run_mutation_full.sh
#
# 将来的には launchd 登録の案:
#   ~/Library/LaunchAgents/com.aichan.mutation.weekly.plist
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

DATE="$(date +%Y-%m-%d)"
LOG_DIR="${ROOT_DIR}/logs/mutation"
LOG_FILE="${LOG_DIR}/full-${DATE}.txt"
mkdir -p "${LOG_DIR}"

{
    echo "=== mutation full run ==="
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "config: .mutmut.toml"
    echo ""
} > "${LOG_FILE}"

if ! command -v mutmut >/dev/null 2>&1; then
    echo "mutmut is not installed — abort full run" | tee -a "${LOG_FILE}"
    echo "hint: pip install -r requirements/dev.txt" | tee -a "${LOG_FILE}"
    exit 0
fi

set +e
mutmut run >> "${LOG_FILE}" 2>&1
STATUS=$?
set -e

{
    echo ""
    echo "--- full results ---"
    mutmut results 2>&1 || true
    echo ""
    echo "exit status (mutmut run): ${STATUS}"
} >> "${LOG_FILE}"

echo "full log: ${LOG_FILE}"
exit 0
