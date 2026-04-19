"""PyPI latest version vs requirements.txt floor comparison.

Usage: python3 scripts/check_outdated.py
Outputs to stdout. Used by scripts/audit.sh.
"""
from __future__ import annotations

import json
import re
import urllib.request
import concurrent.futures
from pathlib import Path

REQ_FILE = Path(__file__).resolve().parent.parent / "requirements.txt"


def parse_requirements(path: Path) -> dict[str, tuple[str, str]]:
    """Return {name_lower: (operator, version)} from requirements.txt."""
    pkgs: dict[str, tuple[str, str]] = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r";.*$", "", s).strip()  # strip markers
        m = re.match(
            r"([A-Za-z0-9_.\-]+)(\[[^\]]+\])?\s*([<>=!~]+)\s*([0-9A-Za-z.\-+]+)", s
        )
        if m:
            name = m.group(1).lower()
            if name not in pkgs:  # keep lowest floor when conditional pins exist
                pkgs[name] = (m.group(3), m.group(4))
    return pkgs


def fetch_latest(name: str) -> tuple[str, str]:
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/json", timeout=10
        ) as r:
            return name, json.load(r)["info"]["version"]
    except Exception as e:
        return name, f"ERR:{type(e).__name__}"


def version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in re.split(r"[.\-+]", v):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts + [0] * 5)[:5]


def main() -> None:
    pkgs = parse_requirements(REQ_FILE)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        results = dict(ex.map(fetch_latest, pkgs.keys()))

    rows: list[tuple[str, str, str, int, bool]] = []
    for name, (_op, floor) in sorted(pkgs.items()):
        latest = results.get(name, "?")
        if latest.startswith("ERR"):
            rows.append((name, floor, latest, 0, False))
            continue
        try:
            fl = version_tuple(floor)
            lt = version_tuple(latest)
            gap = (lt[0] - fl[0]) * 1000 + (lt[1] - fl[1])
            outdated = (lt[0] > fl[0]) or (lt[0] == fl[0] and lt[1] - fl[1] >= 2)
            rows.append((name, floor, latest, gap, outdated))
        except Exception:
            rows.append((name, floor, latest, 0, False))

    print("=== Outdated (>=2 minor behind or major behind) ===")
    for name, floor, latest, gap, outd in rows:
        if outd:
            print(f"{name:30s} floor={floor:15s} latest={latest:15s} gap={gap}")

    print("\n=== All packages ===")
    for name, floor, latest, _gap, outd in rows:
        mark = "!" if outd else " "
        print(f"{mark} {name:30s} {floor:15s} -> {latest}")

    outdated_n = sum(1 for r in rows if r[4])
    print(f"\nTotal: {len(rows)} | Outdated: {outdated_n}")


if __name__ == "__main__":
    main()
