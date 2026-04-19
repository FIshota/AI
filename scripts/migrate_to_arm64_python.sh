#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Apple Silicon (arm64) ネイティブ Python への移行スクリプト
# 実行: bash scripts/migrate_to_arm64_python.sh
#
# 問題: 現在 x86_64 (Intel) 版 Python 3.9 が Rosetta 経由で動いており
#       cffi / cryptography などバイナリ拡張が arm64 に対応していない。
# 解決: Miniforge (arm64 ネイティブ Conda) で Python 3.11 環境を作成する。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONDA_ENV_NAME="ai_chan"
PYTHON_VERSION="3.11"

echo "========================================"
echo "ai-chan arm64 Python 移行スクリプト"
echo "========================================"
echo ""

# 1. アーキテクチャ確認
ARCH=$(uname -m)
echo "✓ アーキテクチャ: $ARCH"
if [[ "$ARCH" != "arm64" ]]; then
    echo "⚠️  このスクリプトは Apple Silicon (arm64) Mac 専用です"
    exit 1
fi

# 2. Miniforge がインストール済みか確認
if ! command -v conda &>/dev/null; then
    echo ""
    echo "Miniforge をインストールしています..."
    brew install --cask miniforge 2>/dev/null || {
        echo "Homebrew が見つかりません。手動でインストールしてください:"
        echo "  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh"
        exit 1
    }
    eval "$(conda shell.bash hook)"
fi

# 3. conda 環境の作成
echo ""
echo "Python $PYTHON_VERSION の conda 環境 '$CONDA_ENV_NAME' を作成します..."
conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -y

# 4. 環境を有効化して依存インストール
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV_NAME"

echo ""
echo "依存パッケージをインストールしています..."
cd "$REPO_DIR"
pip install -r requirements.txt

# MLX は arm64 ネイティブで利用可能
echo ""
echo "MLX (Apple Silicon 専用) をインストールしています..."
pip install mlx mlx-lm || echo "  ⚠️  MLX インストール失敗（スキップ）"

echo ""
echo "========================================"
echo "✅ 移行完了！"
echo ""
echo "使い方:"
echo "  conda activate $CONDA_ENV_NAME"
echo "  python main.py"
echo ""
echo "または: conda run -n $CONDA_ENV_NAME python main.py"
echo "========================================"
