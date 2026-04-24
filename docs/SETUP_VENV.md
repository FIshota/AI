# venv セットアップガイド (ai-chan)

**作成日**: 2026-04-24
**対象**: 移管先 Apple Silicon Mac でのクリーンセットアップ

## 現状（移管元: Intel Mac）

- システム Python 3.13 を直接使用
- venv なし（`python3` 直呼び出し）
- `pip install` はユーザー領域 (`~/Library/Python/3.13/`) or システム領域
- MLX 関連依存は **未インストール**（Intel なので Metal 非対応）

この運用は移管先（Apple Silicon）では以下の理由で不適切:

1. Apple Silicon で MLX を入れる場合、システム汚染を避けたい
2. 複数プロジェクト（ai-chan, hinomoto-model）で依存が衝突する可能性
3. 再現性が低い（requirements.txt ロックが活きない）

## 推奨手順（移管先）

### 1. Python 3.13 確保

以下いずれかを選択:

**A. pyenv (推奨)**
```bash
brew install pyenv
pyenv install 3.13.1
pyenv local 3.13.1  # プロジェクト固定
```

**B. brew**
```bash
brew install python@3.13
# /opt/homebrew/bin/python3.13 を使用
```

**C. python.org 公式インストーラ**
- <https://www.python.org/downloads/macos/> から universal2 版を取得
- Framework が `/Library/Frameworks/Python.framework/Versions/3.13/` に配置

### 2. venv 作成

```bash
cd /path/to/ai-chan
python3.13 -m venv .venv
source .venv/bin/activate

# 確認
which python  # → .../ai-chan/.venv/bin/python
python --version  # → Python 3.13.x
```

### 3. 依存インストール

```bash
pip install --upgrade pip
pip install -r requirements.txt

# 開発依存がある場合
pip install -r requirements-dev.txt
```

### 4. .venv を gitignore

`.gitignore` に以下が無ければ追加:
```
.venv/
```

### 5. 有効化の自動化（任意）

`direnv` を使う場合:
```bash
brew install direnv
echo 'layout python python3.13' > .envrc
direnv allow
```

## MLX 依存の扱い

Apple Silicon 移管後、以下を **venv 内に** 入れるか判断:

| パッケージ | venv 内 | システム |
|-----------|---------|----------|
| `mlx` | ○（プロジェクト依存） | × |
| `mlx-lm` | ○ | × |
| `mlx-metal` | ○ | × |

**判断基準**:
- **venv 内を推奨**: ai-chan 専用の MLX ビルドを使う、バージョン固定したい、他プロジェクトと分離したい
- **システム側**: 複数プロジェクトで共通の MLX を使い、プロジェクト間で同一バージョンを強制したい

**迷ったら venv 内**（隔離優先）。

## 検証

```bash
source .venv/bin/activate
python -c "import sys; print(sys.prefix)"  # .venv パスが出ること
python -c "import mlx.core as mx; print(mx.default_device())"  # Metal が出ること（MLX 導入時）
pytest  # テストが通ること
```

## トラブルシュート

- `ModuleNotFoundError` → venv が activate されていない
- `mlx` が import できない → Intel バイナリが混入。`pip uninstall mlx && pip install mlx` を universal2 Python で
- `requirements.txt` が無い → プロジェクトルートで `pip freeze > requirements.txt` を移管前に生成
