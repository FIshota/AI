"""
リリースチェックリストスクリプト

バージョン確認、pytest 実行、ベンチマーク、整合性チェック、
CHANGELOG 生成を順に実行し、リリース可否のサマリーを表示する。
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent


def _run_cmd(cmd: List[str], timeout: int = 120) -> Tuple[bool, str]:
    """コマンドを実行して (成功?, 出力) を返す。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(BASE_DIR),
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            output += "\n" + result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "タイムアウト"
    except FileNotFoundError:
        return False, f"コマンドが見つかりません: {cmd[0]}"


def check_version() -> Tuple[bool, str]:
    """settings.json のバージョンを確認する。"""
    settings_path = BASE_DIR / "config" / "settings.json"
    if not settings_path.exists():
        return False, "config/settings.json が見つかりません"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        version = data.get("version", "")
        if not version:
            return False, "version フィールドが未設定"
        return True, f"バージョン: {version}"
    except Exception as exc:
        return False, f"設定読み込みエラー: {exc}"


def run_pytest() -> Tuple[bool, str]:
    """pytest を実行する。"""
    ok, output = _run_cmd([sys.executable, "-m", "pytest", "-x", "-q", "--tb=short"])
    return ok, output


def run_benchmark() -> Tuple[bool, str]:
    """品質ベンチマーク結果の存在を確認する。"""
    bench_dir = BASE_DIR / "data" / "benchmarks"
    if not bench_dir.exists():
        return False, "data/benchmarks/ が見つかりません"
    files = list(bench_dir.glob("benchmark_*.json"))
    if not files:
        return False, "ベンチマーク結果がありません"
    latest = max(files, key=lambda f: f.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        score = data.get("overall_score", 0)
        ok = score >= 50
        return ok, f"最新スコア: {score} ({latest.name})"
    except Exception as exc:
        return False, f"ベンチマーク読み込みエラー: {exc}"


def check_integrity() -> Tuple[bool, str]:
    """重要ファイルの存在を確認する。"""
    required_files = [
        "config/settings.json",
        "core/ai_chan.py",
        "core/emotion.py",
        "core/memory.py",
        "core/llm.py",
        "ui/desktop_pet.py",
        "main.py",
    ]
    missing: List[str] = []
    for f in required_files:
        if not (BASE_DIR / f).exists():
            missing.append(f)
    if missing:
        return False, f"不足: {', '.join(missing)}"
    return True, f"全 {len(required_files)} ファイル確認済み"


def generate_changelog() -> Tuple[bool, str]:
    """CHANGELOG を生成する。"""
    try:
        from scripts.gen_changelog import generate_changelog as gen
        md = gen(BASE_DIR)
        lines = md.strip().splitlines()
        return True, f"CHANGELOG 生成完了 ({len(lines)} 行)"
    except Exception as exc:
        return False, f"CHANGELOG 生成エラー: {exc}"


# ── メイン ──────────────────────────────────────────────

CHECKLIST = [
    ("バージョン確認", check_version),
    ("テスト実行", run_pytest),
    ("品質ベンチマーク", run_benchmark),
    ("整合性チェック", check_integrity),
    ("CHANGELOG 生成", generate_changelog),
]


def run_release_checklist() -> int:
    """リリースチェックリストを実行し、失敗数を返す。"""
    print("=" * 50)
    print("  リリースチェックリスト")
    print("=" * 50)
    print()

    failures = 0
    results: List[Tuple[str, bool, str]] = []

    for label, fn in CHECKLIST:
        print(f"  [{label}] 実行中...")
        try:
            ok, msg = fn()
        except Exception as exc:
            ok, msg = False, f"例外: {exc}"
        results.append((label, ok, msg))
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        # 長い出力は最初の5行に制限
        short_msg = "\n".join(msg.splitlines()[:5])
        print(f"    [{status}] {short_msg}")
        print()

    print("-" * 50)
    print("  サマリー:")
    for label, ok, msg in results:
        mark = "[OK]" if ok else "[NG]"
        first_line = msg.splitlines()[0] if msg else ""
        print(f"    {mark} {label}: {first_line}")
    print()

    if failures == 0:
        print("  リリース準備完了!")
    else:
        print(f"  {failures} 項目が失敗 - 修正が必要です")
    return failures


def main() -> None:
    failures = run_release_checklist()
    sys.exit(1 if failures > 0 else 0)


if __name__ == "__main__":
    main()
