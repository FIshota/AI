"""
ロギング設定ユーティリティ

RotatingFileHandler を使ったログ設定を提供する。
100KB / 5 バックアップのローテーションで運用する。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# デフォルト設定
DEFAULT_MAX_BYTES = 100 * 1024   # 100 KB
DEFAULT_BACKUP_COUNT = 5
DEFAULT_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    base_dir: Path | str,
    *,
    log_file: str = "ai_chan.log",
    level: int = logging.INFO,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    console: bool = True,
    log_format: str = DEFAULT_LOG_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> logging.Logger:
    """プロジェクト全体のロギングを設定する。

    Parameters
    ----------
    base_dir:
        ログファイルの配置先ベースディレクトリ。
        ``{base_dir}/logs/{log_file}`` にファイルが作られる。
    log_file:
        ログファイル名。
    level:
        ログレベル。
    max_bytes:
        ローテーションのファイルサイズ上限。
    backup_count:
        保持するバックアップ数。
    console:
        True なら stdout にも出力する。
    log_format:
        ログフォーマット文字列。
    date_format:
        日時フォーマット文字列。

    Returns
    -------
    logging.Logger
        ルートロガー。
    """
    base_dir = Path(base_dir)
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file

    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 既存ハンドラをクリア（多重追加防止）
    root_logger.handlers.clear()

    # ファイルハンドラ（RotatingFileHandler）
    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # コンソールハンドラ
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    root_logger.info("ロギング設定完了: %s (max=%dKB, backups=%d)",
                     log_path, max_bytes // 1024, backup_count)
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """名前付きロガーを取得する。configure_logging() を先に呼ぶこと。"""
    return logging.getLogger(name)
