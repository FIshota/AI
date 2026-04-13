#!/usr/bin/env python3
"""
マイク権限をリクエストするヘルパー
Terminal から直接実行してください:
  python3 scripts/request_mic.py
"""
import sys, time, signal

def main():
    # ── 現在のステータスを確認 ──────────────────────────
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio  # type: ignore
    except ImportError:
        print("pyobjc-framework-AVFoundation が必要です。")
        print("pip install pyobjc-framework-AVFoundation")
        sys.exit(1)

    status = int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
    labels = {0: "⚠️  未設定", 1: "制限", 2: "❌ 拒否済み", 3: "✅ 許可済み"}
    print(f"現在のマイク権限: {labels.get(status, status)}")

    if status == 3:
        print("\n✅ 既にマイク権限があります！")
        print("   python3 main.py --desktop でアプリを起動してください")
        return

    if status == 2:
        print("\n❌ マイク権限が拒否されています。")
        print("   システム設定 → プライバシーとセキュリティ → マイク")
        print("   → python3 または Terminal のトグルをONにしてください")
        return

    # ── status == 0（未設定）→ ダイアログを表示 ────────────────
    print("\nマイク権限ダイアログを表示します...")
    print("【重要】画面に表示されるダイアログで「OK」をクリックしてください！\n")

    try:
        from AppKit import NSApplication  # type: ignore
        from Foundation import NSRunLoop, NSDate  # type: ignore
    except ImportError:
        print("pyobjc-framework-AppKit が必要です。")
        sys.exit(1)

    # NSApplication の run loop を確立（ダイアログ表示に必要）
    NSApplication.sharedApplication()

    result = [None]

    def _cb(granted):
        result[0] = bool(granted)

    AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        AVMediaTypeAudio, _cb
    )

    # ダイアログへの応答を最大 60 秒待つ
    deadline = time.time() + 60
    while result[0] is None and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.2)
        )
        sys.stdout.write(".")
        sys.stdout.flush()

    print()
    if result[0] is True:
        print("\n✅ マイク権限が許可されました！")
        print("   これで録音できます。")
        print("   python3 main.py --desktop を起動してください。")
    elif result[0] is False:
        print("\n❌ マイク権限が拒否されました。")
        print("   システム設定 → プライバシーとセキュリティ → マイク で手動でONにしてください。")
    else:
        print("\n⏰ タイムアウト（60秒）。もう一度実行してください。")

if __name__ == "__main__":
    main()
