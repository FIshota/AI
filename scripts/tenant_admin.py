#!/usr/bin/env python3
"""tenant_admin — テナント管理 CLI。

Usage:
    python scripts/tenant_admin.py --base data/tenants --list
    python scripts/tenant_admin.py --base data/tenants --create family-a
    python scripts/tenant_admin.py --base data/tenants --purge family-a --confirm
    python scripts/tenant_admin.py --base data/tenants --audit family-a
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# allow running directly from repo root
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core.tenant_context import (  # noqa: E402
    InvalidTenantIdError,
    TenantContext,
    TenantIsolationError,
    list_tenants,
    purge_tenant,
)


def _cmd_list(base: Path) -> int:
    for t in list_tenants(base):
        print(t)
    return 0


def _cmd_create(base: Path, tenant_id: str) -> int:
    ctx = TenantContext.create_isolated(base, tenant_id)
    print(f"created: {ctx.root_dir}")
    return 0


def _cmd_purge(base: Path, tenant_id: str, confirm: bool) -> int:
    target = purge_tenant(base, tenant_id, confirm=confirm)
    if not confirm:
        print(f"[dry-run] would delete: {target}")
        print("re-run with --confirm to actually delete")
    else:
        print(f"purged: {target}")
    return 0


def _cmd_audit(base: Path, tenant_id: str) -> int:
    ctx = TenantContext.create_isolated(base, tenant_id)
    audit = ctx.audit_dir
    entries = sorted(p for p in audit.iterdir() if p.is_file()) if audit.is_dir() else []
    report = {
        "tenant_id": tenant_id,
        "root_dir": str(ctx.root_dir),
        "audit_dir": str(audit),
        "entry_count": len(entries),
        "entries": [p.name for p in entries[-20:]],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ai-chan tenant administration")
    p.add_argument(
        "--base",
        type=Path,
        default=Path("data/tenants"),
        help="base directory containing tenant roots (default: data/tenants)",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--create", metavar="TENANT_ID")
    g.add_argument("--purge", metavar="TENANT_ID")
    g.add_argument("--audit", metavar="TENANT_ID")
    p.add_argument(
        "--confirm",
        action="store_true",
        help="actually perform destructive ops (default: dry-run)",
    )
    args = p.parse_args(argv)

    try:
        if args.list:
            return _cmd_list(args.base)
        if args.create:
            return _cmd_create(args.base, args.create)
        if args.purge:
            return _cmd_purge(args.base, args.purge, args.confirm)
        if args.audit:
            return _cmd_audit(args.base, args.audit)
    except (InvalidTenantIdError, TenantIsolationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
