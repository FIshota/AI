"""
設定ファイルのホットリロード＋自動バックアップ

デーモンスレッドで settings.json の mtime を5秒ごとに監視し、
変更検出時にバックアップを作成して CONFIG_CHANGED イベントを発火します。
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from core.event_bus import CONFIG_CHANGED, EventBus

logger = logging.getLogger(__name__)

# ─── デフォルト設定 ───────────────────────────────────────────

DEFAULT_SETTINGS_PATH: Path = Path("config/settings.json")
CHECK_INTERVAL_SEC: float = 5.0


# ─── 設定ウォッチャー ─────────────────────────────────────────


class ConfigWatcher:
    """settings.json を監視し変更時にイベントを発火するウォッチャー"""

    def __init__(
        self,
        bus: EventBus,
        settings_path: Optional[Path] = None,
        interval: float = CHECK_INTERVAL_SEC,
    ) -> None:
        self._bus: EventBus = bus
        self._settings_path: Path = settings_path or DEFAULT_SETTINGS_PATH
        self._interval: float = interval
        self._last_mtime: float = self._get_mtime()
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()

    def start(self) -> None:
        """監視を開始する（デーモンスレッド）"""
        if self._running:
            logger.warning("ConfigWatcher は既に起動中です")
            return

        self._running = True
        self._stop_event.clear()
        self._last_mtime = self._get_mtime()

        self._thread = threading.Thread(
            target=self._watch_loop,
            name="config-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "設定監視開始: %s (間隔 %.1f秒)",
            self._settings_path,
            self._interval,
        )

    def stop(self) -> None:
        """監視を停止する"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1)
            self._thread = None

        logger.info("設定監視停止")

    def is_changed(self) -> bool:
        """現在の mtime が最後に記録した値と異なるか確認する"""
        current_mtime: float = self._get_mtime()
        return current_mtime != self._last_mtime

    def _watch_loop(self) -> None:
        """監視ループ（デーモンスレッドで実行）"""
        while not self._stop_event.is_set():
            try:
                if self.is_changed():
                    self._on_changed()
            except Exception:
                logger.exception("設定監視中のエラー")

            self._stop_event.wait(timeout=self._interval)

    def _on_changed(self) -> None:
        """変更検出時の処理：バックアップ作成 + イベント発火"""
        logger.info("設定ファイル変更検出: %s", self._settings_path)

        self._create_backup()
        self._last_mtime = self._get_mtime()
        self._bus.emit(CONFIG_CHANGED, path=str(self._settings_path))

    def _create_backup(self) -> None:
        """設定ファイルの .bak バックアップを作成する"""
        source: Path = self._settings_path
        if not source.is_file():
            return

        backup_path: Path = source.with_suffix(".json.bak")
        try:
            shutil.copy2(str(source), str(backup_path))
            logger.info("設定バックアップ作成: %s", backup_path)
        except OSError:
            logger.exception("バックアップ作成失敗: %s", backup_path)

    def _get_mtime(self) -> float:
        """設定ファイルの mtime を取得する（存在しない場合は 0.0）"""
        try:
            return self._settings_path.stat().st_mtime
        except OSError:
            return 0.0
