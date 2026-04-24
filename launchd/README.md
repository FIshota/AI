# ai-chan/launchd/

リポジトリ管理下の macOS LaunchAgent plist 群。

**現状**: いずれも `launchctl load` されていない（opt-in 運用）。必要になった時点で個別に `~/Library/LaunchAgents/` へコピーして load する。

## 含まれる plist

| plist | 目的 | 推奨頻度 |
|-------|------|----------|
| `com.aichan.api-docs.plist` | API ドキュメント再生成 | 週次 |
| `com.aichan.backup-restore-drill.plist` | バックアップ復元ドリル | 月次 |
| `com.aichan.dr-drill.plist` | 災害復旧ドリル | 四半期 |
| `com.aichan.flaky-finder.plist` | flaky test 検出 | 日次 |
| `com.aichan.killswitch-drill.plist` | killswitch 動作確認 | 月次 |
| `com.aichan.log-retention.plist` | ログ保持ポリシー適用 | 日次 |
| `com.aichan.monitoring-checks.plist` | 監視チェック | 時間次 |

## なぜ未 load か

- 開発段階で副作用コストが高い（ドリル系はシステム状態を触る）
- 開発者ごとに必要なジョブが異なる
- CI/本番ホストで管理すべきもの（`com.aichan.log-retention` など）は別ホストに配置予定
- 実メールや絶対パスを含むジョブ（セキュリティ監査系）は `~/Library/LaunchAgents/` に別途配置済み（`docs/migration/PLIST_PII_REMOVAL_PROPOSAL.md` 参照）

## load 手順（個別）

```bash
# 例: flaky-finder を有効化
PLIST="com.aichan.flaky-finder.plist"

# 1. ProgramArguments の絶対パスが自ホストに合っているか確認
grep -E "<string>/" "$(pwd)/launchd/$PLIST"

# 2. ~/Library/LaunchAgents/ にコピー
cp "launchd/$PLIST" ~/Library/LaunchAgents/

# 3. load
launchctl load ~/Library/LaunchAgents/$PLIST

# 4. 確認
launchctl list | grep aichan
```

## unload 手順

```bash
launchctl unload ~/Library/LaunchAgents/com.aichan.flaky-finder.plist
rm ~/Library/LaunchAgents/com.aichan.flaky-finder.plist
```

## 移管時の扱い

移管先で必要なジョブだけを `cp` で再度配置する。全件自動 load はしない。
