#!/usr/bin/env python3
"""ai-chan セキュリティポリシー期限切れ検知ツール (Phase 0.75).

config/security_policy.yaml に記載されている
「受容済み CVE / Bandit / Outdated」の expires フィールドを検査し、
期限切れを警告する。

使い方:
    python3 scripts/check_security_policy.py                  # 検査のみ
    python3 scripts/check_security_policy.py --json           # JSON 出力
    python3 scripts/check_security_policy.py --days-warn 30   # 30日前から warn
    python3 scripts/check_security_policy.py --strict         # 期限切れで exit 1
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "config" / "security_policy.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        print("[policy] pyyaml が必要です: pip install pyyaml", file=sys.stderr)
        sys.exit(2)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def check_section(name: str, items: list[dict], today: date, days_warn: int) -> list[dict]:
    """1 セクション内のエントリを検査して結果を返す。"""
    results = []
    for item in items or []:
        expires_str = item.get("expires", "")
        expires = _parse_date(expires_str)
        ident = item.get("id") or item.get("test_id") or item.get("package") or "(no-id)"

        if not expires:
            results.append({
                "section": name, "id": ident, "status": "NO_EXPIRY",
                "expires": expires_str, "days_left": None,
                "rationale": item.get("rationale", ""),
            })
            continue

        days_left = (expires - today).days
        if days_left < 0:
            status = "EXPIRED"
        elif days_left <= days_warn:
            status = "WARN"
        else:
            status = "OK"

        results.append({
            "section": name, "id": ident, "status": status,
            "expires": expires_str, "days_left": days_left,
            "rationale": item.get("rationale", ""),
        })
    return results


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days-warn", type=int, default=30,
                   help="期限 N 日以内を WARN 扱い (既定: 30)")
    p.add_argument("--json", action="store_true", help="JSON 出力")
    p.add_argument("--strict", action="store_true",
                   help="EXPIRED / NO_EXPIRY で exit 1 (CI 用)")
    p.add_argument("--policy", default=str(POLICY), help="policy YAML パス")
    args = p.parse_args()

    policy = _load_yaml(Path(args.policy))
    today = date.today()

    sections = {
        "accepted_cves": policy.get("accepted_cves", []),
        "accepted_bandit": policy.get("accepted_bandit", []),
        "accepted_outdated": policy.get("accepted_outdated", []),
    }

    all_results: list[dict] = []
    for name, items in sections.items():
        all_results.extend(check_section(name, items, today, args.days_warn))

    if args.json:
        print(json.dumps({
            "checked_at": today.isoformat(),
            "days_warn": args.days_warn,
            "results": all_results,
        }, ensure_ascii=False, indent=2))
    else:
        counts = {"OK": 0, "WARN": 0, "EXPIRED": 0, "NO_EXPIRY": 0}
        for r in all_results:
            counts[r["status"]] += 1

        print(f"[policy] 検査日: {today} / WARN 閾値: {args.days_warn}日")
        print(f"  ✅ OK:         {counts['OK']}")
        print(f"  ⚠  WARN:       {counts['WARN']}")
        print(f"  🚫 EXPIRED:    {counts['EXPIRED']}")
        print(f"  ❓ NO_EXPIRY:  {counts['NO_EXPIRY']}")
        print()

        for r in all_results:
            if r["status"] == "OK":
                continue
            icon = {"WARN": "⚠", "EXPIRED": "🚫", "NO_EXPIRY": "❓"}[r["status"]]
            days = f"{r['days_left']:+d}日" if r["days_left"] is not None else "--"
            print(f"  {icon} [{r['section']}] {r['id']}  expires={r['expires']} ({days})")
            if r["rationale"]:
                print(f"     └ {r['rationale'][:80]}")

    expired_or_missing = [r for r in all_results
                          if r["status"] in ("EXPIRED", "NO_EXPIRY")]
    if args.strict and expired_or_missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
