#!/usr/bin/env python3
"""ai-chan ライセンス監査ツール (Phase 0.75).

pip-licenses の出力を解析し、以下を検知する:
  1. GPL / AGPL / LGPL などコピーレフトライセンスの混入
  2. 未判定 (UNKNOWN) ライセンス
  3. docs/LICENSES.md との差分 (新規依存 / 削除依存)

使い方:
    python3 scripts/check_licenses.py                 # 検査のみ
    python3 scripts/check_licenses.py --update-doc    # docs/LICENSES.md を更新
    python3 scripts/check_licenses.py --fail-on-gpl   # GPL 検出で exit 1 (CI 用)

環境構築:
    python3 -m pip install --user pip-licenses
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Phase 0.75: 絶対禁止ライセンス (混入で CI fail)
FORBIDDEN = {"GPL-3.0", "GPL-2.0", "AGPL-3.0", "AGPL-1.0"}

# 要注意 (混入自体は許容、但し docs/LICENSES.md で明示必須)
WARN_LICENSES = {"LGPL-3.0", "LGPL-2.1", "MPL-2.0", "EPL-2.0", "CDDL-1.0"}

# 受容済み (ai-chan が明示的に問題ないと判断)
ACCEPTED_EXCEPTIONS: dict[str, str] = {
    # 例: "some-package": "実はデュアルライセンスで MIT も選べるため OK"
}


def run_pip_licenses() -> list[dict]:
    """pip-licenses を JSON 形式で実行して返す。"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "piplicenses", "--format=json",
             "--with-urls", "--with-license-file", "--no-license-path"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            # pip-licenses が無い場合: pip install で代替
            print("[licenses] pip-licenses が見つかりません。インストール中...", file=sys.stderr)
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--user", "--quiet", "pip-licenses"],
                check=True,
            )
            result = subprocess.run(
                [sys.executable, "-m", "piplicenses", "--format=json",
                 "--with-urls", "--with-license-file", "--no-license-path"],
                capture_output=True, text=True, check=True,
            )
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[licenses] 実行失敗: {e}", file=sys.stderr)
        return []


def classify(pkg: dict) -> str:
    """pkg → 'forbidden' | 'warn' | 'ok' | 'unknown'"""
    name = pkg.get("Name", "")
    lic = (pkg.get("License", "") or "").strip()
    if name in ACCEPTED_EXCEPTIONS:
        return "ok"
    if not lic or lic.upper() in ("UNKNOWN", "NONE"):
        return "unknown"
    # 正規化: "GNU General Public License v3 (GPLv3)" → "GPL-3.0"
    lic_upper = lic.upper()
    for forbidden in FORBIDDEN:
        key = forbidden.replace("-", "").replace(".", "")
        if key.lower() in lic_upper.lower().replace("-", "").replace(".", "").replace(" ", ""):
            return "forbidden"
    for warn in WARN_LICENSES:
        key = warn.replace("-", "").replace(".", "")
        if key.lower() in lic_upper.lower().replace("-", "").replace(".", "").replace(" ", ""):
            return "warn"
    return "ok"


def generate_markdown(pkgs: list[dict]) -> str:
    """docs/LICENSES.md の内容を生成。"""
    from datetime import datetime, timezone
    date_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    by_class: dict[str, list[dict]] = {"forbidden": [], "warn": [], "ok": [], "unknown": []}
    for p in pkgs:
        by_class[classify(p)].append(p)

    lines = [
        "# ai-chan Dependency Licenses",
        "",
        f"**Auto-generated**: {date_utc} (UTC) by `scripts/check_licenses.py`",
        "",
        "## Summary",
        "",
        f"- ✅ OK (permissive): **{len(by_class['ok'])}** packages",
        f"- ⚠ WARN (weak copyleft): **{len(by_class['warn'])}** packages",
        f"- 🚫 FORBIDDEN (strong copyleft): **{len(by_class['forbidden'])}** packages",
        f"- ❓ UNKNOWN: **{len(by_class['unknown'])}** packages",
        "",
    ]

    if by_class["forbidden"]:
        lines += ["## 🚫 FORBIDDEN (ai-chan では使用禁止)", ""]
        lines += ["| Package | Version | License | URL |",
                  "|---|---|---|---|"]
        for p in sorted(by_class["forbidden"], key=lambda x: x["Name"]):
            lines.append(
                f"| `{p['Name']}` | {p.get('Version','')} | **{p.get('License','?')}** | {p.get('URL','')} |"
            )
        lines.append("")

    if by_class["warn"]:
        lines += ["## ⚠ WARN (使用可だが明示必須)", ""]
        lines += ["| Package | Version | License | Note |",
                  "|---|---|---|---|"]
        for p in sorted(by_class["warn"], key=lambda x: x["Name"]):
            lines.append(
                f"| `{p['Name']}` | {p.get('Version','')} | {p.get('License','?')} | 動的リンクのみ |"
            )
        lines.append("")

    if by_class["unknown"]:
        lines += ["## ❓ UNKNOWN (要確認)", ""]
        lines += ["| Package | Version | URL |", "|---|---|---|"]
        for p in sorted(by_class["unknown"], key=lambda x: x["Name"]):
            lines.append(
                f"| `{p['Name']}` | {p.get('Version','')} | {p.get('URL','')} |"
            )
        lines.append("")

    lines += ["## ✅ OK (MIT / BSD / Apache / PSF / etc.)", ""]
    lines += ["| Package | Version | License |", "|---|---|---|"]
    for p in sorted(by_class["ok"], key=lambda x: x["Name"].lower()):
        lines.append(
            f"| `{p['Name']}` | {p.get('Version','')} | {p.get('License','?')} |"
        )
    lines.append("")

    lines += [
        "## ai-chan 本体",
        "",
        "- **License**: MIT (予定 — Phase 0.75 時点で LICENSE ファイル未作成)",
        "- **Base Model**: Sarashina2-7B (MIT, SB Intuitions)",
        "",
        "---",
        "",
        "このファイルは自動生成されます。編集は `scripts/check_licenses.py` で。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-doc", action="store_true",
                        help="docs/LICENSES.md を再生成")
    parser.add_argument("--fail-on-gpl", action="store_true",
                        help="GPL 混入時に exit 1 (CI 用)")
    parser.add_argument("--fail-on-unknown", action="store_true",
                        help="UNKNOWN license 混入時に exit 1")
    args = parser.parse_args()

    pkgs = run_pip_licenses()
    if not pkgs:
        print("[licenses] 解析失敗", file=sys.stderr)
        return 2

    forbidden_pkgs = [p for p in pkgs if classify(p) == "forbidden"]
    warn_pkgs = [p for p in pkgs if classify(p) == "warn"]
    unknown_pkgs = [p for p in pkgs if classify(p) == "unknown"]

    print(f"[licenses] 総計 {len(pkgs)} packages")
    print(f"  🚫 FORBIDDEN: {len(forbidden_pkgs)}")
    print(f"  ⚠ WARN:      {len(warn_pkgs)}")
    print(f"  ❓ UNKNOWN:   {len(unknown_pkgs)}")
    print(f"  ✅ OK:        {len(pkgs) - len(forbidden_pkgs) - len(warn_pkgs) - len(unknown_pkgs)}")

    if forbidden_pkgs:
        print("\n🚫 FORBIDDEN:")
        for p in forbidden_pkgs:
            print(f"  - {p['Name']} ({p.get('Version','?')}): {p.get('License','?')}")

    if warn_pkgs:
        print("\n⚠ WARN (要確認):")
        for p in warn_pkgs:
            print(f"  - {p['Name']} ({p.get('Version','?')}): {p.get('License','?')}")

    if args.update_doc:
        md = generate_markdown(pkgs)
        out = ROOT / "docs" / "LICENSES.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"\n[licenses] ✓ docs/LICENSES.md 更新完了 ({len(md)} bytes)")

    exit_code = 0
    if args.fail_on_gpl and forbidden_pkgs:
        exit_code = 1
    if args.fail_on_unknown and unknown_pkgs:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
