#!/usr/bin/env python3
"""
アイ - エントリーポイント
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import argparse
from pathlib import Path

# プロジェクトルートをパスに追加
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# B10 fix: logger を最初に定義（dotenv ブロックより前）
logger = logging.getLogger(__name__)

# .env ファイルから環境変数をロード（存在する場合）
try:
    from dotenv import load_dotenv
    _env_file = BASE_DIR / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
        logger.debug(".env ファイルをロードしました: %s", _env_file)
except ImportError:
    pass  # python-dotenv 未インストール時はスキップ


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


def _ensure_runtime_dirs(base_dir: Path) -> None:
    """Phase 0: data/, logs/ 等が無い状態でも起動できるよう空ディレクトリを用意する。

    記憶切り離し (Phase B) 後の新生起動 / CI / 公開デモ での
    "記憶ゼロから動く ai-chan" を保証する最小限の土台整備。
    personality/ はアーカイブ復元でしか作らない方針なので除外。
    """
    for d in ("data", "logs", "output", "reports", "backups", "models"):
        (base_dir / d).mkdir(parents=True, exist_ok=True)


def _configure_logging(base_dir: Path) -> None:
    """Item #61: RotatingFileHandler によるログローテーション"""
    from logging.handlers import RotatingFileHandler

    log_dir = base_dir / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # ファイルハンドラ (100KB, 5世代)
    fh = RotatingFileHandler(
        str(log_path), maxBytes=100_000, backupCount=5, encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    # コンソールハンドラ
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root.addHandler(ch)


def _run_startup_checks(base_dir: Path) -> bool:
    """Item #64: 起動時の自己診断。致命的問題があれば False を返す。"""
    issues: list[str] = []

    # モデルファイル存在確認
    settings_path = base_dir / "config" / "settings.json"
    if settings_path.exists():
        try:
            cfg = json.loads(settings_path.read_text(encoding="utf-8"))
            model_dir = base_dir / cfg.get("llm", {}).get("model_path", "models")
            model_file = cfg.get("llm", {}).get("model_file", "")
            if model_file and not (model_dir / model_file).exists():
                issues.append(f"モデルファイルが見つかりません: {model_dir / model_file}")
        except Exception:
            issues.append("settings.json の読み込みに失敗しました")
    else:
        issues.append("config/settings.json が存在しません")

    # data/ の書き込みテスト
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    test_file = data_dir / ".write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
    except OSError:
        issues.append("data/ ディレクトリに書き込みできません")

    # SQLite DB 接続テスト
    import sqlite3
    db_path = data_dir / "memories.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            conn.close()
        except sqlite3.Error as e:
            issues.append(f"データベースエラー: {e}")

    # 暗号鍵の検証
    key_path = data_dir / ".key"
    if key_path.exists():
        try:
            from utils.crypto import load_or_create_key
            load_or_create_key(str(key_path))
        except Exception as e:
            issues.append(f"暗号鍵の読み込みに失敗: {e}")

    if issues:
        for issue in issues:
            logger.warning("[起動診断] %s", issue)
            print(f"  ⚠ {issue}", flush=True)
    else:
        logger.info("[起動診断] すべてのチェックに合格しました")

    # 致命的エラーはモデル不在のみ — 他は警告で続行
    return True


def _show_enhanced_status(base_dir: Path) -> None:
    """Item #70: 拡張ステータス表示"""
    import resource
    import sqlite3

    data_dir = base_dir / "data"
    status: dict = {}

    # メモリ使用量
    usage = resource.getrusage(resource.RUSAGE_SELF)
    status["memory_mb"] = round(usage.ru_maxrss / (1024 * 1024), 1)

    # DB サイズ
    db_path = data_dir / "memories.db"
    if db_path.exists():
        status["db_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)
        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.close()
            status["total_memories"] = count
        except Exception:
            status["total_memories"] = "N/A"
    else:
        status["db_size_mb"] = 0
        status["total_memories"] = 0

    # 最終会話時刻
    log_path = data_dir / "conversation_log.jsonl"
    if log_path.exists():
        try:
            last_line = ""
            with open(log_path, "rb") as f:
                f.seek(0, 2)
                pos = f.tell()
                while pos > 0:
                    pos -= 1
                    f.seek(pos)
                    if f.read(1) == b"\n" and pos < f.seek(0, 2) - 1:
                        f.seek(pos + 1)
                        last_line = f.readline().decode("utf-8", errors="replace")
                        break
                if not last_line:
                    f.seek(0)
                    for line in f:
                        last_line = line.decode("utf-8", errors="replace")
            if last_line.strip():
                entry = json.loads(last_line)
                status["last_conversation"] = entry.get("timestamp", "不明")
        except Exception:
            status["last_conversation"] = "不明"
    else:
        status["last_conversation"] = "会話ログなし"

    # ロックファイル (起動時刻推定)
    lock_path = data_dir / "aichan.lock"
    if lock_path.exists():
        import time
        mtime = lock_path.stat().st_mtime
        uptime_sec = time.time() - mtime
        hours = int(uptime_sec // 3600)
        mins = int((uptime_sec % 3600) // 60)
        status["uptime"] = f"{hours}時間{mins}分" if hours else f"{mins}分"
    else:
        status["uptime"] = "停止中"

    # モデル状態
    settings_path = base_dir / "config" / "settings.json"
    if settings_path.exists():
        cfg = json.loads(settings_path.read_text(encoding="utf-8"))
        model_file = cfg.get("llm", {}).get("model_file", "")
        model_dir = base_dir / cfg.get("llm", {}).get("model_path", "models")
        status["model"] = model_file
        status["model_loaded"] = (model_dir / model_file).exists() if model_file else False

    print(json.dumps(status, ensure_ascii=False, indent=2))


# ────────────────────────────────────────────────────────────
# Item #14: Graceful shutdown
# ────────────────────────────────────────────────────────────
_ai_instance = None  # グローバル参照 (shutdown 用)


def _graceful_shutdown(signum: int, frame: object) -> None:
    """SIGTERM / SIGINT でのクリーンアップ"""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info("シグナル %s を受信。クリーンアップ中…", sig_name)
    print(f"\n[main] {sig_name} を受信しました。安全に終了します…", flush=True)

    if _ai_instance is not None:
        try:
            # メモリ保存
            if hasattr(_ai_instance, "memory"):
                _ai_instance.memory.close()
            # ThreadPoolExecutor シャットダウン
            if hasattr(_ai_instance, "_executor"):
                _ai_instance._executor.shutdown(wait=False)
        except Exception as e:
            logger.error("クリーンアップ中にエラー: %s", e)

    # ロックファイル解放
    global _LOCK_FILE_HANDLE
    if _LOCK_FILE_HANDLE is not None:
        try:
            _LOCK_FILE_HANDLE.close()
        except Exception:
            pass

    sys.exit(0)


def _run_voice_activation(base_dir: Path) -> None:
    """
    呼びかけ起動モード: ウェイクワードで AiChan を起こし、
    ハンズフリー音声会話ループに入る。
    """
    print("=== アイ 呼びかけ起動モード ===", flush=True)

    # 診断ログを必ず見えるようにする
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("core.wake_word").setLevel(logging.INFO)
    logging.getLogger("core.voice_loop").setLevel(logging.INFO)

    # 事前チェック
    print("\n[診断] 依存関係を確認中...", flush=True)
    try:
        import vosk  # noqa: F401
        print("  ✓ vosk インストール済み", flush=True)
    except ImportError:
        print("  ✗ vosk が未インストールです。`pip install vosk` を実行してください。", flush=True)
        return
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        print(f"  ✓ sounddevice OK (入力デバイス数: {len(input_devices)})", flush=True)
        default_in = sd.default.device[0] if sd.default.device else None
        if default_in is not None:
            print(f"    デフォルト入力: {devices[default_in]['name']}", flush=True)
    except Exception as e:
        print(f"  ✗ sounddevice 異常: {e}", flush=True)
        return

    vosk_model = base_dir / "models" / "vosk-small-ja"
    if vosk_model.exists():
        print(f"  ✓ Vosk モデル: {vosk_model}", flush=True)
    else:
        print(f"  ✗ Vosk モデルが見つかりません: {vosk_model}", flush=True)
        print(f"    ダウンロード: https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip", flush=True)
        return

    # settings.json ロード
    try:
        with open(base_dir / "config" / "settings.json", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception as e:
        print(f"[ERROR] settings.json 読み込み失敗: {e}", flush=True)
        return

    va_cfg = settings.get("voice_activation", {})
    if not va_cfg.get("enabled", False):
        # --voice 指定時は一時的に enabled=true として扱う
        va_cfg["enabled"] = True
        settings["voice_activation"] = va_cfg
        print("[info] 呼びかけ起動を一時的に有効化しました（--voice フラグ）", flush=True)

    # AiChan 初期化
    from core.ai_chan import AiChan
    print("[info] アイを起動中...", flush=True)
    ai = AiChan(base_dir=str(base_dir), settings=settings)

    # Voice loop + wake word
    from core.voice_loop import VoiceLoop
    from core.wake_word import create_wake_word_detector

    voice_loop = VoiceLoop(
        ai_chan=ai,
        tts=getattr(ai, "tts", None),
        stt=getattr(ai, "stt", None),
        config=settings,
    )

    def _on_wake(trigger_word: str) -> None:
        print(f"\n🔔 呼びかけ検出: 『{trigger_word}』", flush=True)
        voice_loop.wake(trigger_word)

    detector = create_wake_word_detector(
        config=settings, on_detected=_on_wake, base_dir=base_dir
    )
    if detector is None:
        print("[ERROR] ウェイクワード検出器を作れませんでした。", flush=True)
        print("        settings.json の voice_activation を確認してください。", flush=True)
        return

    detector.start()
    words = va_cfg.get("wake_words", ["アイちゃん"])
    print(f"\n🎤 呼びかけ待機中: {words}", flush=True)
    print("    （Ctrl+C で終了）", flush=True)

    try:
        while detector.is_running:
            signal.pause() if hasattr(signal, "pause") else __import__("time").sleep(1)
    except KeyboardInterrupt:
        print("\n[info] 停止中...", flush=True)
    finally:
        detector.stop()
        voice_loop.sleep()
        print("[info] 終了しました。", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="アイ - ローカルAIパートナー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方:
  python main.py              通常起動（CLI）
  python main.py --status     状態確認のみ
  python main.py --copy /Volumes/USB  USBにコピー
  python main.py --diagnose   起動診断のみ
        """,
    )
    parser.add_argument("--desktop", action="store_true", help="デスクトップペットモードで起動")
    parser.add_argument("--web", action="store_true", help="Web API サーバーモードで起動（iPhone対応）")
    parser.add_argument("--web-port", type=int, default=8721, help="Web API のポート番号（デフォルト: 8721）")
    parser.add_argument("--voice", action="store_true", help="呼びかけ起動モード（ウェイクワード + ハンズフリー音声対話）")
    parser.add_argument("--status", action="store_true", help="拡張ステータスを表示して終了")
    parser.add_argument("--copy", metavar="DEST", help="指定先にアイをコピー")
    parser.add_argument("--diagnose", action="store_true", help="起動診断のみ実行")
    parser.add_argument("--base-dir", default=str(BASE_DIR), help="ベースディレクトリ（デフォルト: スクリプトと同じ場所）")
    parser.add_argument("--restore-memory", metavar="ARCHIVE_DIR",
                        help="記憶アーカイブから復元してから起動（家族モード）")
    parser.add_argument("--smoke-test", action="store_true",
                        help="主要モジュールの import のみ行い終了（CI/検証用）")

    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    # Phase 0 切り離し対応: --restore-memory があればアーカイブから復元
    if args.restore_memory:
        print(f"[main] 記憶を復元中: {args.restore_memory}", flush=True)
        import subprocess
        r = subprocess.run(
            [sys.executable, str(base_dir / "scripts" / "restore_memory.py"),
             "--from", args.restore_memory],
            cwd=str(base_dir),
        )
        if r.returncode != 0:
            print("[main] 復元に失敗しました。起動を中止します。", flush=True)
            return

    # Phase 0 切り離し対応: data/ が無ければ空で自動初期化（新生モード）
    _ensure_runtime_dirs(base_dir)

    # smoke test: 主要モジュールの import だけ確認して終了
    if args.smoke_test:
        print("[smoke] importing core modules ...", flush=True)
        from core import llm  # noqa: F401
        from bench import runner  # noqa: F401
        print(f"[smoke] model_family default: {__import__('core.llm', fromlist=['default_model_family']).default_model_family()}")
        print("[smoke] ✓ OK", flush=True)
        return

    # Item #61: ログローテーション設定
    _configure_logging(base_dir)

    # Item #14: シグナルハンドラ登録
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    # Item #64: 起動時自己診断
    if args.diagnose:
        print("=== アイちゃん起動診断 ===", flush=True)
        _run_startup_checks(base_dir)
        return

    if args.web:
        _run_startup_checks(base_dir)
        from web_main import run_web_server
        run_web_server(base_dir=base_dir, port=args.web_port)
        return

    if args.voice:
        _run_startup_checks(base_dir)
        _run_voice_activation(base_dir)
        return

    if args.desktop:
        _check_python_environment()
        if not _acquire_single_instance_lock(base_dir):
            print("[main] アイは既に起動しています。二重起動を防ぎました。", flush=True)
            return
        _run_startup_checks(base_dir)
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
        _show_enhanced_status(base_dir)
        return

    # 通常のCLI起動
    _run_startup_checks(base_dir)
    from ui.cli import run_cli
    run_cli(base_dir=base_dir)


if __name__ == "__main__":
    main()
