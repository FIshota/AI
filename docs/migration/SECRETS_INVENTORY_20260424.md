# SECRETS INVENTORY — 2026-04-24

> PC 移管準備: 機密情報の **所在のみ** を記録したインベントリ。
> **値は一切記録しない** (存在 / 権限 / サイズ / キー名のみ)。
> 新 PC 移管時の復元手順を各項目に添付。

スキャン対象:
- `/Users/fujihiranoborudai/Downloads/agent/ai-chan`
- `/Users/fujihiranoborudai/Downloads/agent/hinomoto-model`
- `~` (ホームディレクトリ、SSH / GPG / Keychain / LaunchAgents)

---

## 1. `.env*` ファイル

| パス | 権限 | サイズ (bytes) | 種別 |
|------|------|----------------|------|
| `ai-chan/.env.example` | `-rw-r--r--` (644) | 1744 | テンプレート (機密なし、公開可) |
| `ai-chan/.env` | — | — | **存在せず** (運用前の生成待ち、または未使用) |
| `hinomoto-model/.env*` | — | — | **存在せず** |
| `~/.env*` | — | — | **存在せず** |

### `.env.example` に含まれる env 変数名 (値ではなくキー名のみ)
- `AICHAN_ALLOWED_ORIGINS`
- `AICHAN_MODEL_PATH`
- `GOOGLE_CREDENTIALS_PATH`
- `NOTION_TOKEN`   ← 要秘匿
- `AICHAN_LOG_LEVEL`

### 復元手順 (新 PC)
1. `cp ai-chan/.env.example ai-chan/.env`
2. `chmod 600 ai-chan/.env`
3. 1Password / Keychain から値を取り出して各変数に流し込む
4. `NOTION_TOKEN` は Notion Integrations から再発行可能

---

## 2. `config/` 配下の API キー候補を含む YAML/JSON

機械スキャン: `grep -l -i -E "api_key|apikey|token|secret|password|credential"` (値は読まず、キー名のみ抽出)

| ファイル | 権限 | サイズ | 検出キー名 (値非記録) |
|---------|------|--------|------------------------|
| `ai-chan/config/settings_schema.json` | `-rw-r--r--` (644) | 14,300 | `api_key`, `credentials_file`, `password` (**schema 定義のみ、実値なし**) |
| `ai-chan/config/settings.json` | — | — | **存在せず** (例示のみ) |
| `ai-chan/config/settings.json.example` | — | — | 記載あり (example, 値はプレースホルダ) |
| `ai-chan/config/access_control.json` | 644 | 118 | なし |
| `ai-chan/config/persona.json` | 644 | 2,298 | なし |
| `ai-chan/config/security_policy.yaml` | 644 | 2,162 | なし |
| `ai-chan/config/consent_items.yaml` | 644 | 2,179 | なし |
| `ai-chan/config/log_retention.yaml` | 644 | 1,616 | なし |
| `ai-chan/config/voice_auth_challenges.yaml` | 644 | 970 | なし (音声認証プロンプトテキストのみ、機密ではない) |
| `hinomoto-model/config/deny_list.yaml` | 644 | — | なし |
| `hinomoto-model/configs/*.json` (ablation, main_run 等) | 644 | — | 学習ハイパラのみ、機密なし |

### 復元手順 (新 PC)
1. リポジトリ clone 後、`config/settings.json` は **別途 Keychain** から値を注入して生成
2. `config/settings.json.example` をコピーし、`YOUR_*` プレースホルダを実値で置換
3. 該当ファイルを `chmod 600` に変更 (実値投入後)

---

## 3. SSH 鍵

`~/.ssh/` 内容:
```
config
known_hosts
known_hosts.old
```

**重要**: 現時点で `id_rsa`, `id_ed25519`, `id_ecdsa` 等の**秘密鍵ファイルは存在しない**。
`known_hosts` は公開情報のみ。

### 復元手順 (新 PC)
- 旧 PC に秘密鍵が無いため、新 PC で新規生成:
  ```
  ssh-keygen -t ed25519 -C "honnsipittu@gmail.com" -f ~/.ssh/id_ed25519
  ```
- 生成後 GitHub / GitLab 等に公開鍵を登録
- `~/.ssh/config` は git で追跡するか手動コピー (機密なしだが便利設定あり)

---

## 4. GPG 鍵

```
$ gpg --list-secret-keys
→ gpg コマンド未インストール (/bin/bash: gpg: command not found)
```

**GPG は現状運用していない**。コミット署名もなし。

### 復元手順
- 必要に応じて新 PC で `brew install gnupg` 後に `gpg --gen-key` で新規作成
- 旧環境からの秘密鍵移管は不要 (存在しないため)

---

## 5. launchd plist 内のシークレット参照

対象: `~/Library/LaunchAgents/*.plist` (ai-chan / hinomoto 関連のみ)

| plist | 機密参照 | 備考 |
|-------|----------|------|
| `com.aichan.security-audit.plist` | `AICHAN_ADMIN_EMAIL` (メールアドレス、個人情報) | 鍵/トークンは含まれない |
| `com.aichan.security-weekly.plist` | `AICHAN_ADMIN_EMAIL` (同上) | 同上 |

**上記以外の LaunchAgents** (Adobe / Google Updater / Epic / Movavi / Avira) はサードパーティ製で ai-chan / hinomoto とは無関係。

### 復元手順 (新 PC)
1. リポジトリ `ai-chan/launchd/` にある plist テンプレートから再生成
2. `AICHAN_ADMIN_EMAIL` 値は手動で差し込み
3. `launchctl load ~/Library/LaunchAgents/com.aichan.security-audit.plist`

---

## 6. iCloud / Apple 署名 (codesigning identities)

```
$ security find-identity -v -p codesigning
0 valid identities found
```

**コード署名用の証明書は現在インストールされていない**。
AiChan.app は開発中のため未署名配布でも問題なし。

### 復元手順
- 本格配布する場合のみ Apple Developer Program (年 $99) で証明書発行
- 発行後 `security import <cert>.p12 -k login.keychain` で Keychain に追加

---

## 7. Keychain (login.keychain)

現時点で ai-chan / hinomoto がプログラム的に Keychain から読み出しているシークレットは **未検出**。
将来 `NOTION_TOKEN` 等を Keychain に移す場合:
```
security add-generic-password -a "$USER" -s "ai-chan/NOTION_TOKEN" -w "<token>"
```

### 復元手順
- 新 PC で上記コマンドを再実行
- 旧 PC からの Keychain 一括エクスポート (`security export`) は暗号化済 p12 経由推奨

---

## 総括

- **高リスク秘密鍵**: 現時点では存在しない (SSH / GPG 共になし)
- **.env 実ファイル**: 存在せず、`.env.example` のみ
- **launchd 内の実秘匿値**: メールアドレスのみ (トークン類なし)
- **コード署名証明書**: なし
- 機密情報は主に `config/settings.json` (まだ未生成) と Notion Token (env 経由) に集約予定

**新 PC 移管は比較的シンプル** — 実秘匿値がまだ少ないため、設定注入は後作業で足りる。
