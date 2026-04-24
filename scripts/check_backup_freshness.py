"""Check that backup restore drills ran recently.

Policy:
- If the newest log under logs/backup_restore_drills/ is older than
  90 days (or missing), emit a `critical` alert.
- If older than 30 days, emit a `warn` alert.
- Otherwise, emit nothing (silent success; no notification fatigue).

Intended to be run daily via launchd.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional, Tuple

# Allow running as a script without installation.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.alerts import emit_alert  # noqa: E402

LOG_DIR = _REPO_ROOT / "logs" / "backup_restore_drills"
WARN_DAYS = 30
CRITICAL_DAYS = 90


def _newest_log(log_dir: Path) -> Optional[Path]:
    if not log_dir.exists():
        return None
    candidates = [
        p for p in log_dir.iterdir()
        if p.is_file() and p.suffix in (".log", ".out", ".err", ".txt")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def evaluate(log_dir: Path, now: Optional[float] = None) -> Tuple[str, str, str]:
    """Return (severity, title, body).

    severity == 'ok' means no alert should be emitted.
    """
    now = now if now is not None else time.time()
    newest = _newest_log(log_dir)
    if newest is None:
        return (
            "critical",
            "Backup restore drill missing",
            f"No drill logs found under {log_dir}. "
            "Run scripts/backup_restore_drill.sh.",
        )
    age_days = (now - newest.stat().st_mtime) / 86400.0
    if age_days >= CRITICAL_DAYS:
        return (
            "critical",
            "Backup restore drill very stale",
            f"Newest drill log is {age_days:.1f} days old "
            f"(>{CRITICAL_DAYS}d). Run a restore drill now.",
        )
    if age_days >= WARN_DAYS:
        return (
            "warn",
            "Backup restore drill aging",
            f"Newest drill log is {age_days:.1f} days old "
            f"(>{WARN_DAYS}d). Schedule a restore drill soon.",
        )
    return ("ok", "", "")


def main() -> int:
    severity, title, body = evaluate(LOG_DIR)
    if severity == "ok":
        print("[check_backup_freshness] ok")
        return 0
    emit_alert(severity, title, body)
    print(f"[check_backup_freshness] {severity}: {title}")
    return 0 if severity != "critical" else 2


if __name__ == "__main__":
    sys.exit(main())
