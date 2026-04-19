"""
10 ポイント診断スクリプト

アイちゃん環境の健全性を確認するための診断ツール。
Python バージョン、Tkinter、llama_cpp、モデルファイル、データディレクトリ、
SQLite、暗号化キー、パッケージ、ディスク容量、メモリを検査する。
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import platform
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent

# ── カラー出力ユーティリティ ────────────────────────────


def _supports_color() -> bool:
    """端末がカラー出力に対応しているか判定する。"""
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


_COLOR = _supports_color()


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m" if _COLOR else text


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m" if _COLOR else text


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m" if _COLOR else text


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _COLOR else text


# ── 診断項目 ────────────────────────────────────────────


def check_python_version() -> Tuple[bool, str]:
    """1. Python バージョン (>= 3.9)"""
    ver = sys.version_info
    ok = ver >= (3, 9)
    msg = f"Python {ver.major}.{ver.minor}.{ver.micro}"
    if not ok:
        msg += " (3.9 以上が必要)"
    return ok, msg


def check_tkinter() -> Tuple[bool, str]:
    """2. Tkinter が利用可能か"""
    try:
        import tkinter as tk
        root = tk.Tk()
        tcl_ver = root.tk.eval("info patchlevel")
        root.destroy()
        return True, f"Tkinter OK (Tcl/Tk {tcl_ver})"
    except Exception as exc:
        return False, f"Tkinter 利用不可: {exc}"


def check_llama_cpp() -> Tuple[bool, str]:
    """3. llama-cpp-python が利用可能か"""
    try:
        import llama_cpp  # type: ignore[import-untyped]
        ver = getattr(llama_cpp, "__version__", "unknown")
        return True, f"llama-cpp-python {ver}"
    except ImportError:
        return False, "llama-cpp-python が見つかりません"


def check_model_file() -> Tuple[bool, str]:
    """4. モデルファイルが存在するか"""
    settings_path = BASE_DIR / "config" / "settings.json"
    if not settings_path.exists():
        return False, "config/settings.json が見つかりません"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        model_dir = settings.get("llm", {}).get("model_path", "models/")
        model_file = settings.get("llm", {}).get("model_file", "")
        full_path = BASE_DIR / model_dir / model_file
        if full_path.exists():
            size_mb = full_path.stat().st_size / (1024 * 1024)
            return True, f"モデル: {model_file} ({size_mb:.0f} MB)"
        return False, f"モデルファイルが見つかりません: {full_path}"
    except Exception as exc:
        return False, f"設定読み込みエラー: {exc}"


def check_data_dir() -> Tuple[bool, str]:
    """5. データディレクトリが存在するか"""
    data_dir = BASE_DIR / "data"
    if data_dir.is_dir():
        files = list(data_dir.iterdir())
        return True, f"data/ ({len(files)} ファイル)"
    return False, "data/ ディレクトリが見つかりません"


def check_sqlite() -> Tuple[bool, str]:
    """6. SQLite が動作するか"""
    try:
        ver = sqlite3.sqlite_version
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.close()
        return True, f"SQLite {ver}"
    except Exception as exc:
        return False, f"SQLite エラー: {exc}"


def check_encryption_key() -> Tuple[bool, str]:
    """7. 暗号化キーファイルが存在するか"""
    key_path = BASE_DIR / "data" / ".key"
    if key_path.exists():
        size = key_path.stat().st_size
        return True, f"暗号化キー: {size} bytes"
    return False, "暗号化キーファイル (data/.key) が見つかりません"


def check_packages() -> Tuple[bool, str]:
    """8. 必要パッケージのインストール状況"""
    required = ["PIL", "numpy", "yaml"]
    optional = ["whisper", "pyaudio", "requests"]
    missing: List[str] = []
    installed: List[str] = []

    for pkg in required:
        try:
            importlib.import_module(pkg)
            installed.append(pkg)
        except ImportError:
            missing.append(pkg)

    opt_count = 0
    for pkg in optional:
        try:
            importlib.import_module(pkg)
            opt_count += 1
        except ImportError:
            pass

    if missing:
        return False, f"不足: {', '.join(missing)} (オプション: {opt_count}/{len(optional)})"
    return True, f"必須パッケージ OK (オプション: {opt_count}/{len(optional)})"


def check_disk_space() -> Tuple[bool, str]:
    """9. ディスク空き容量"""
    try:
        usage = shutil.disk_usage(str(BASE_DIR))
        free_gb = usage.free / (1024 ** 3)
        ok = free_gb > 1.0
        return ok, f"ディスク空き: {free_gb:.1f} GB"
    except Exception as exc:
        return False, f"ディスク情報取得エラー: {exc}"


def check_memory() -> Tuple[bool, str]:
    """10. メモリ使用状況"""
    try:
        import resource
        usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS は bytes, Linux は KB
        if platform.system() == "Darwin":
            usage_mb = usage_kb / (1024 * 1024)
        else:
            usage_mb = usage_kb / 1024
        return True, f"プロセスメモリ: {usage_mb:.0f} MB"
    except ImportError:
        return True, "メモリ情報: resource モジュール非対応"
    except Exception as exc:
        return False, f"メモリ情報取得エラー: {exc}"


# ── メイン ──────────────────────────────────────────────

ALL_CHECKS = [
    ("Python バージョン", check_python_version),
    ("Tkinter", check_tkinter),
    ("llama-cpp-python", check_llama_cpp),
    ("モデルファイル", check_model_file),
    ("データディレクトリ", check_data_dir),
    ("SQLite", check_sqlite),
    ("暗号化キー", check_encryption_key),
    ("パッケージ", check_packages),
    ("ディスク容量", check_disk_space),
    ("メモリ", check_memory),
]


def run_diagnostics() -> int:
    """全診断項目を実行して結果を表示する。失敗数を返す。"""
    print(_bold("=" * 50))
    print(_bold("  アイちゃん環境診断"))
    print(_bold("=" * 50))
    print()

    failures = 0
    for i, (label, fn) in enumerate(ALL_CHECKS, 1):
        try:
            ok, msg = fn()
        except Exception as exc:
            ok, msg = False, f"例外: {exc}"

        if ok:
            status = _green("PASS")
        else:
            status = _red("FAIL")
            failures += 1

        print(f"  [{status}] {i:2d}. {label}")
        print(f"       {msg}")
        print()

    print(_bold("-" * 50))
    if failures == 0:
        print(_green(f"  全 {len(ALL_CHECKS)} 項目 PASS"))
    else:
        print(_yellow(f"  {failures}/{len(ALL_CHECKS)} 項目が FAIL"))
    print()
    return failures


def main() -> None:
    failures = run_diagnostics()
    sys.exit(1 if failures > 0 else 0)


if __name__ == "__main__":
    main()
