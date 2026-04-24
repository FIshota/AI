"""Warn the owner when the disk hosting ai-chan is running low.

Thresholds:
- < 2 GB free  -> critical
- < 10 GB free -> warn
- otherwise    -> silent
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.alerts import emit_alert  # noqa: E402

WARN_GB = 10.0
CRITICAL_GB = 2.0
_BYTES_PER_GB = 1024 ** 3


def evaluate(path: Path) -> Tuple[str, str, str, float]:
    """Return (severity, title, body, free_gb).

    severity == 'ok' means no alert should be emitted.
    """
    usage = shutil.disk_usage(str(path))
    free_gb = usage.free / _BYTES_PER_GB
    total_gb = usage.total / _BYTES_PER_GB
    if free_gb < CRITICAL_GB:
        return (
            "critical",
            "Disk space critical",
            f"Only {free_gb:.2f} GB free of {total_gb:.1f} GB on {path}. "
            "Clear space immediately to avoid data loss.",
            free_gb,
        )
    if free_gb < WARN_GB:
        return (
            "warn",
            "Disk space low",
            f"Only {free_gb:.2f} GB free of {total_gb:.1f} GB on {path}. "
            "Clean up soon.",
            free_gb,
        )
    return ("ok", "", "", free_gb)


def main() -> int:
    severity, title, body, free_gb = evaluate(_REPO_ROOT)
    if severity == "ok":
        print(f"[check_disk_space] ok ({free_gb:.2f} GB free)")
        return 0
    emit_alert(severity, title, body)
    print(f"[check_disk_space] {severity}: {free_gb:.2f} GB free")
    return 0 if severity != "critical" else 2


if __name__ == "__main__":
    sys.exit(main())
