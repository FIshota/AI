"""
プラグインアーキテクチャ

core/plugins/ ディレクトリから .py ファイルをスキャンし、
各プラグインの register(bus) 関数を呼び出してイベントバスに登録します。
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

from core.errors import PluginError
from core.event_bus import EventBus

logger = logging.getLogger(__name__)

# ─── プラグインディレクトリ ────────────────────────────────────

PLUGIN_DIR: Path = Path(__file__).resolve().parent / "plugins"


# ─── プラグインローダー ───────────────────────────────────────


class PluginLoader:
    """プラグインの検出・読み込み・管理を行うクラス"""

    def __init__(self, bus: EventBus, plugin_dir: Optional[Path] = None) -> None:
        self._bus: EventBus = bus
        self._plugin_dir: Path = plugin_dir or PLUGIN_DIR
        self._plugins: Dict[str, ModuleType] = {}

    def discover(self) -> List[str]:
        """プラグインディレクトリ内の .py ファイル名（拡張子なし）を返す

        Returns:
            発見されたプラグイン名のリスト
        """
        if not self._plugin_dir.is_dir():
            logger.warning("プラグインディレクトリが存在しません: %s", self._plugin_dir)
            return []

        names: List[str] = []
        for path in sorted(self._plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            names.append(path.stem)

        logger.info("プラグイン検出: %d 件 %s", len(names), names)
        return names

    def load_plugin(self, name: str) -> ModuleType:
        """指定名のプラグインを読み込み、register(bus) を呼び出す

        Args:
            name: プラグイン名（拡張子なし）

        Returns:
            読み込まれたモジュール

        Raises:
            PluginError: ファイルが見つからない、または register 関数がない場合
        """
        if name in self._plugins:
            logger.debug("プラグイン既読み込み済み: %s", name)
            return self._plugins[name]

        plugin_path: Path = self._plugin_dir / f"{name}.py"
        if not plugin_path.is_file():
            raise PluginError(
                f"プラグインファイルが見つかりません: {plugin_path}",
                details={"name": name, "path": str(plugin_path)},
            )

        try:
            spec = importlib.util.spec_from_file_location(
                f"core.plugins.{name}", str(plugin_path)
            )
            if spec is None or spec.loader is None:
                raise PluginError(
                    f"プラグインのインポート仕様を取得できません: {name}",
                    details={"name": name},
                )

            module: ModuleType = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except PluginError:
            raise
        except Exception as exc:
            raise PluginError(
                f"プラグイン読み込みエラー: {name}",
                details={"name": name, "error": str(exc)},
            ) from exc

        register_fn: Any = getattr(module, "register", None)
        if not callable(register_fn):
            raise PluginError(
                f"プラグインに register(bus) 関数がありません: {name}",
                details={"name": name},
            )

        try:
            register_fn(self._bus)
        except Exception as exc:
            raise PluginError(
                f"プラグイン登録エラー: {name}",
                details={"name": name, "error": str(exc)},
            ) from exc

        self._plugins[name] = module
        logger.info("プラグイン読み込み完了: %s", name)
        return module

    def load_all(self) -> Dict[str, ModuleType]:
        """検出された全プラグインを読み込む

        Returns:
            プラグイン名をキーとするモジュール辞書
        """
        names: List[str] = self.discover()
        for name in names:
            try:
                self.load_plugin(name)
            except PluginError:
                logger.exception("プラグイン読み込みスキップ: %s", name)

        return dict(self._plugins)

    def get_plugin(self, name: str) -> Optional[ModuleType]:
        """読み込み済みプラグインを取得する

        Args:
            name: プラグイン名

        Returns:
            モジュール、または未読み込みなら None
        """
        return self._plugins.get(name)

    @property
    def loaded_names(self) -> List[str]:
        """読み込み済みプラグイン名のリスト"""
        return list(self._plugins.keys())
