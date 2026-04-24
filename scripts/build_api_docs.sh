#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# build_api_docs.sh
#
# ai-chan の内部 API リファレンス (HTML) を pdoc で自動生成する。
# 対象パッケージ: core / utils / ui
# 出力先       : docs/api/
#
# 生成物 (*.html) は .gitignore 済み。必要に応じて個別再生成する。
# 月次再生成は launchd/com.aichan.api-docs.plist から呼ばれる想定。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

# スクリプト位置からプロジェクトルートを解決
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/docs/api"

cd "${PROJECT_ROOT}"

# pdoc 存在チェック（未インストールなら案内して exit 1）
if ! python3 -c "import pdoc" >/dev/null 2>&1; then
  echo "[build_api_docs] pdoc がインストールされていません。" >&2
  echo "[build_api_docs] 次のコマンドでインストールしてください:" >&2
  echo "    pip install pdoc" >&2
  echo "  もしくは requirements/dev.txt 経由:" >&2
  echo "    pip install -r requirements/dev.txt" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

echo "[build_api_docs] pdoc で API リファレンスを生成中..."
echo "[build_api_docs] output: ${OUTPUT_DIR}"

# core / utils / ui を対象に HTML 生成
python3 -m pdoc \
  --output-directory "${OUTPUT_DIR}" \
  core utils ui

HTML_COUNT=$(find "${OUTPUT_DIR}" -name "*.html" -type f | wc -l | tr -d ' ')
echo "[build_api_docs] done. html files = ${HTML_COUNT}"
