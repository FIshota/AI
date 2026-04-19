#!/usr/bin/env bash
# ai-chan メール通知 (macOS Mail.app 経由 — SMTP設定不要)
#
# Usage: scripts/notify_mail.sh <to> <subject> <body_md_path> [severity]
#
# 仕組み:
#   AppleScript で Mail.app を操作し、新規メッセージを作成して送信。
#   Mail.app が起動していない場合は一時的に起動される。
#   送信アカウントは Mail.app のデフォルト送信元。
#
# 事前準備:
#   - Mail.app に少なくとも1つのアカウント (iCloud / Gmail 等) を登録済み
#   - システム環境設定 > セキュリティ > オートメーション で
#     「ターミナル (または launchd)」が Mail を操作する権限を許可
set -uo pipefail

TO="${1:-}"
SUBJECT="${2:-ai-chan Notification}"
BODY_PATH="${3:-}"
SEVERITY="${4:-INFO}"

if [ -z "$TO" ]; then
  echo "[notify_mail] no recipient; skipping" >&2
  exit 0
fi

# 本文: md ファイルがあれば先頭 200 行を使う
if [ -n "$BODY_PATH" ] && [ -f "$BODY_PATH" ]; then
  BODY=$(head -n 200 "$BODY_PATH")
else
  BODY="(no summary available)"
fi

# AppleScript 用に本文をエスケープ (改行は \n に、ダブルクォートは \")
BODY_ESCAPED=$(printf '%s' "$BODY" | python3 -c '
import sys
text = sys.stdin.read()
# AppleScript string literal 用
text = text.replace("\\", "\\\\").replace("\"", "\\\"")
# 改行は "\n" リテラル扱い (AppleScript では文字列中の実際の改行はOK)
print(text)
')

# ヘッダに severity を含める
FULL_BODY="ai-chan 自動セキュリティ監査レポート

Severity: $SEVERITY
Date:     $(date -u +%Y-%m-%dT%H:%M:%SZ)
Host:     $(hostname)

─────────────────────────────────────
$BODY_ESCAPED
─────────────────────────────────────

このメールは ai-chan ローカル launchd ($(basename "$0")) から自動送信されました。
ログ全体は $BODY_PATH 参照。
"

# 一時ファイル経由で AppleScript に渡す (引数長制限回避)
TMP_BODY=$(mktemp -t aichan-mail)
printf '%s' "$FULL_BODY" > "$TMP_BODY"

osascript <<APPLESCRIPT
set bodyText to (do shell script "cat " & quoted form of "$TMP_BODY")
tell application "Mail"
    set newMessage to make new outgoing message with properties {subject:"$SUBJECT", content:bodyText, visible:false}
    tell newMessage
        make new to recipient at end of to recipients with properties {address:"$TO"}
    end tell
    send newMessage
end tell
APPLESCRIPT
RC=$?

rm -f "$TMP_BODY"

if [ $RC -eq 0 ]; then
  echo "[notify_mail] sent to $TO"
else
  echo "[notify_mail] FAILED (rc=$RC) — check Mail.app automation permission" >&2
fi
exit $RC
