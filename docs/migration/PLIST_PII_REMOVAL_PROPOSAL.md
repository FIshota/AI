# LaunchAgents plist PII 除去 提案

**ステータス**: 要ユーザー承認（自動実行していません）
**作成日**: 2026-04-24
**対象ファイル**:
- `~/Library/LaunchAgents/com.aichan.security-audit.plist`
- `~/Library/LaunchAgents/com.aichan.security-weekly.plist`

## 問題

両 plist の `EnvironmentVariables` セクションに `AICHAN_ADMIN_EMAIL` として実メールアドレスが平文で埋め込まれている。plist は `~/Library/LaunchAgents/` に配置され、Spotlight・Time Machine・バックアップ対象となるため、PII の露出面が広い。

該当箇所（確認済）:

```
com.aichan.security-audit.plist:63-64   <key>AICHAN_ADMIN_EMAIL</key>
                                        <string>honnsipittu@gmail.com</string>
com.aichan.security-weekly.plist:35-36  <key>AICHAN_ADMIN_EMAIL</key>
                                        <string>honnsipittu@gmail.com</string>
```

launchctl load 状態（確認済）: 両方ロード済み。

```
-  0  com.aichan.security-weekly
-  0  com.aichan.security-audit
```

## 推奨修正方式 (Option A: admin.env 分離方式)

### 1. 秘密ファイルを作成

```bash
mkdir -p ~/.config/ai-chan
cat > ~/.config/ai-chan/admin.env <<'EOF'
export AICHAN_ADMIN_EMAIL="<REDACTED_EMAIL>"
EOF
chmod 700 ~/.config/ai-chan
chmod 600 ~/.config/ai-chan/admin.env
```

### 2. plist の `EnvironmentVariables` から `AICHAN_ADMIN_EMAIL` を削除

`com.aichan.security-audit.plist` の L63-64、`com.aichan.security-weekly.plist` の L35-36 を丸ごと削除。

### 3. `ProgramArguments` を env source 経由に変更

Before:
```xml
<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>/Users/fujihiranoborudai/Downloads/agent/ai-chan/scripts/daily_security_audit.sh</string>
</array>
```

After:
```xml
<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>source "$HOME/.config/ai-chan/admin.env" &amp;&amp; exec /Users/fujihiranoborudai/Downloads/agent/ai-chan/scripts/daily_security_audit.sh</string>
</array>
```

### 4. 反映手順

```bash
# バックアップ
mkdir -p ~/Library/LaunchAgents/backups/$(date +%Y%m%d_%H%M%S)
cp ~/Library/LaunchAgents/com.aichan.security-audit.plist \
   ~/Library/LaunchAgents/backups/$(date +%Y%m%d_%H%M%S)/
cp ~/Library/LaunchAgents/com.aichan.security-weekly.plist \
   ~/Library/LaunchAgents/backups/$(date +%Y%m%d_%H%M%S)/

# unload
launchctl unload ~/Library/LaunchAgents/com.aichan.security-audit.plist
launchctl unload ~/Library/LaunchAgents/com.aichan.security-weekly.plist

# (plist を編集)

# load
launchctl load ~/Library/LaunchAgents/com.aichan.security-audit.plist
launchctl load ~/Library/LaunchAgents/com.aichan.security-weekly.plist

# 確認
launchctl list | grep aichan
```

## 代替方式 (Option B: 単純ファイル参照)

シェル側実装がシンプルで良い場合:

```bash
echo "<REDACTED_EMAIL>" > ~/.config/ai-chan/admin_email.txt
chmod 600 ~/.config/ai-chan/admin_email.txt
```

`daily_security_audit.sh` 内部で読み込み:
```bash
AICHAN_ADMIN_EMAIL="$(cat ~/.config/ai-chan/admin_email.txt)"
```

plist からは `AICHAN_ADMIN_EMAIL` 環境変数を削除するだけで済む。

## Option A vs B

| 項目 | A (admin.env + source) | B (admin_email.txt) |
|------|------------------------|----------------------|
| plist の改変量 | `ProgramArguments` + env 両方 | env 削除のみ |
| スクリプト改変 | 不要 | 必要 |
| 拡張性（他秘密の追加） | 高い | 低い |
| 推奨 | ○ | △ |

## 要確認

- [ ] Option A / B どちらを採用するか
- [ ] `~/.config/ai-chan/admin.env` パスで良いか（既存 `~/.config` 配下慣習に従う）
- [ ] バックアップ保存先 `~/Library/LaunchAgents/backups/<ts>/` で良いか
- [ ] 移管先マシンで新規セットアップする際、このファイルは手動再作成（`.example` のみ同期）か
