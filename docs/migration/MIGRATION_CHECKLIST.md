# MIGRATION CHECKLIST — 新 PC 移管手順

> 移管当日に旧 → 新 PC で実行するチェックリスト。
> 各項目に ✓ とフォールバック手順を併記。

**対象リポジトリ**:
- `ai-chan` (`/Users/fujihiranoborudai/Downloads/agent/ai-chan`)
- `hinomoto-model` (`/Users/fujihiranoborudai/Downloads/agent/hinomoto-model`)

**前提**: 旧 PC = arm64 Apple Silicon / macOS 15.5 / Python 3.13.2 (詳細 `ENV_SNAPSHOT_20260424.md`)

---

## 📋 実行済みサマリ (2026-04-24 時点)

| 項目 | ステータス | 出力先 |
|---|---|---|
| Git checkpoint commit + tag | ✅ 完了 | tag `pre-migration-20260424` (両 repo, push 済) |
| Python env snapshot | ✅ 完了 | `docs/migration/env_20260424/` |
| Logs/config/data tarball | ✅ 完了 | `docs/migration/backups_20260424/` |
| Sensitive config 0600 化 | ✅ 完了 | persona/access_control/voice_auth_challenges |
| pip cache purge (1.5GB) | ✅ 完了 | — |
| Security audit (pip-audit/bandit) | ✅ 完了 WARN | `logs/security_audit/pre-migration-20260424_*` |
| cryptography / pillow 更新 | ✅ 完了 | 46.0.7 / 12.2.0 |
| pytest baseline 取得 | ✅ 完了 | ai-chan 1437 pass / hinomoto 276 pass |
| MLX Metal 稼働確認 | ✅ 完了 | `mx.metal.is_available() = True` |
| RUNBOOK_NEW_MAC.md 作成 | ✅ 完了 | 同ディレクトリ |
| KNOWN_ISSUES.md 作成 | ✅ 完了 | `docs/KNOWN_ISSUES.md` |
| CHANGELOG 更新 | ✅ 完了 | `docs/CHANGELOG.md` |
| FileVault 有効化 | ⚠️ **未実施** | ユーザー操作必要 (System Settings) |
| Time Machine バックアップ | ⚠️ **マウント失敗** | 外付け再接続必要 |
| 外部ディスク rsync (artifacts 8.2GB) | ⏳ 未実施 | ユーザー操作必要 |
| plist PII Option A/B 選択 | ⏳ 保留 | ユーザー判断必要 |
| `.zshrc` anaconda3 ブロック削除 | ⏳ 保留 | ユーザー承認必要 |
| 3 件 deprecated scheduled tasks 削除 | ⏳ 保留 | claude.ai/code/scheduled |

---

## Phase A: 旧 PC での事前作業 (移管前日まで)

### A-1. git commit + tag
- [ ] ai-chan の未 commit 変更を確認
  ```
  cd /Users/fujihiranoborudai/Downloads/agent/ai-chan
  git status
  git diff --stat
  ```
- [ ] 必要に応じて **作業中 WIP** を stash またはブランチにコミット
  - ⚠️ **SECRETS_INVENTORY / ENV_SNAPSHOT で識別した機密** (.env, credentials) は commit しないこと
- [ ] 移管マーカー tag を打つ
  ```
  git tag pre-migration-20260424
  git push origin pre-migration-20260424   # リモートあれば
  ```
- [ ] hinomoto-model でも同様
  ```
  cd /Users/fujihiranoborudai/Downloads/agent/hinomoto-model
  git tag pre-migration-20260424
  ```

**失敗時**: push できない (ネット不調等) 場合は tag だけ local に打って bundle (`git bundle create repo.bundle --all`) で外部ディスクへ。

---

### A-2. 外部ディスクへの rsync

- [ ] 外部ディスクをマウント (`/Volumes/Migration` と仮定)
- [ ] 2 リポジトリをコピー
  ```
  rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
    /Users/fujihiranoborudai/Downloads/agent/ai-chan \
    /Volumes/Migration/repos/
  rsync -av --exclude='.venv' --exclude='__pycache__' \
    /Users/fujihiranoborudai/Downloads/agent/hinomoto-model \
    /Volumes/Migration/repos/
  ```
- [ ] scheduled-tasks をコピー
  ```
  rsync -av ~/.claude/scheduled-tasks/ /Volumes/Migration/claude-scheduled-tasks/
  ```
- [ ] LaunchAgents (プロジェクト関連のみ) をコピー
  ```
  mkdir -p /Volumes/Migration/LaunchAgents
  cp ~/Library/LaunchAgents/com.aichan.*.plist /Volumes/Migration/LaunchAgents/
  ```
- [ ] 設定ファイル / 重要データ
  ```
  cp ~/.bash_profile /Volumes/Migration/dotfiles/bash_profile.txt
  cp ~/.zshrc        /Volumes/Migration/dotfiles/zshrc.txt
  ```

**失敗時**: rsync エラーは通常権限問題。`--no-perms` で再試行、または `sudo rsync`。

---

### A-3. SHA-256 チェックサム (重要データ)

- [ ] アーカイブ直前に SHA-256 記録 — 移管後の照合に使用
  ```
  cd /Volumes/Migration
  find repos -type f \( -name '*.pt' -o -name '*.gguf' -o -name '*.safetensors' \) \
    -exec shasum -a 256 {} \; > /Volumes/Migration/SHA256_BEFORE.txt
  find repos -name 'requirements.lock' -exec shasum -a 256 {} \; >> /Volumes/Migration/SHA256_BEFORE.txt
  ```
- [ ] `/Volumes/Migration/SHA256_BEFORE.txt` を確認

**失敗時**: ディスク容量不足なら `.safetensors`, `.pt` 等のモデルバイナリは別ディスクに分離。

---

### A-4. 機密値のエクスポート (手動、紙 or 1Password)

- [ ] `NOTION_TOKEN` の現在値を 1Password に保存 (Notion 管理画面で再発行もあり)
- [ ] `AICHAN_ADMIN_EMAIL` 値は `honnsipittu@gmail.com` (メール)
- [ ] その他 Keychain 登録済みのシークレットがあれば `security export` で p12 エクスポート
- [ ] `.env` 実ファイルが存在する場合は **1Password の Secure Note に手動コピー** (ディスクに平文で置かない)

---

## Phase B: 新 PC 到着後の環境構築

### B-1. OS 基盤
- [ ] macOS バージョン確認 (`sw_vers`) — 15.5 相当以上推奨
- [ ] CPU 確認 (`arch`) — `arm64` なら旧環境と同等、`x86_64` なら MLX 除外が必要
- [ ] `xcode-select --install` で CLT 導入
- [ ] Rosetta (x86_64 バイナリ互換、arm64 新 PC の場合のみ): `softwareupdate --install-rosetta --agree-to-license`

### B-2. パッケージマネージャ / ランタイム

- [ ] Homebrew (任意、旧環境には無かった):
  ```
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```
- [ ] Python 3.13.2 を python.org Framework からインストール
  - 代替: `pyenv install 3.13.2 && pyenv global 3.13.2`
- [ ] (任意) miniforge3 arm64 の再導入
  ```
  curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh
  bash Miniforge3-MacOSX-arm64.sh
  ```
- [ ] nvm + Node.js 22.22.1
  ```
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
  nvm install 22.22.1
  ```
- [ ] OrbStack (Docker 代替): https://orbstack.dev

**失敗時**: Python Framework インストーラが arm64 版が無い場合は pyenv 経由に切替。

### B-3. リポジトリ復元

- [ ] 外部ディスクから rsync
  ```
  mkdir -p /Users/<new-user>/Downloads/agent
  rsync -av /Volumes/Migration/repos/ai-chan        /Users/<new-user>/Downloads/agent/
  rsync -av /Volumes/Migration/repos/hinomoto-model /Users/<new-user>/Downloads/agent/
  ```
- [ ] パーミッション再設定
  ```
  chmod -R u+rwX /Users/<new-user>/Downloads/agent
  ```
- [ ] SHA-256 照合
  ```
  cd /Users/<new-user>/Downloads/agent
  find ai-chan hinomoto-model -type f \( -name '*.pt' -o -name '*.gguf' -o -name '*.safetensors' \) \
    -exec shasum -a 256 {} \; > /tmp/SHA256_AFTER.txt
  diff /Volumes/Migration/SHA256_BEFORE.txt /tmp/SHA256_AFTER.txt
  ```
  - 差分なし → ✓
  - 差分あり → 該当ファイルを再 rsync

**失敗時**: rsync 途中断なら `--partial --append-verify` で再開。

### B-4. Python 依存インストール

- [ ] ai-chan venv
  ```
  cd ai-chan
  python3.13 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  ```
- [ ] 完全再現が必要なら lock 版
  ```
  pip install -r requirements.lock
  ```
- [ ] hinomoto-model 同様
  ```
  cd ../hinomoto-model
  python3.13 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

**失敗時**: `llama-cpp-python` / `faiss-cpu` / `torch` 等のネイティブビルドは arm64 の場合 prebuilt wheel がある。ビルド失敗時は `pip install --only-binary=:all: <pkg>` を試す。

### B-5. Apple Silicon (arm64) — MLX / MPS 有効化

移管先が **arm64** の場合のみ:
- [ ] MLX は `requirements.txt` に含まれていれば自動インストール。
      なければ追加: `pip install mlx mlx-lm`
- [ ] PyTorch MPS 動作確認
  ```
  python3 -c "import torch; print(torch.backends.mps.is_available())"
  ```
- [ ] MEMORY.md / 関連ドキュメントの「MLX 不在 / Metal 不使用」記述を**更新**する

移管先が **x86_64** (Intel Mac) の場合:
- [ ] MLX を除去: `pip uninstall mlx mlx-lm mlx-metal`
- [ ] `torch` CPU wheel に切替 (prebuilt wheel を選択)

### B-6. 環境変数 / 設定ファイル

- [ ] `.bash_profile` / `.zshrc` の非機密セクションを新 PC へ反映
  - ⚠️ **旧 x86 anaconda3 init は除去推奨**
- [ ] `~/.ssh/` 再生成
  ```
  ssh-keygen -t ed25519 -C "honnsipittu@gmail.com" -f ~/.ssh/id_ed25519
  ```
  GitHub / GitLab に公開鍵登録
- [ ] `.env` 作成 (1Password から値を注入)
  ```
  cd ai-chan
  cp .env.example .env
  chmod 600 .env
  # エディタで NOTION_TOKEN 等を投入
  ```
- [ ] `config/settings.json` 生成 (`.example` から、実値投入後 chmod 600)

### B-7. launchd plist 復元

- [ ] LaunchAgents コピー
  ```
  cp /Volumes/Migration/LaunchAgents/com.aichan.*.plist ~/Library/LaunchAgents/
  ```
- [ ] plist 内のパス確認 (新 PC のホームディレクトリと一致するか)
  ```
  grep -l "/Users/fujihiranoborudai" ~/Library/LaunchAgents/com.aichan.*.plist
  ```
  - 新 PC のユーザ名が違う場合は sed で一括置換
- [ ] load
  ```
  launchctl load ~/Library/LaunchAgents/com.aichan.security-audit.plist
  launchctl load ~/Library/LaunchAgents/com.aichan.security-weekly.plist
  launchctl list | grep aichan
  ```

**失敗時**: load エラーは plist の XML 構文不正 or パス誤り。`plutil -lint <plist>` で検証。

### B-8. scheduled-tasks (Claude Code MCP) 復元

- [ ] コピー
  ```
  mkdir -p ~/.claude/scheduled-tasks
  rsync -av /Volumes/Migration/claude-scheduled-tasks/ ~/.claude/scheduled-tasks/
  ```
- [ ] deprecated 3 件を削除 (任意)
  ```
  rm -rf ~/.claude/scheduled-tasks/ai-chan-daily-learning
  rm -rf ~/.claude/scheduled-tasks/ai-chan-daily-security-scan
  rm -rf ~/.claude/scheduled-tasks/ai-chan-test-regression
  ```
- [ ] Claude Code 起動 → MCP scheduled-tasks list 確認

詳細は `SCHEDULED_TASKS_EXPORT_20260424.md` 参照。

---

## Phase C: 疎通テスト

### C-1. pytest 緑確認
- [ ] ai-chan
  ```
  cd /Users/<new-user>/Downloads/agent/ai-chan
  source .venv/bin/activate
  python3 -m pytest -q
  ```
  - 全緑期待 / カバレッジ 80%+ (`--cov=core --cov=utils --cov=ui`)
- [ ] hinomoto-model
  ```
  cd /Users/<new-user>/Downloads/agent/hinomoto-model
  source .venv/bin/activate
  python3 -m pytest -q
  ```

**失敗時**: import error は wheel 不整合の可能性 → `pip install --force-reinstall <pkg>`。環境差分は `MIGRATION_WARNINGS.md` を作成して記録。

### C-2. main.py smoke 起動
- [ ] ai-chan
  ```
  cd ai-chan
  python3 main.py --smoke   # smoke フラグがあれば
  # なければ対話を起動し即 Ctrl-C で停止して import エラーが無いこと確認
  ```

### C-3. health-check 動作確認
- [ ] `ai-chan-health-check` を手動トリガ (MCP or cron 次回まで待つ)
- [ ] `logs/health/health-YYYYMMDD.log` が生成される
- [ ] import smoke が N/N 成功

### C-4. watchdog 動作確認
- [ ] hinomoto `logs/watchdog/watchdog-YYYYMMDD.log` が 30 分以内に生成

---

## Phase D: Kill-Switch 動作確認 (ai-chan)

- [ ] Kill-Switch トリガ確認 (ai-chan セキュリティ機構)
  ```
  cd ai-chan
  python3 -m core.kill_switch --dry-run   # 実装に合わせる
  ```
- [ ] Kill-Switch ログが `logs/kill_switch/` に出ることを確認
- [ ] 復旧手順 (SECURITY.md の Kill-Switch セクション) に従い戻せる

---

## Phase E: 最終確認

- [ ] `git status` が clean (全リポジトリ)
- [ ] `git log --oneline -5` で tag `pre-migration-20260424` が見える
- [ ] scheduled-tasks が 6 件 (または deprecated 含め 9 件) 認識される
- [ ] `launchctl list | grep aichan` が 2 件
- [ ] ディスク使用量確認 (`du -sh /Users/<new-user>/Downloads/agent/`)

### 旧 PC 廃棄前の最終タスク
- [ ] ディスクの secure erase (FileVault 暗号化済なら unenroll 後 erase で足りる)
- [ ] 外部ディスクの SHA256 照合を最後にもう一度
- [ ] 旧 PC 内の `~/.ssh/`, `.env`, Keychain を完全削除

---

## 付録: フォールバック早見表

| 症状 | フォールバック |
|------|----------------|
| Python が見つからない | `pyenv install 3.13.2 && pyenv local 3.13.2` |
| pip install 失敗 (ネイティブビルド) | `pip install --only-binary=:all: <pkg>` |
| launchctl load 失敗 | `plutil -lint <plist>` で XML 検証、パス置換 |
| scheduled-tasks が認識されない | Claude Code 再起動、`~/.claude/scheduled-tasks/<id>/SKILL.md` の frontmatter 検証 |
| SHA256 不一致 | 該当ファイルを再 rsync、巨大モデルは再ダウンロード可能なものは HF から取り直し |
| MLX import エラー (x86_64 環境) | `pip uninstall mlx mlx-lm mlx-metal` |
| PyTorch MPS 利用不可 | `torch.device('cpu')` にフォールバック、学習速度は劣化するが動く |
| `.env` 不在 | `.env.example` からコピー → 1Password から値注入 → `chmod 600` |
| Notion Token 失効 | Notion → Settings → Integrations で再発行 |

---

## 関連ドキュメント
- `SECRETS_INVENTORY_20260424.md` — 機密所在地インベントリ
- `ENV_SNAPSHOT_20260424.md` — OS / Python / pip 一覧
- `SCHEDULED_TASKS_EXPORT_20260424.md` — scheduled-tasks 全文エクスポート
