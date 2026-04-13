#!/bin/bash
# アイ インストールスクリプト（Mac/Linux）
set -e

echo "================================================"
echo "  アイ セットアップ (Phase 1)"
echo "================================================"

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# Python 確認
python3 --version || { echo "Python 3 が必要です"; exit 1; }

# 仮想環境の作成
if [ ! -d ".venv" ]; then
    echo "→ 仮想環境を作成しています..."
    python3 -m venv .venv
fi

# 仮想環境を有効化
source .venv/bin/activate

# pip アップグレード
pip install --upgrade pip --quiet

# 基本依存パッケージのインストール
echo "→ 依存パッケージをインストールしています..."
pip install cryptography rich click pydantic python-dateutil --quiet

# llama-cpp-python (Apple Silicon Metal対応)
echo "→ llama-cpp-python (Metal GPU対応) をインストールしています..."
pip install llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/metal \
    || pip install llama-cpp-python  # フォールバック

echo ""
echo "✓ インストール完了！"
echo ""
echo "次のステップ:"
echo "  1. source .venv/bin/activate"
echo "  2. python scripts/setup_model.py  (モデルをダウンロード)"
echo "  3. python main.py                 (アイを起動)"
