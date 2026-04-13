"""
macOS 通知エンジン（機能⑤）
osascript を使ってバナー通知を送ります。追加インストール不要・完全ローカル。
"""
from __future__ import annotations
import subprocess
import platform

IS_MAC = platform.system() == "Darwin"


def notify(title: str, message: str, subtitle: str = "") -> bool:
    """
    macOS 通知センターにバナーを表示する。
    戻り値: 送信成功なら True
    """
    if not IS_MAC:
        return False
    try:
        sub_part = f'subtitle "{_esc(subtitle)}" ' if subtitle else ""
        script = (
            f'display notification "{_esc(message)}" '
            f'with title "{_esc(title)}" '
            f'{sub_part}'
            f'sound name "Ping"'
        )
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=5
        )
        return True
    except Exception as e:
        print(f"[Notifier] エラー: {e}", flush=True)
        return False


def notify_ai(message: str) -> bool:
    """アイからの通知を送る"""
    return notify("アイ 💗", message)


def notify_battery(percent: int) -> bool:
    """バッテリー警告通知"""
    msg = f"バッテリーが {percent}% になったよ。充電しよう！"
    return notify("アイ - バッテリー警告", msg)


def notify_schedule(message: str) -> bool:
    """スケジュール通知"""
    return notify("アイ - リマインダー", message)


def _esc(text: str) -> str:
    """AppleScript 文字列用エスケープ"""
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
