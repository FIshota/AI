# config/settings.json 初期化ガイド

**作成日**: 2026-04-24
**対象**: `ai-chan/config/settings.json`（リポジトリに未コミット）

## 現状

- `config/settings.json.example` はリポジトリ管理下
- `config/settings.json` は **未生成**（gitignore 対象）
- 実行時に `settings.json` 不在で fallback が効くが、本番運用には明示生成が必須

## 初期化手順

### 1. 雛形コピー

```bash
cd /path/to/ai-chan
cp config/settings.json.example config/settings.json
```

### 2. パーミッション設定（必須）

```bash
chmod 600 config/settings.json
```

理由: 機密値（メールアドレス、トークン等）を含むため、グループ/他ユーザーから読めないようにする。

### 3. 機密フィールドを手動設定

以下のフィールドは `.example` では placeholder になっているため、実運用値に置換:

| フィールド | 内容 | 取得方法 |
|-----------|------|----------|
| `admin_email` | 管理者通知先メール | 本人のメール |
| `admin_webhook_url` | 通知 Webhook URL | Slack / Discord の Incoming Webhook |
| `voice_id_salt` | 話者識別ソルト | `openssl rand -hex 32` |
| `federated_api_key` | フェデレーション API キー | サービス発行値 |

**編集例（擬似）**:
```json
{
  "admin_email": "<YOUR_EMAIL>",
  "admin_webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ",
  "voice_id_salt": "<RANDOM_HEX_32>",
  "federated_api_key": "<API_KEY>"
}
```

**注意**: 本ファイルには実値を書かない。`config/settings.json` はリポジトリに commit しないこと（`.gitignore` 確認済み想定）。

### 4. 検証

```bash
# JSON パース確認
python3 -c "import json; json.load(open('config/settings.json'))"

# スキーマ検証
python3 -c "
import json, jsonschema
s = json.load(open('config/settings_schema.json'))
c = json.load(open('config/settings.json'))
jsonschema.validate(c, s)
print('OK')
"
```

## 移管先での扱い

1. リポジトリを clone
2. この手順に従って `settings.json` を **手動再作成**
3. 既存マシンの `config/settings.json` を **コピー転送しない**（PII 漏れ防止、1Password/Bitwarden 経由で個別に値を転送）

## 関連

- `config/settings.json.example` - 雛形
- `config/settings_schema.json` - JSON Schema
- `docs/migration/SECRETS_INVENTORY_20260424.md` - 秘密情報棚卸
- `docs/migration/PLIST_PII_REMOVAL_PROPOSAL.md` - LaunchAgent 側の admin_email 除去提案
