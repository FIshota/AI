"""
システムヘルスチェック

モデルファイル・DB接続・ディスク容量・メモリ使用量・パッケージ状態等を
診断し、各項目のステータスとメッセージを返します。
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# ─── ヘルスステータス ─────────────────────────────────────────

STATUS_OK: str = "ok"
STATUS_WARN: str = "warn"
STATUS_FAIL: str = "fail"


@dataclass(frozen=True)
class HealthStatus:
    """個別チェック項目の結果

    Attributes:
        status: "ok", "warn", "fail" のいずれか
        message: 状態を説明するメッセージ
    """

    status: str
    message: str


# ─── 閾値定数 ─────────────────────────────────────────────────

DISK_WARN_GB: float = 5.0
DISK_FAIL_GB: float = 1.0
MEMORY_WARN_PERCENT: float = 85.0
MEMORY_FAIL_PERCENT: float = 95.0

MODEL_DIR: Path = Path("models")
MEMORIES_DB: Path = Path("data/memories.db")
KEY_FILE: Path = Path("data/.key")


# ─── チェック関数群 ───────────────────────────────────────────


def check_model_files() -> HealthStatus:
    """モデルファイルの存在を確認する"""
    if not MODEL_DIR.is_dir():
        return HealthStatus(STATUS_FAIL, f"モデルディレクトリが存在しません: {MODEL_DIR}")

    gguf_files: List[Path] = list(MODEL_DIR.glob("*.gguf"))
    if not gguf_files:
        model_subdirs: List[Path] = [
            p for p in MODEL_DIR.iterdir() if p.is_dir()
        ]
        if not model_subdirs:
            return HealthStatus(STATUS_WARN, "モデルファイルが見つかりません")
        return HealthStatus(STATUS_OK, f"モデルディレクトリ検出: {len(model_subdirs)} 件")

    return HealthStatus(STATUS_OK, f"GGUFモデル検出: {len(gguf_files)} 件")


def check_database() -> HealthStatus:
    """記憶データベースへの接続を確認する"""
    if not MEMORIES_DB.is_file():
        return HealthStatus(STATUS_WARN, f"データベースが存在しません: {MEMORIES_DB}")

    try:
        conn = sqlite3.connect(str(MEMORIES_DB))
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM sqlite_master")
        table_count: int = cursor.fetchone()[0]
        conn.close()
        return HealthStatus(STATUS_OK, f"DB接続正常: テーブル数={table_count}")
    except sqlite3.Error as exc:
        return HealthStatus(STATUS_FAIL, f"DB接続エラー: {exc}")


def check_key_file() -> HealthStatus:
    """暗号化キーファイルの存在と権限を確認する"""
    if not KEY_FILE.is_file():
        return HealthStatus(STATUS_WARN, f"キーファイルが存在しません: {KEY_FILE}")

    stat = KEY_FILE.stat()
    mode_octal: str = oct(stat.st_mode)[-3:]
    if mode_octal not in ("400", "600"):
        return HealthStatus(
            STATUS_WARN,
            f"キーファイルの権限が緩すぎます: {mode_octal} (推奨: 400)",
        )

    return HealthStatus(STATUS_OK, f"キーファイル正常: 権限={mode_octal}")


def check_disk_space() -> HealthStatus:
    """ディスク空き容量を確認する"""
    try:
        usage = shutil.disk_usage("/")
        free_gb: float = usage.free / (1024 ** 3)

        if free_gb < DISK_FAIL_GB:
            return HealthStatus(
                STATUS_FAIL, f"ディスク容量不足: {free_gb:.1f}GB"
            )
        if free_gb < DISK_WARN_GB:
            return HealthStatus(
                STATUS_WARN, f"ディスク容量少なめ: {free_gb:.1f}GB"
            )
        return HealthStatus(STATUS_OK, f"ディスク空き: {free_gb:.1f}GB")
    except OSError as exc:
        return HealthStatus(STATUS_FAIL, f"ディスク確認エラー: {exc}")


def check_memory_usage() -> HealthStatus:
    """メモリ使用率を確認する（macOS / psutil なし）"""
    try:
        import resource

        usage_kb: int = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS: バイト単位, Linux: KB単位
        usage_mb: float = usage_kb / (1024 * 1024)
        if usage_mb < 1:
            usage_mb = usage_kb / 1024

        if usage_mb > 2048:
            return HealthStatus(
                STATUS_WARN,
                f"プロセスメモリ使用量が高め: {usage_mb:.0f}MB",
            )
        return HealthStatus(STATUS_OK, f"プロセスメモリ: {usage_mb:.0f}MB")
    except Exception as exc:
        return HealthStatus(STATUS_WARN, f"メモリ確認エラー: {exc}")


def check_required_packages() -> HealthStatus:
    """必須パッケージのインポートを確認する"""
    required: List[str] = ["pydantic", "sqlite3", "json", "pathlib"]
    missing: List[str] = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        return HealthStatus(
            STATUS_FAIL,
            f"必須パッケージが不足: {', '.join(missing)}",
        )
    return HealthStatus(STATUS_OK, f"全必須パッケージ利用可能: {len(required)} 件")


def check_data_directory() -> HealthStatus:
    """データディレクトリの存在と書き込み権限を確認する"""
    data_dir: Path = Path("data")
    if not data_dir.is_dir():
        return HealthStatus(STATUS_FAIL, "data/ ディレクトリが存在しません")

    if not os.access(str(data_dir), os.W_OK):
        return HealthStatus(STATUS_FAIL, "data/ ディレクトリに書き込み権限がありません")

    return HealthStatus(STATUS_OK, "data/ ディレクトリ正常")


# ─── メイン実行 ───────────────────────────────────────────────


def run() -> Dict[str, HealthStatus]:
    """全ヘルスチェックを実行する

    Returns:
        チェック名をキーとする HealthStatus の辞書
    """
    checks: Dict[str, Callable[[], HealthStatus]] = {
        "model_files": check_model_files,
        "database": check_database,
        "key_file": check_key_file,
        "disk_space": check_disk_space,
        "memory_usage": check_memory_usage,
        "required_packages": check_required_packages,
        "data_directory": check_data_directory,
    }

    results: Dict[str, HealthStatus] = {}
    for name, check_fn in checks.items():
        try:
            results[name] = check_fn()
        except Exception as exc:
            results[name] = HealthStatus(STATUS_FAIL, f"チェック例外: {exc}")
            logger.exception("ヘルスチェック例外: %s", name)

    ok_count: int = sum(1 for r in results.values() if r.status == STATUS_OK)
    total: int = len(results)
    logger.info("ヘルスチェック完了: %d/%d OK", ok_count, total)

    return results


def format_report(results: Dict[str, HealthStatus]) -> str:
    """ヘルスチェック結果をテキストレポートに整形する

    Args:
        results: run() の戻り値

    Returns:
        整形されたテキストレポート
    """
    status_icons: Dict[str, str] = {
        STATUS_OK: "[OK]",
        STATUS_WARN: "[WARN]",
        STATUS_FAIL: "[FAIL]",
    }

    lines: List[str] = ["── システムヘルスチェック ──"]
    for name, health in results.items():
        icon: str = status_icons.get(health.status, "[??]")
        lines.append(f"  {icon} {name}: {health.message}")

    return "\n".join(lines)
