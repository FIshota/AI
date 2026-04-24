#!/usr/bin/env bash
# ------------------------------------------------------------------
# docker_build_and_hash.sh
#
# 目的:
#   ai-chan の Docker image を build し、その内容 (tar stream) の
#   sha256 を取って logs/docker_image_hashes/ に保存する。
#   10 年後に「当時の image と一致するか」を検証できるようにするための
#   証拠保全スクリプト。
#
# 前提:
#   docker daemon が利用可能であること。無い環境でも構文エラーで
#   落ちないよう、依存は全て実行時 (runtime) に委ねる。
#
# 使い方:
#   bash scripts/docker_build_and_hash.sh
# ------------------------------------------------------------------
set -euo pipefail

# --- リポジトリルートに移動 ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# --- 必須コマンド確認 (無ければ早期 exit) ---
if ! command -v docker >/dev/null 2>&1; then
    echo "[docker_build_and_hash] docker コマンドが見つかりません。skip します。" >&2
    exit 0
fi

if ! docker info >/dev/null 2>&1; then
    echo "[docker_build_and_hash] docker daemon に接続できません。skip します。" >&2
    exit 0
fi

# --- タグ生成 (git short sha。git が無い/非 repo の場合は 'nogit') ---
if command -v git >/dev/null 2>&1 && git rev-parse --short HEAD >/dev/null 2>&1; then
    SHA="$(git rev-parse --short HEAD)"
else
    SHA="nogit"
fi

IMAGE_TAG="aichan:${SHA}"
DATE="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${REPO_ROOT}/logs/docker_image_hashes"
OUT_FILE="${OUT_DIR}/${DATE}-${SHA}.txt"

mkdir -p "${OUT_DIR}"

# --- sha256sum の互換ラッパ (macOS には標準で無いので shasum 使用) ---
if command -v sha256sum >/dev/null 2>&1; then
    SHA256_CMD="sha256sum"
else
    SHA256_CMD="shasum -a 256"
fi

echo "[docker_build_and_hash] building ${IMAGE_TAG}"
docker build -t "${IMAGE_TAG}" .

echo "[docker_build_and_hash] hashing image tarball"
# docker save は大きいので pipe で直接ハッシュ
HASH_LINE="$(docker save "${IMAGE_TAG}" | ${SHA256_CMD})"

{
    echo "image_tag: ${IMAGE_TAG}"
    echo "build_date_utc: ${DATE}"
    echo "git_sha: ${SHA}"
    echo "sha256: ${HASH_LINE%% *}"
    echo "host_uname: $(uname -a)"
} > "${OUT_FILE}"

echo "[docker_build_and_hash] wrote ${OUT_FILE}"
cat "${OUT_FILE}"
