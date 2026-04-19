"""
会話・記憶データのエクスポート

会話履歴・記憶・学習データを CSV / JSON 形式でファイルに出力します。
"""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── サポートフォーマット ──────────────────────────────────────

FORMAT_CSV: str = "csv"
FORMAT_JSON: str = "json"
SUPPORTED_FORMATS: tuple[str, ...] = (FORMAT_CSV, FORMAT_JSON)

# ─── デフォルトパス ───────────────────────────────────────────

DEFAULT_DB_PATH: Path = Path("data/memories.db")
DEFAULT_LEARNING_PATH: Path = Path("data/continuous_learning.json")


# ─── データエクスポーター ─────────────────────────────────────


class DataExporter:
    """会話・記憶・学習データのエクスポーター"""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        learning_path: Optional[Path] = None,
    ) -> None:
        self._db_path: Path = db_path or DEFAULT_DB_PATH
        self._learning_path: Path = learning_path or DEFAULT_LEARNING_PATH

    def export_conversations(
        self, output_path: Path, fmt: str = FORMAT_JSON
    ) -> int:
        """会話履歴をエクスポートする

        Args:
            output_path: 出力ファイルパス
            fmt: 出力フォーマット ("csv" or "json")

        Returns:
            エクスポートされたレコード数

        Raises:
            ValueError: フォーマットが不正な場合
            FileNotFoundError: DBが存在しない場合
        """
        self._validate_format(fmt)
        rows: List[Dict[str, Any]] = self._query_table("conversations")

        self._write_output(rows, output_path, fmt)
        logger.info(
            "会話エクスポート完了: %d 件 → %s (%s)",
            len(rows),
            output_path,
            fmt,
        )
        return len(rows)

    def export_memories(
        self, output_path: Path, fmt: str = FORMAT_JSON
    ) -> int:
        """記憶データをエクスポートする

        Args:
            output_path: 出力ファイルパス
            fmt: 出力フォーマット ("csv" or "json")

        Returns:
            エクスポートされたレコード数

        Raises:
            ValueError: フォーマットが不正な場合
            FileNotFoundError: DBが存在しない場合
        """
        self._validate_format(fmt)
        rows: List[Dict[str, Any]] = self._query_table("memories")

        self._write_output(rows, output_path, fmt)
        logger.info(
            "記憶エクスポート完了: %d 件 → %s (%s)",
            len(rows),
            output_path,
            fmt,
        )
        return len(rows)

    def export_learning(self, output_path: Path) -> int:
        """学習データをエクスポートする（JSON のみ）

        Args:
            output_path: 出力ファイルパス

        Returns:
            エクスポートされたレコード数
        """
        if not self._learning_path.is_file():
            logger.warning(
                "学習データファイルが存在しません: %s", self._learning_path
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("[]", encoding="utf-8")
            return 0

        raw: str = self._learning_path.read_text(encoding="utf-8")
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("学習データの JSON パースに失敗: %s", self._learning_path)
            data = []

        records: List[Any] = data if isinstance(data, list) else [data]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "学習データエクスポート完了: %d 件 → %s",
            len(records),
            output_path,
        )
        return len(records)

    # ─── 内部メソッド ─────────────────────────────────────────

    def _query_table(self, table_name: str) -> List[Dict[str, Any]]:
        """SQLite テーブルからレコードを辞書リストで取得する"""
        if not self._db_path.is_file():
            raise FileNotFoundError(
                f"データベースが見つかりません: {self._db_path}"
            )

        conn: sqlite3.Connection = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            # テーブルの存在チェック
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            if cursor.fetchone() is None:
                logger.warning("テーブルが存在しません: %s", table_name)
                return []

            cursor.execute(f"SELECT * FROM {table_name}")  # noqa: S608
            rows: List[Dict[str, Any]] = [dict(row) for row in cursor.fetchall()]
            return rows
        finally:
            conn.close()

    @staticmethod
    def _write_output(
        rows: List[Dict[str, Any]], output_path: Path, fmt: str
    ) -> None:
        """レコードをファイルに書き出す"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == FORMAT_JSON:
            output_path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        elif fmt == FORMAT_CSV:
            if not rows:
                output_path.write_text("", encoding="utf-8")
                return

            fieldnames: List[str] = list(rows[0].keys())
            buffer = StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            output_path.write_text(buffer.getvalue(), encoding="utf-8")

    @staticmethod
    def _validate_format(fmt: str) -> None:
        """フォーマットを検証する"""
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(
                f"未対応のフォーマット: {fmt} (対応: {SUPPORTED_FORMATS})"
            )
