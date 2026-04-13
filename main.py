#!/usr/bin/env python3
"""
アイ - エントリーポイント
"""
import os
import sys
import argparse
from pathlib import Path

# プロジェクトルートをパスに追加
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


# ────────────────────────────────────────────────────────────
# Python / Tk バージョンガード
#  - macOS CommandLineTools の Python 3.9 は Tk 8.5 を同梱しており、
#    overrideredirect(True) + 半透明のデスクトップペット表示が崩れる
#    （ウィンドウは生きているが中身が描画されない）。
#  - その場合は Python 3.13 を自動検出して再 exec する。
# ────────────────────────────────────────────────────────────
def _find_better_python() -> str | None:
    """llama_cpp と Tk 8.6 を備えた Python を探す"""
    candidates = [
        BASE_DIR / ".venv" / "bin" / "python3",
        BASE_DIR / "venv"  / "bin" / "python3",
        Path("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"),
        Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"),
        Path("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"),
        Path("/opt/homebrew/bin/python3.13"),
        Path("/opt/homebrew/bin/python3.12"),
        Path("/opt/homebrew/bin/python3"),
    ]
    import subprocess
    for p in candidates:
        if not p.exists():
            continue
        # 自分自身はスキップ
        try:
            if Path(sys.executable).resolve() == p.resolve():
                continue
        except OSError:
            continue
        try:
            r = subprocess.run(
                [str(p), "-c",
                 "import sys,tkinter; "
                 "assert tkinter.TkVersion >= 8.6; "
                 "import llama_cpp; "
                 "print('OK')"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and "OK" in r.stdout:
                return str(p)
        except Exception:
            continue
    return None


def _check_python_environment():
    """Tk 8.5 や古い Python で起動していたら 3.13 系へ再 exec"""
    import tkinter
    tk_ver = float(tkinter.TkVersion)
    py_ver = sys.version_info
    ok = (py_ver >= (3, 10)) and (tk_ver >= 8.6)
    if ok:
        return

    print(
        f"[main] ⚠️  この Python ({py_ver.major}.{py_ver.minor}, "
        f"Tk {tk_ver}) ではデスクトップペットが正常表示されません。",
        flush=True,
    )
    # 無限再 exec 防止
    if os.environ.get("AICHAN_REEXECED") == "1":
        print("[main] 再 exec しましたが依然として環境が不足しています。"
              "Python 3.13 系で実行してください。", flush=True)
        sys.exit(2)

    better = _find_better_python()
    if not better:
        print("[main] Tk 8.6 + llama_cpp を備えた Python 3.13 が見つかりません。\n"
              "       https://www.python.org/downloads/macos/ から 3.13 を入れてください。",
              flush=True)
        sys.exit(2)

    print(f"[main] → {better} で再起動します…", flush=True)
    env = dict(os.environ)
    env["AICHAN_REEXECED"] = "1"
    os.execve(better, [better, "-u", str(Path(__file__).resolve()), *sys.argv[1:]], env)


# ────────────────────────────────────────────────────────────
# シングルインスタンスロック（多重起動防止）
# ────────────────────────────────────────────────────────────
_LOCK_FILE_HANDLE = None  # モジュール存続中は握り続ける


def _acquire_single_instance_lock(base_dir: Path) -> bool:
    """fcntl.flock でペット多重起動を防ぐ。取得失敗時は False"""
    global _LOCK_FILE_HANDLE
    import fcntl
    lock_dir = base_dir / "data"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "aichan.lock"
    try:
        fh = open(lock_path, "w")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(os.getpid()))
        fh.flush()
        _LOCK_FILE_HANDLE = fh  # 握り続ける
        return True
    except (BlockingIOError, OSError):
        return False


def main():
    parser = argparse.ArgumentParser(
        description="アイ - ローカルAIパートナー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方:
  python main.py              通常起動（CLI）
  python main.py --status     状態確認のみ
  python main.py --copy /Volumes/USB  USBにコピー
        """,
    )
    parser.add_argument("--desktop", action="store_true", help="デスクトップペットモードで起動")
    parser.add_argument("--status", action="store_true", help="状態を表示して終了")
    parser.add_argument("--copy", metavar="DEST", help="指定先にアイをコピー")
    parser.add_argument("--base-dir", default=str(BASE_DIR), help="ベースディレクトリ（デフォルト: スクリプトと同じ場所）")

    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    if args.desktop:
        # デスクトップペット起動前に Python / Tk バージョンを確認
        _check_python_environment()
        # 多重起動防止
        if not _acquire_single_instance_lock(base_dir):
            print("[main] アイは既に起動しています。二重起動を防ぎました。", flush=True)
            return
        from ui.desktop_pet import run_desktop_pet
        run_desktop_pet(base_dir=base_dir)
        return

    if args.copy:
        from utils.portable import copy_to_portable
        print(f"アイを {args.copy} にコピーしています...")
        report = copy_to_portable(base_dir, args.copy)
        if report["success"]:
            print(f"✓ コピー完了！ {report['total_mb']} MB, {len(report['files_copied'])} ファイル")
        else:
            print(f"エラーが発生しました: {report['errors']}")
        return

    if args.status:
        from core.ai_chan import AiChan
        ai = AiChan(base_dir=base_dir)
        import json
        print(json.dumps(ai.get_status(), ensure_ascii=False, indent=2))
        return

    # 通常のCLI起動
    from ui.cli import run_cli
    run_cli(base_dir=base_dir)


if __name__ == "__main__":
    main()
