#!/usr/bin/env bash
# ai-chan セキュリティ監査 LaunchAgent インストーラ
#
# 実行内容:
#   1. ~/Library/LaunchAgents/ に plist をコピー
#   2. launchctl load で登録
#   3. 初回テスト実行
#   4. Mail.app オートメーション権限の案内
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$ROOT/config/com.aichan.security-audit.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.aichan.security-audit.plist"
LABEL="com.aichan.security-audit"

echo "━━━ ai-chan Security Audit LaunchAgent インストール ━━━"
echo "Root : $ROOT"
echo "Plist: $PLIST_DST"
echo ""

# ─── 1. 権限確認 ────────────────────────────────────────
chmod +x "$ROOT/scripts/daily_security_audit.sh" "$ROOT/scripts/notify_mail.sh" "$ROOT/scripts/audit.sh"

# ─── 2. 既存エージェントを unload ────────────────────────
if launchctl list | grep -q "$LABEL"; then
  echo "[1/5] 既存の LaunchAgent を unload..."
  launchctl unload "$PLIST_DST" 2>/dev/null || true
else
  echo "[1/5] 既存エージェント なし"
fi

# ─── 3. plist をユーザー LaunchAgents にコピー ───────────
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
echo "[2/5] plist コピー完了: $PLIST_DST"

# ─── 4. load ─────────────────────────────────────────────
launchctl load "$PLIST_DST"
if launchctl list | grep -q "$LABEL"; then
  echo "[3/5] LaunchAgent 登録成功"
else
  echo "[3/5] ❌ 登録失敗 — launchctl load のエラーを確認してください"
  exit 1
fi

# ─── 5. 初回テスト実行 ───────────────────────────────────
echo "[4/5] 初回テスト実行 (数分かかる場合あり) ..."
echo "       → logs/security/ に結果が出力されます"
# 非同期で実行 (kick off のみ)
launchctl start "$LABEL"
echo "       kicked off. ログ: $ROOT/logs/security/launchd.out"
echo ""

# ─── 6. 案内 ─────────────────────────────────────────────
cat <<'MSG'
[5/5] ✅ インストール完了

━━━ 次に必要な設定 ━━━

📧 Mail.app オートメーション権限:
   初回のメール送信時に、macOSがダイアログで
   「Terminal が Mail を制御することを許可しますか？」
   と尋ねます。「許可」を選んでください。

   既に拒否してしまった場合:
   システム設定 → プライバシーとセキュリティ → オートメーション
   → [Terminal] または [launchd] → Mail にチェック

🔔 通知センター:
   システム設定 → 通知 → 「ターミナル」および「スクリプトエディタ」
   → 通知を許可 ON

━━━ 手動操作 ━━━

今すぐ実行:      launchctl start  com.aichan.security-audit
一時停止:        launchctl unload ~/Library/LaunchAgents/com.aichan.security-audit.plist
再開:            launchctl load   ~/Library/LaunchAgents/com.aichan.security-audit.plist
ステータス確認:  launchctl list | grep aichan
ログ確認:        tail -n 50 logs/security/launchd.out
最新サマリ:      ls -t logs/security/*.md | head -1 | xargs cat

━━━ スケジュール ━━━
   毎朝 09:00 (ローカル時刻 = JST)
   Macがスリープ中の場合は、次回起動時に1回だけ追実行されます
MSG
