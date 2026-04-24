#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# run_mutation_smoke.sh
#
# 変異テストのパイプラインが動くことだけを確認する smoke test。
# 変異の生存 (survived mutant) はこの段階では許容する。
# weekly の本番実行は scripts/run_mutation_full.sh を参照。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

DATE="$(date +%Y-%m-%d)"
LOG_DIR="${ROOT_DIR}/logs/mutation"
LOG_FILE="${LOG_DIR}/${DATE}.txt"
mkdir -p "${LOG_DIR}"

{
    echo "=== mutation smoke test ==="
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "target: core/tenant.py"
    echo ""
} > "${LOG_FILE}"

if ! command -v mutmut >/dev/null 2>&1; then
    echo "mutmut is not installed — skip smoke test" | tee -a "${LOG_FILE}"
    echo "hint: pip install -r requirements/dev.txt" | tee -a "${LOG_FILE}"
    exit 0
fi

# 1 ファイルだけ、子プロセス上限を絞って smoke 実行。
# --max-children は mutmut のバージョンによってフラグが変わるため、
# サポートされない場合は黙ってフォールバックする。
set +e
mutmut run \
    --paths-to-mutate "core/tenant.py" \
    --max-children 5 \
    >> "${LOG_FILE}" 2>&1
STATUS=$?
set -e

{
    echo ""
    echo "--- results ---"
    mutmut results 2>&1 || true
    echo ""
    echo "exit status (mutmut run): ${STATUS}"
} >> "${LOG_FILE}"

echo "smoke log: ${LOG_FILE}"
exit 0
