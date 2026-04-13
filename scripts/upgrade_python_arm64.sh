#!/bin/bash
# ===================================================================
# Python環境をarm64ネイティブに切り替えるスクリプト
# ===================================================================
#
# 現状の問題:
#   x86版Anaconda Python 3.9 を Rosetta 2 で実行中
#   → llama-cpp-python の Metal (GPU) が使えない
#   → MLX も使えない（Apple Silicon専用）
#   → LLMがフォールバックモードで動作
#
# このスクリプトで解決すること:
#   1. Miniforge (arm64) をインストール
#   2. ai-chan用のconda環境を作成
#   3. 必要なパッケージをインストール
#   4. MLX + llama-cpp-python (Metal対応) が使える状態に
#
# 使い方:
#   bash scripts/upgrade_python_arm64.sh
#
# ===================================================================

set -e

echo "🔍 現在の環境を確認..."
echo "  CPU: $(sysctl -n machdep.cpu.brand_string)"
echo "  OS arch: $(uname -m)"
echo "  Python: $(python --version 2>&1)"
echo "  Python arch: $(python -c 'import platform; print(platform.machine())')"
echo ""

# Apple Silicon チェック
if [ "$(uname -m)" != "arm64" ]; then
    echo "❌ このスクリプトはApple Silicon (M1/M2/M3) Mac用です。"
    exit 1
fi

MINIFORGE_DIR="$HOME/miniforge3"

if [ -d "$MINIFORGE_DIR" ]; then
    echo "✅ Miniforge は既にインストール済み: $MINIFORGE_DIR"
else
    echo "📦 Miniforge (arm64) をダウンロード・インストール..."
    curl -L -o /tmp/Miniforge3.sh \
        "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh"
    bash /tmp/Miniforge3.sh -b -p "$MINIFORGE_DIR"
    rm /tmp/Miniforge3.sh
    echo "✅ Miniforge インストール完了"
fi

# conda を有効化
eval "$($MINIFORGE_DIR/bin/conda shell.bash hook)"

echo ""
echo "🐍 ai-chan 環境を作成..."
if conda env list | grep -q "ai-chan"; then
    echo "  既存の ai-chan 環境を検出。アップデートします。"
    conda activate ai-chan
else
    conda create -n ai-chan python=3.11 -y
    conda activate ai-chan
fi

echo ""
echo "📦 パッケージをインストール..."

# 基本依存
pip install -r "$(dirname "$0")/../requirements.txt"

# MLX (Apple Silicon ネイティブ)
pip install mlx mlx-lm

# llama-cpp-python (Metal対応)
pip install llama-cpp-python

echo ""
echo "✅ セットアップ完了！"
echo ""
echo "使い方:"
echo "  conda activate ai-chan"
echo "  cd $(dirname "$0")/.."
echo "  python main.py"
echo ""
echo "確認:"
python -c "
import platform
print(f'  Python arch: {platform.machine()}')
try:
    from mlx_lm import load
    print('  MLX: ✅ 利用可能')
except ImportError:
    print('  MLX: ❌ 利用不可')
try:
    from llama_cpp import Llama
    print('  llama-cpp: ✅ 利用可能')
except Exception:
    print('  llama-cpp: ❌ 利用不可')
"
