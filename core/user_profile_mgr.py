"""
マルチユーザープロファイル管理

data/profiles/{name}/ 配下にユーザーごとの記憶DB・感情履歴を保持し、
プロファイルの作成・切り替え・一覧・削除を提供します。
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── デフォルト設定 ───────────────────────────────────────────

PROFILES_DIR: Path = Path("data/profiles")
MEMORIES_DB_NAME: str = "memories.db"
EMOTION_HISTORY_NAME: str = "emotion_history.json"
PROFILE_META_NAME: str = "profile.json"


# ─── プロファイルマネージャー ──────────────────────────────────


class UserProfileManager:
    """マルチユーザープロファイルの管理"""

    def __init__(self, profiles_dir: Optional[Path] = None) -> None:
        self._profiles_dir: Path = profiles_dir or PROFILES_DIR
        self._current_name: Optional[str] = None
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str) -> Path:
        """新規プロファイルを作成する

        Args:
            name: プロファイル名

        Returns:
            作成されたプロファイルディレクトリのパス

        Raises:
            ValueError: 名前が空または不正な場合
            FileExistsError: 既に存在する場合
        """
        validated_name: str = self._validate_name(name)
        profile_dir: Path = self._profiles_dir / validated_name

        if profile_dir.exists():
            raise FileExistsError(
                f"プロファイルが既に存在します: {validated_name}"
            )

        profile_dir.mkdir(parents=True, exist_ok=True)

        emotion_path: Path = profile_dir / EMOTION_HISTORY_NAME
        emotion_path.write_text("[]", encoding="utf-8")

        meta: Dict[str, Any] = {
            "name": validated_name,
            "created": True,
        }
        meta_path: Path = profile_dir / PROFILE_META_NAME
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("プロファイル作成: %s (%s)", validated_name, profile_dir)
        return profile_dir

    def switch(self, name: str) -> Path:
        """アクティブプロファイルを切り替える

        Args:
            name: 切り替え先のプロファイル名

        Returns:
            プロファイルディレクトリのパス

        Raises:
            FileNotFoundError: プロファイルが存在しない場合
        """
        validated_name: str = self._validate_name(name)
        profile_dir: Path = self._profiles_dir / validated_name

        if not profile_dir.is_dir():
            raise FileNotFoundError(
                f"プロファイルが見つかりません: {validated_name}"
            )

        self._current_name = validated_name
        logger.info("プロファイル切り替え: %s", validated_name)
        return profile_dir

    def list_profiles(self) -> List[str]:
        """全プロファイル名を返す

        Returns:
            プロファイル名のリスト（ソート済み）
        """
        if not self._profiles_dir.is_dir():
            return []

        names: List[str] = []
        for path in sorted(self._profiles_dir.iterdir()):
            if path.is_dir() and not path.name.startswith("."):
                names.append(path.name)

        return names

    def current(self) -> Optional[str]:
        """現在のアクティブプロファイル名を返す

        Returns:
            プロファイル名、または未選択なら None
        """
        return self._current_name

    def current_dir(self) -> Optional[Path]:
        """現在のアクティブプロファイルディレクトリを返す

        Returns:
            パス、または未選択なら None
        """
        if self._current_name is None:
            return None
        return self._profiles_dir / self._current_name

    def delete(self, name: str) -> None:
        """プロファイルを削除する

        Args:
            name: 削除するプロファイル名

        Raises:
            FileNotFoundError: プロファイルが存在しない場合
            ValueError: 現在アクティブなプロファイルを削除しようとした場合
        """
        validated_name: str = self._validate_name(name)
        profile_dir: Path = self._profiles_dir / validated_name

        if not profile_dir.is_dir():
            raise FileNotFoundError(
                f"プロファイルが見つかりません: {validated_name}"
            )

        if validated_name == self._current_name:
            raise ValueError(
                f"アクティブなプロファイルは削除できません: {validated_name}"
            )

        shutil.rmtree(str(profile_dir))
        logger.info("プロファイル削除: %s", validated_name)

    def get_db_path(self, name: Optional[str] = None) -> Path:
        """指定プロファイル（またはカレント）の記憶DB パスを返す

        Args:
            name: プロファイル名（省略時はカレント）

        Returns:
            memories.db のパス
        """
        target: str = name or self._current_name or ""
        if not target:
            return Path("data") / MEMORIES_DB_NAME
        return self._profiles_dir / target / MEMORIES_DB_NAME

    def get_emotion_path(self, name: Optional[str] = None) -> Path:
        """指定プロファイル（またはカレント）の感情履歴パスを返す

        Args:
            name: プロファイル名（省略時はカレント）

        Returns:
            emotion_history.json のパス
        """
        target: str = name or self._current_name or ""
        if not target:
            return Path("data") / EMOTION_HISTORY_NAME
        return self._profiles_dir / target / EMOTION_HISTORY_NAME

    @staticmethod
    def _validate_name(name: str) -> str:
        """プロファイル名をバリデーションする

        Args:
            name: プロファイル名

        Returns:
            検証済みの名前

        Raises:
            ValueError: 不正な名前の場合
        """
        stripped: str = name.strip()
        if not stripped:
            raise ValueError("プロファイル名が空です")

        forbidden_chars = set('/\\:*?"<>|')
        if any(c in forbidden_chars for c in stripped):
            raise ValueError(
                f"プロファイル名に使用できない文字が含まれています: {stripped}"
            )

        if stripped.startswith("."):
            raise ValueError(
                f"プロファイル名はドットで始められません: {stripped}"
            )

        return stripped
