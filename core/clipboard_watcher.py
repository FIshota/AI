"""
クリップボード監視システム（macOS専用）
コピーされたテキストを検出してアイに通知します。
settings.json の autonomous.clipboard_watch: true の場合のみ動作。
"""
from __future__ import annotations
import subprocess
import threading
import time

MIN_LENGTH    = 10     # 反応する最小文字数
MAX_LENGTH    = 3000   # 反応する最大文字数
COOLDOWN_SECS = 40     # 連続通知の抑制間隔（秒）
POLL_INTERVAL = 2.5    # ポーリング間隔（秒）


def _read_clipboard() -> str:
    """macOS の pbpaste でクリップボードを読む"""
    try:
        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2
        )
        return result.stdout
    except Exception:
        return ""


class ClipboardWatcher(threading.Thread):
    """
    バックグラウンドでクリップボードを監視し、
    テキストが変わったら callback(text) を呼び出します。
    """

    def __init__(self, callback, interval: float = POLL_INTERVAL):
        super().__init__(daemon=True, name="ClipboardWatcher")
        self._callback    = callback
        self._interval    = interval
        self._last_text   = _read_clipboard()   # 起動時の内容は無視
        self._last_fired  = 0.0
        self._running     = True

    def run(self):
        while self._running:
            time.sleep(self._interval)
            try:
                text = _read_clipboard()
                if (
                    text
                    and text != self._last_text
                    and MIN_LENGTH <= len(text) <= MAX_LENGTH
                    and time.time() - self._last_fired >= COOLDOWN_SECS
                ):
                    self._last_text  = text
                    self._last_fired = time.time()
                    self._callback(text)
                elif text != self._last_text:
                    # 内容は更新しておく（クールダウン中 or 長さ外でもリセット）
                    self._last_text = text
            except Exception as e:
                # 失敗を可視化（pbpaste権限エラーやコールバック例外を隠さない）
                print(f"[ClipboardWatcher] error: {e}", flush=True)

    def stop(self):
        self._running = False
