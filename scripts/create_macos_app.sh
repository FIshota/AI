#!/bin/bash
# アイ.app を作成して /Applications に配置するスクリプト
# 使い方: bash scripts/create_macos_app.sh

set -e

# ─── 設定 ───────────────────────────────────────────────
APP_NAME="アイ"
APP_BUNDLE="${APP_NAME}.app"
AI_CHAN_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # このスクリプトの親ディレクトリ

# Python 実行ファイルを探す（llama_cpp が入っている環境を優先）
find_python() {
    for candidate in \
        "${AI_CHAN_DIR}/.venv/bin/python" \
        "${AI_CHAN_DIR}/venv/bin/python" \
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
        "$(which python3 2>/dev/null)" \
        "$(which python 2>/dev/null)"; do
        if [ -f "${candidate}" ] && "${candidate}" -c "import llama_cpp" 2>/dev/null; then
            echo "${candidate}"
            return 0
        fi
    done
    # llama_cpp なくても最低限動かす
    echo "$(which python3 || which python)"
}
PYTHON="$(find_python)"

echo "=== アイ.app 作成スクリプト ==="
echo "AI_CHAN_DIR : ${AI_CHAN_DIR}"
echo "Python      : ${PYTHON}"
echo "App Bundle  : ~/Desktop/${APP_BUNDLE}"
echo ""

# ─── .app バンドルを作成 ─────────────────────────────────
DEST="${HOME}/Desktop/${APP_BUNDLE}"
rm -rf "${DEST}"

mkdir -p "${DEST}/Contents/MacOS"
mkdir -p "${DEST}/Contents/Resources"

# ── 起動スクリプト（MacOS/launch）
cat > "${DEST}/Contents/MacOS/launch" << LAUNCH_SCRIPT
#!/bin/bash
export PATH="${AI_CHAN_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
cd "${AI_CHAN_DIR}"
# arm64 を明示して Rosetta 経由起動を防ぐ
exec /usr/bin/arch -arm64 "${PYTHON}" -u main.py --desktop >> "${AI_CHAN_DIR}/data/app.log" 2>&1
LAUNCH_SCRIPT
chmod +x "${DEST}/Contents/MacOS/launch"

# ── Info.plist
cat > "${DEST}/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>アイ</string>
  <key>CFBundleDisplayName</key>
  <string>アイ</string>
  <key>CFBundleIdentifier</key>
  <string>jp.local.ai-chan</string>
  <key>CFBundleVersion</key>
  <string>0.1.0</string>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleSignature</key>
  <string>????</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>LSUIElement</key>
  <false/>
  <key>NSRequiresAquaSystemAppearance</key>
  <false/>
</dict>
</plist>
PLIST

# ── アイコン（assets/ai_chan.png があれば icns に変換）
ICON_PNG="${AI_CHAN_DIR}/assets/ai_chan.png"
if [ -f "${ICON_PNG}" ]; then
    echo "アイコンを変換中..."
    ICONSET="${DEST}/Contents/Resources/AppIcon.iconset"
    mkdir -p "${ICONSET}"

    sips -z 16   16   "${ICON_PNG}" --out "${ICONSET}/icon_16x16.png"    2>/dev/null || true
    sips -z 32   32   "${ICON_PNG}" --out "${ICONSET}/icon_16x16@2x.png" 2>/dev/null || true
    sips -z 32   32   "${ICON_PNG}" --out "${ICONSET}/icon_32x32.png"    2>/dev/null || true
    sips -z 64   64   "${ICON_PNG}" --out "${ICONSET}/icon_32x32@2x.png" 2>/dev/null || true
    sips -z 128  128  "${ICON_PNG}" --out "${ICONSET}/icon_128x128.png"  2>/dev/null || true
    sips -z 256  256  "${ICON_PNG}" --out "${ICONSET}/icon_128x128@2x.png" 2>/dev/null || true
    sips -z 256  256  "${ICON_PNG}" --out "${ICONSET}/icon_256x256.png"  2>/dev/null || true
    sips -z 512  512  "${ICON_PNG}" --out "${ICONSET}/icon_256x256@2x.png" 2>/dev/null || true
    sips -z 512  512  "${ICON_PNG}" --out "${ICONSET}/icon_512x512.png"  2>/dev/null || true
    sips -z 1024 1024 "${ICON_PNG}" --out "${ICONSET}/icon_512x512@2x.png" 2>/dev/null || true

    iconutil -c icns "${ICONSET}" -o "${DEST}/Contents/Resources/AppIcon.icns" 2>/dev/null \
        && echo "✓ アイコン変換完了" \
        || echo "△ iconutil 失敗（アイコンなしで続行）"
    rm -rf "${ICONSET}"
fi

echo ""
echo "✓ ${DEST} を作成しました"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Dock への追加方法："
echo "  1. デスクトップにできた「アイ.app」をダブルクリックして起動確認"
echo "  2. Dock に表示されたアイコンを右クリック →「オプション」→「Dockに追加」"
echo "  または"
echo "  3. Finder で ~/Desktop/アイ.app を開き、"
echo "     そのまま Dock にドラッグ&ドロップ"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "※ 初回起動時に「開発元が不明」と表示されたら："
echo "   システム環境設定 → セキュリティとプライバシー →「このまま開く」を選択"
