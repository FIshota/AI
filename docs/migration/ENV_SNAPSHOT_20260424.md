# ENV SNAPSHOT — 2026-04-24

> PC 移管時に「同じ環境を再構築するために必要な」状態情報を固定記録。
> 秘密環境変数・値は記録しない (PATH / alias 等の非機密セクションのみ)。

---

## ⚠️ MEMORY.md 上の記述との差分 (移管先で要確認)

`~/.claude/projects/.../MEMORY.md` には
> Intel Mac, Py3.9, no MLX, Metal incompatible

と記載されているが、**現在の実機を機械計測した結果は以下のとおりで、記述と食い違う**:

| 項目 | MEMORY.md 記述 | 実機 (2026-04-24 計測) |
|------|-----------------|-------------------------|
| CPU アーキ | Intel (x86_64) | **arm64 (Apple Silicon, T6020 = M2 Pro 系)** |
| Python 既定 | 3.9 | **3.13.2** (3.9 / 3.11 も並存) |
| MLX | 不在 | **mlx 0.31.1 / mlx-metal 0.31.1 / mlx-lm 0.31.2 インストール済** |
| Metal | 非互換 | Apple Silicon なので GPU/Metal 利用可 |

**結論**: 現在の物理機は既に Apple Silicon。移管先がさらに別の Apple Silicon (M3/M4 等) なら MLX / PyTorch MPS をそのまま移植可能。もし Intel Mac に「戻す」場合は MLX を外して `torch` CPU ホイールに切替必要。

---

## 1. OS / ハードウェア

```
$ sw_vers
ProductName:    macOS
ProductVersion: 15.5
BuildVersion:   24F74

$ uname -a
Darwin Apples-MacBook-Pro.local 24.5.0 Darwin Kernel Version 24.5.0:
Tue Apr 22 19:54:25 PDT 2025; root:xnu-11417.121.6~2/RELEASE_ARM64_T6020 arm64

$ arch
arm64

$ sysctl hw.optional.arm64
hw.optional.arm64: 1
```

ホスト名: `Apples-MacBook-Pro.local`
カーネルタグ `T6020` → Apple M2 Pro 相当。

---

## 2. Shell / PATH

```
$ echo $SHELL
/bin/bash
```

### `~/.bash_profile` 非機密セクション
```bash
# Python 3.9 / 3.11 / 3.13 の Framework PATH (順に export)
PATH="/Library/Frameworks/Python.framework/Versions/3.9/bin:${PATH}"
PATH="/Library/Frameworks/Python.framework/Versions/3.11/bin:${PATH}"
PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:${PATH}"

# miniforge3 arm64 conda init (block managed by `conda init`)
# Old x86 Anaconda init は disabled (コメントのみ残存)

# OrbStack
source ~/.orbstack/shell/init.bash 2>/dev/null || :

# $HOME/.local/bin
. "$HOME/.local/bin/env"

# NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
```

### `~/.zshrc` 非機密セクション
```bash
# conda init (zsh, /Users/fujihiranoborudai/opt/anaconda3)
#   ※ 旧 x86 anaconda3 インスタンスが zsh 側に残っている。移管時に整理推奨。
. "$HOME/.local/bin/env"
export PATH=$HOME/bin:$PATH
```

**観測された alias**: 現時点では登録なし。

---

## 3. Python 環境

```
$ python3 --version
Python 3.13.2

$ which python3.9
/Library/Frameworks/Python.framework/Versions/3.9/bin/python3.9
$ which python3.11
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11
$ which python3.13
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13
$ which pip3
/Library/Frameworks/Python.framework/Versions/3.13/bin/pip3
```

- 3.9 / 3.11 / 3.13 が python.org Framework ビルドとして並存
- 既定 `python3` は 3.13 へ解決
- `requirements.txt` のヘッダには `Python 3.10+ (arm64 ネイティブ推奨、Py3.13 対応)` と明記
- **現状は Py3.13 運用**。MEMORY.md の「Py3.9」は古い記述。

### venv
- `ai-chan/venv`, `ai-chan/.venv`: **存在せず** (システム Framework Python に直接 `pip install --user` 運用)
- `hinomoto-model/venv`, `hinomoto-model/.venv`: **存在せず**

### 移管方針
新 PC でも Python 3.13 を `python.org` Framework (arm64) からインストール、もしくは `pyenv install 3.13.2` → `pyenv local 3.13.2`。
可搬性のため移管先では **venv 化を推奨** (`python3.13 -m venv .venv` 各リポジトリで)。

---

## 4. pip freeze (system / user-installed, Python 3.13 側)

計 **181 パッケージ**。主要項目:

### コア AI / LLM
```
llama_cpp_python==0.3.20
torch==2.11.0
transformers==5.5.0
tokenizers==0.22.2
huggingface_hub==1.9.0
safetensors==0.7.0
sentence-transformers==5.3.0
sentencepiece==0.2.1
```

### MLX (Apple Silicon 専用) — **インストール済み**
```
mlx==0.31.1
mlx-lm==0.31.2
mlx-metal==0.31.1
```
※ MEMORY.md の「no MLX」と不一致。

### 音声
```
faster-whisper==1.2.1
edge-tts==7.2.8
vosk==0.3.44
sounddevice==0.5.5
soundfile==0.13.1
librosa==0.11.0
ctranslate2==4.7.1
```

### ベクトル検索
```
faiss-cpu==1.13.2
```

### 暗号 / セキュリティ
```
cryptography==46.0.5
bandit==1.9.4
pip_audit==2.10.0
cyclonedx-python-lib==11.7.0
```

### データ処理
```
numpy==2.4.4
pandas==3.0.2
scipy==1.17.1
scikit-learn==1.8.0
scikit-image==0.26.0
pyarrow==23.0.1
```

### Web フレームワーク
```
Flask==3.1.0
Flask-SocketIO==5.5.1
fastapi==0.135.3
starlette==1.0.0
uvicorn==0.44.0
```

### 開発ツール
```
pytest==9.0.3
pytest-cov==7.1.0
coverage==7.13.5
ruff==0.15.11
mypy==1.20.1
hypothesis==6.152.1
build==1.4.3
pip-tools==7.5.3
```

**全 181 パッケージの完全リストは `requirements.lock` (ai-chan)** を正本とする。
復元時は:
```
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # 通常運用
# もしくは
pip install -r requirements.lock        # 完全再現
```

---

## 5. Homebrew

```
$ brew list --versions
/bin/bash: brew: command not found

$ brew services list
/bin/bash: brew: command not found
```

**Homebrew はインストールされていない**。
代わりに:
- Python: `python.org` Framework インストーラ
- Conda: `miniforge3` (arm64) と `anaconda3` (旧 x86, zsh 側に init 残存)
- Node: `nvm`
- Docker 相当: `OrbStack`

### 移管時の注意
- Homebrew に依存するスクリプトは現状無し (grep で未確認)
- 新 PC でも brew 必須ではないが、利便性で導入する場合は `/opt/homebrew` (arm64) 側へ

---

## 6. launchctl (プロジェクト関連のみ)

```
$ launchctl list | grep -i -E "(claude|ai-chan|hinomoto|aichan)"
-    0   com.aichan.security-weekly
-    0   com.anthropic.claudefordesktop.ShipIt
82968 0  application.com.anthropic.claudefordesktop.99785718.99785724
-    0   com.aichan.security-audit
```

- `com.aichan.security-audit`: 毎朝 09:00 JST, `~/Library/LaunchAgents/com.aichan.security-audit.plist`
- `com.aichan.security-weekly`: 月曜 08:30 JST, `~/Library/LaunchAgents/com.aichan.security-weekly.plist`

リポジトリ内にさらに未 load の plist テンプレート多数 (`ai-chan/launchd/`, `hinomoto-model/launchd/`)。
詳細は `SCHEDULED_TASKS_EXPORT_20260424.md` を参照。

---

## 7. Node.js

```
$ node --version
v22.22.1
$ npm --version
10.9.4
```

`nvm` 管理。`$NVM_DIR=$HOME/.nvm`。
**ai-chan / hinomoto は現状 Python 主体で Node 依存は最小** (`web/` 配下の UI 補助のみ)。

---

## 8. Xcode Command Line Tools

```
$ xcode-select -p
/Library/Developer/CommandLineTools
```

Xcode 本体ではなく **Command Line Tools 単体**インストール。
移管先でも `xcode-select --install` で十分。

---

## 9. その他ツール

| ツール | 状態 | 用途 |
|--------|------|------|
| gpg | **未インストール** | コミット署名未使用 |
| brew | **未インストール** | — |
| conda (miniforge3 arm64) | インストール済 | Python 環境の代替 |
| conda (anaconda3 x86) | zsh 側に init 残存 | **不要、移管時に整理推奨** |
| OrbStack | インストール済 | Docker 代替 |
| nvm | インストール済 | Node.js 管理 |

---

## 移管先 (新 PC) 再現手順 (概略)

1. macOS 15.5 相当以上、arm64 推奨
2. `xcode-select --install`
3. Python 3.13.2 を python.org Framework からインストール、もしくは pyenv
4. `pip install --upgrade pip`
5. 各リポジトリで venv 化: `python3.13 -m venv .venv && pip install -r requirements.txt`
6. MLX は arm64 のみ有効 — x86_64 移管先なら `pip uninstall mlx mlx-lm mlx-metal`
7. nvm: `curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash` → `nvm install 22.22.1`
8. LaunchAgents: `cp <plist> ~/Library/LaunchAgents/ && launchctl load <plist>`
9. conda 旧 x86 init は `.zshrc` から除去推奨

詳細チェックリストは `MIGRATION_CHECKLIST.md` を参照。
