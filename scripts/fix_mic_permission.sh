#!/bin/bash
# macOS マイク権限修正スクリプト
# Terminal から直接実行してください: bash scripts/fix_mic_permission.sh

echo "========================================"
echo "  ai-chan マイク権限セットアップ"
echo "========================================"
echo ""

# 現在のステータスを確認
STATUS=$(python3 -c "
from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
s = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
print(s)
" 2>/dev/null || echo "unknown")

echo "現在のマイク権限ステータス: $STATUS"
echo "  (0=未決定, 1=制限, 2=拒否, 3=許可済み)"
echo ""

if [ "$STATUS" = "3" ]; then
    echo "✅ 既にマイク権限があります！"
    echo "   python3 main.py --desktop でアプリを起動してください"
    exit 0
fi

echo "マイク権限を要求するためにアプリを起動します..."
echo "【重要】ダイアログが表示されたら「OK」をクリックしてください"
echo ""

# アプリを起動してマイク権限をリクエスト
cd "$(dirname "$0")/.."
python3 main.py --desktop &
APP_PID=$!

sleep 5
kill $APP_PID 2>/dev/null

# 再チェック
STATUS2=$(python3 -c "
from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
s = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
print(s)
" 2>/dev/null || echo "unknown")

echo ""
if [ "$STATUS2" = "3" ]; then
    echo "✅ マイク権限が付与されました！"
    echo ""
    echo "アプリを起動します:"
    echo "  python3 main.py --desktop"
else
    echo "⚠️ 自動設定できませんでした。手動で設定してください:"
    echo ""
    echo "【手動設定方法】"
    echo "1. システム設定を開く:"
    echo "   open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone'"
    echo ""
    echo "2.「+」ボタンをクリック"
    echo "   → /Applications/Utilities/Terminal.app を選択"
    echo "   → トグルをONにする"
    echo ""
    echo "3. Terminalを完全に終了して再起動"
    echo ""
    echo "4. もう一度このスクリプトを実行: bash scripts/fix_mic_permission.sh"
    open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone'
fi
