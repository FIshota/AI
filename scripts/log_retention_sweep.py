#!/usr/bin/env python3
"""Sweep stale log files according to config/log_retention.yaml.

Principle:
    - Dry-run by default (safety).
    - Only files are deleted; directories are preserved.
    - Undeclared directories are skipped (opt-in policy).
    - Delete actions are recorded to the audit_chain for tamper-evident
      traceability. If audit_chain import fails, fall back to stderr.

Usage:
    python scripts/log_retention_sweep.py                 # dry-run
    python scripts/log_retention_sweep.py --apply         # actually delete
    python scripts/log_retention_sweep.py --config PATH   # custom config
    python scripts/log_retention_sweep.py --root  PATH    # custom project root

See docs/security/LOG_RETENTION.md for policy rationale.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

logger = logging.getLogger("log_retention_sweep")


# ─────────────────────────────────────────────────────────────
# Data model (immutable)
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Policy:
    """Retention policy for one logical log directory."""

    rel_dir: str
    max_age_days: int


@dataclass(frozen=True)
class Candidate:
    """A single file considered for deletion."""

    path: Path
    rel_dir: str
    age_days: float


# ─────────────────────────────────────────────────────────────
# Config loading
# ─────────────────────────────────────────────────────────────
def load_policies(config_path: Path) -> list[Policy]:
    """Load retention policies from YAML. Returns an empty list if absent."""
    if not config_path.exists():
        logger.warning("policy config not found: %s", config_path)
        return []

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    policies_raw = raw.get("policies") or {}
    if not isinstance(policies_raw, dict):
        raise ValueError(f"invalid policies block in {config_path}")

    policies: list[Policy] = []
    for rel_dir, body in policies_raw.items():
        if not isinstance(body, dict) or "max_age_days" not in body:
            raise ValueError(f"invalid policy for {rel_dir!r} in {config_path}")
        max_age_days = int(body["max_age_days"])
        if max_age_days < 0:
            raise ValueError(f"negative max_age_days for {rel_dir!r}")
        policies.append(Policy(rel_dir=str(rel_dir), max_age_days=max_age_days))
    return policies


# ─────────────────────────────────────────────────────────────
# Scanning
# ─────────────────────────────────────────────────────────────
def scan_candidates(
    root: Path,
    policies: Iterable[Policy],
    now_epoch: float | None = None,
) -> list[Candidate]:
    """Return files that exceed their policy's max_age_days."""
    now = now_epoch if now_epoch is not None else time.time()
    out: list[Candidate] = []

    for pol in policies:
        target = root / pol.rel_dir
        if not target.exists() or not target.is_dir():
            logger.info("skip (missing dir): %s", target)
            continue

        cutoff = now - pol.max_age_days * 86400.0
        for p in _walk_files(target):
            try:
                mtime = p.stat().st_mtime
            except OSError as exc:
                logger.warning("stat failed %s: %s", p, exc)
                continue
            if mtime < cutoff:
                age_days = (now - mtime) / 86400.0
                out.append(Candidate(path=p, rel_dir=pol.rel_dir, age_days=age_days))
    return out


def _walk_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


# ─────────────────────────────────────────────────────────────
# Audit chain (best-effort)
# ─────────────────────────────────────────────────────────────
def _audit_record(root: Path, action: str, payload: dict) -> None:
    """Append an entry to the security audit chain. Falls back to stderr."""
    try:
        # Ensure the project root is importable for `core.audit_chain`.
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from core.audit_chain import append_entry  # type: ignore
        from datetime import datetime, timezone

        entry = {
            "event": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "log_retention_sweep",
            **payload,
        }
        append_entry(root / "logs" / "security_audit", entry)
    except Exception as exc:  # pragma: no cover - best-effort fallback
        print(
            f"[log_retention_sweep] audit_chain unavailable ({exc}); "
            f"action={action} payload={payload}",
            file=sys.stderr,
        )


# ─────────────────────────────────────────────────────────────
# Deletion
# ─────────────────────────────────────────────────────────────
def apply_deletions(root: Path, candidates: list[Candidate]) -> list[Path]:
    """Delete the candidate files. Returns successfully-deleted paths."""
    deleted: list[Path] = []
    for c in candidates:
        try:
            c.path.unlink()
            deleted.append(c.path)
            logger.info("deleted: %s (age=%.1fd)", c.path, c.age_days)
        except OSError as exc:
            logger.error("delete failed %s: %s", c.path, exc)

    _audit_record(
        root,
        action="log_retention_sweep.apply",
        payload={
            "deleted_count": len(deleted),
            "deleted_files": [str(p.relative_to(root)) for p in deleted],
        },
    )
    return deleted


def report_dry_run(root: Path, candidates: list[Candidate]) -> None:
    """Print dry-run summary; do not delete."""
    if not candidates:
        print("[dry-run] no files exceed retention policy.")
        return
    print(f"[dry-run] {len(candidates)} file(s) would be deleted:")
    for c in candidates:
        try:
            rel = c.path.relative_to(root)
        except ValueError:
            rel = c.path
        print(f"  - {rel}  (age={c.age_days:.1f}d, policy={c.rel_dir})")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sweep stale log files per config/log_retention.yaml."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Project root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Policy YAML (default: <root>/config/log_retention.yaml).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete files. Without this, runs in dry-run mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request dry-run (default behavior).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.apply and args.dry_run:
        print("error: --apply and --dry-run are mutually exclusive", file=sys.stderr)
        return 2

    root = args.root.resolve()
    config_path = (args.config or (root / "config" / "log_retention.yaml")).resolve()

    policies = load_policies(config_path)
    if not policies:
        print(f"[log_retention_sweep] no policies loaded from {config_path}")
        return 0

    candidates = scan_candidates(root, policies)

    if args.apply:
        deleted = apply_deletions(root, candidates)
        print(f"[apply] deleted {len(deleted)} file(s).")
    else:
        report_dry_run(root, candidates)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
