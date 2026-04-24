# Deprecated Scheduled Tasks 整理手順

**作成日**: 2026-04-24
**対象**: Claude Scheduled Tasks (MCP scheduled-tasks) に `enabled=false` で残存している非推奨タスク

## 背景

`enabled=false` で残すと移管時・棚卸時に「これ何？」となり混乱の原因になる。MCP では削除不可のため、ユーザーが Web UI から手動削除する必要がある。

削除 UI: <https://claude.ai/code/scheduled>

## 削除対象一覧

| Task ID | ステータス | 非推奨理由 | 代替タスク |
|---------|-----------|-----------|-----------|
| `ai-chan-daily-learning` | SUPERSEDED | 日次学習ループは `ai-chan-daily-morning` の learning フェーズに統合済み | `ai-chan-daily-morning` |
| `ai-chan-daily-security-scan` | DEPRECATED | macOS LaunchAgent (`com.aichan.security-audit`) に移管済み。Scheduled Task 側は二重実行になるため停止 | `~/Library/LaunchAgents/com.aichan.security-audit.plist` |
| `ai-chan-test-regression` | SUPERSEDED | `ai-chan-daily-morning` の regression フェーズに統合済み | `ai-chan-daily-morning` |

## 削除手順（ユーザー作業）

1. <https://claude.ai/code/scheduled> を開く
2. 上表の各 Task ID を検索
3. タスクカードの「...」メニュー → Delete を選択
4. 確認ダイアログで削除実行
5. 3 件すべて削除したら、以下のコマンドで残存確認:

```bash
# MCP 側での確認（Claude Code 内）
# scheduled-tasks__list_scheduled_tasks を実行し、該当 ID が出ないこと
```

## 削除前チェック

- [ ] `ai-chan-daily-morning` が正しく動作している（直近7日以内に success 記録あり）
- [ ] `com.aichan.security-audit` LaunchAgent がロードされている (`launchctl list | grep aichan` で確認）
- [ ] 監査証跡（最後の実行ログ）を別途保全したい場合は、削除前に実行履歴をエクスポート

## 移管先マシンでの扱い

移管先では以下のみを再登録する:

- `ai-chan-daily-morning`
- （その他現時点で enabled=true のタスク）

非推奨3タスクは再登録しないこと。
