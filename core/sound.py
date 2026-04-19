"""
通知サウンドマネージャー

macOS の afplay コマンドを使用してシステムサウンドを再生します。
再生はデーモンスレッドで行い、メインスレッドをブロックしません。
"""
from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── システムサウンドパス ──────────────────────────────────────

SOUND_GREETING: str = "/System/Library/Sounds/Glass.aiff"
SOUND_RESPONSE: str = "/System/Library/Sounds/Pop.aiff"
SOUND_ERROR: str = "/System/Library/Sounds/Basso.aiff"
SOUND_AUTONOMOUS: str = "/System/Library/Sounds/Tink.aiff"
SOUND_ALERT: str = "/System/Library/Sounds/Sosumi.aiff"


# ─── サウンドマネージャー ─────────────────────────────────────


class SoundManager:
    """macOS システムサウンドの再生管理"""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled: bool = enabled

    @property
    def enabled(self) -> bool:
        """サウンドが有効かどうか"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """サウンドの有効/無効を切り替える"""
        self._enabled = value
        logger.debug("サウンド %s", "有効" if value else "無効")

    def play_greeting(self) -> None:
        """挨拶サウンドを再生する"""
        self._play(SOUND_GREETING)

    def play_response(self) -> None:
        """応答サウンドを再生する"""
        self._play(SOUND_RESPONSE)

    def play_error(self) -> None:
        """エラーサウンドを再生する"""
        self._play(SOUND_ERROR)

    def play_autonomous(self) -> None:
        """自律行動サウンドを再生する"""
        self._play(SOUND_AUTONOMOUS)

    def play_alert(self) -> None:
        """警告サウンドを再生する"""
        self._play(SOUND_ALERT)

    def _play(self, path: str) -> None:
        """指定パスのサウンドファイルをデーモンスレッドで再生する

        Args:
            path: サウンドファイルの絶対パス
        """
        if not self._enabled:
            return

        if not Path(path).is_file():
            logger.warning("サウンドファイルが見つかりません: %s", path)
            return

        thread = threading.Thread(
            target=self._play_sync,
            args=(path,),
            daemon=True,
        )
        thread.start()

    @staticmethod
    def _play_sync(path: str) -> None:
        """サウンドファイルを同期的に再生する（スレッド内で使用）"""
        try:
            subprocess.Popen(
                ["afplay", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("afplay コマンドが見つかりません（macOS 以外の環境）")
        except OSError:
            logger.exception("サウンド再生エラー: %s", path)
