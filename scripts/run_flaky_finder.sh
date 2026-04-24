#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# run_flaky_finder.sh
#
# pytest-flakefinder を使用して、テストを同一セッション内で
# 複数回繰り返し実行し、非決定的なテスト（flaky）を検出する。
#
# 使い方:
#   bash scripts/run_flaky_finder.sh
#
# 出力:
#   logs/flaky/<YYYY-MM-DD>.txt       テキストログ
#
# 注意:
#   - 診断ツールであり、失敗しても CI ブロッカーにはしない (exit 0)。
#   - @pytest.mark.flaky が付与されたテストは `-m "not flaky"` で除外する
#     （quarantine 済み）。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

DATE="$(date +%Y-%m-%d)"
TIMESTAMP="$(date +%Y-%m-%dT%H:%M:%S%z)"
LOG_DIR="${PROJECT_ROOT}/logs/flaky"
LOG_FILE="${LOG_DIR}/${DATE}.txt"

mkdir -p "${LOG_DIR}"

echo "[flaky-finder] start: ${TIMESTAMP}"
echo "[flaky-finder] log:   ${LOG_FILE}"

# pytest-flakefinder の存在確認
if ! python -c "import flakefinder" >/dev/null 2>&1; then
  MSG="[flaky-finder] pytest-flakefinder が未インストールです。pip install pytest-flakefinder を実行してください。"
  echo "${MSG}" | tee "${LOG_FILE}"
  echo "[flaky-finder] スキップ (exit 0)"
  exit 0
fi

FLAKE_RUNS="${FLAKE_RUNS:-10}"

echo "[flaky-finder] runs per test: ${FLAKE_RUNS}"
echo "[flaky-finder] command: pytest --flake-finder --flake-runs=${FLAKE_RUNS} -q -x -m 'not flaky' tests/"

{
  echo "# ai-chan flaky-finder log"
  echo "# generated: ${TIMESTAMP}"
  echo "# flake-runs: ${FLAKE_RUNS}"
  echo "# command: pytest --flake-finder --flake-runs=${FLAKE_RUNS} -q -x -m 'not flaky' tests/"
  echo ""
} > "${LOG_FILE}"

set +e
pytest \
  --flake-finder \
  --flake-runs="${FLAKE_RUNS}" \
  -q \
  -x \
  -m "not flaky" \
  tests/ \
  >> "${LOG_FILE}" 2>&1
PYTEST_EXIT=$?
set -e

echo "" >> "${LOG_FILE}"
echo "# pytest exit code: ${PYTEST_EXIT}" >> "${LOG_FILE}"

# サマリ抽出 — FAILED 行を stdout に出す
echo ""
echo "[flaky-finder] ===== summary ====="
if grep -E "^(FAILED|ERROR) " "${LOG_FILE}" | sort -u; then
  :
else
  echo "[flaky-finder] 非決定的なテストは検出されませんでした。"
fi
echo "[flaky-finder] ===== end ====="
echo "[flaky-finder] full log: ${LOG_FILE}"

# 診断用途なので常に exit 0
exit 0
