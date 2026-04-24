#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# run_weekly_flaky.sh
#
# 週次 launchd から呼ばれる flaky-finder ラッパ。
# run_flaky_finder.sh を実行し、結果を人間可読な Markdown
# サマリとして logs/flaky/weekly-<date>-summary.md に書き出す。
#
# TODO(launchd): launchd/com.aichan.flaky-finder.plist を
#                `launchctl load` することで毎週土曜 04:00 JST
#                に自動実行されるようにする。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

DATE="$(date +%Y-%m-%d)"
TIMESTAMP="$(date +%Y-%m-%dT%H:%M:%S%z)"
LOG_DIR="${PROJECT_ROOT}/logs/flaky"
FINDER_LOG="${LOG_DIR}/${DATE}.txt"
SUMMARY="${LOG_DIR}/weekly-${DATE}-summary.md"

mkdir -p "${LOG_DIR}"

echo "[weekly-flaky] start: ${TIMESTAMP}"
bash "${PROJECT_ROOT}/scripts/run_flaky_finder.sh" || true

# サマリ生成
{
  echo "# ai-chan flaky-finder weekly summary"
  echo ""
  echo "- 日付: ${DATE}"
  echo "- 実行時刻: ${TIMESTAMP}"
  echo "- 詳細ログ: \`logs/flaky/${DATE}.txt\`"
  echo ""
  echo "## 検出結果"
  echo ""
  echo "| テストパス | 状態 |"
  echo "|------------|------|"

  if [[ -f "${FINDER_LOG}" ]]; then
    FAILED_LINES=$(grep -E "^(FAILED|ERROR) " "${FINDER_LOG}" | sort -u || true)
    if [[ -z "${FAILED_LINES}" ]]; then
      echo "| (none) | 全テスト決定的 |"
    else
      while IFS= read -r line; do
        TEST_PATH=$(echo "${line}" | awk '{print $2}')
        STATUS=$(echo "${line}" | awk '{print $1}')
        echo "| \`${TEST_PATH}\` | ${STATUS} |"
      done <<< "${FAILED_LINES}"
    fi
  else
    echo "| (log missing) | flaky-finder ログが生成されませんでした |"
  fi

  echo ""
  echo "## 次のアクション"
  echo ""
  echo "- 上記テストを \`@pytest.mark.flaky\` で隔離（quarantine）"
  echo "- \`logs/flaky/README.md\` の registry に追記"
  echo "- 2週間以内の根本原因修正を TODO 化"
} > "${SUMMARY}"

echo "[weekly-flaky] summary: ${SUMMARY}"
echo "[weekly-flaky] done"
exit 0
