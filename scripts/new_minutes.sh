#!/usr/bin/env bash
# new_minutes.sh — 議事録ファイルをテンプレートから生成する
#
# 使い方:
#   scripts/new_minutes.sh <slug>
#   scripts/new_minutes.sh <slug> <YYYY-MM-DD>
#
# 例:
#   scripts/new_minutes.sh model-upgrade
#     -> docs/minutes/2026-04-23-model-upgrade.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MINUTES_DIR="${REPO_ROOT}/docs/minutes"
TEMPLATE="${MINUTES_DIR}/TEMPLATE.md"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $(basename "$0") <slug> [YYYY-MM-DD]" >&2
  exit 1
fi

SLUG="$1"
DATE="${2:-$(date +%Y-%m-%d)}"

# slug バリデーション: 英数 / ハイフン / アンダースコアのみ
if ! [[ "${SLUG}" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "error: slug には英数字・ハイフン・アンダースコアのみ使用できます: ${SLUG}" >&2
  exit 1
fi

# date バリデーション: YYYY-MM-DD
if ! [[ "${DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "error: date は YYYY-MM-DD 形式で指定してください: ${DATE}" >&2
  exit 1
fi

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "error: テンプレートが見つかりません: ${TEMPLATE}" >&2
  exit 1
fi

OUT="${MINUTES_DIR}/${DATE}-${SLUG}.md"

if [[ -e "${OUT}" ]]; then
  echo "error: 既に存在します: ${OUT}" >&2
  exit 1
fi

mkdir -p "${MINUTES_DIR}"

# テンプレートの日付プレースホルダを置換してコピー
# macOS / Linux 双方で動くよう sed は -i を使わず中間ファイル経由で書き出す
TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT
sed "s/^YYYY-MM-DD$/${DATE}/" "${TEMPLATE}" > "${TMP}"
cp "${TMP}" "${OUT}"

echo "${OUT}"
