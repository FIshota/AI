"""
Tamper-evident hash chain for security audit logs.

Each entry is a JSON file in ``log_dir`` whose name sorts chronologically.
Every entry embeds ``prev_hash`` (sha256 of the canonical JSON of the
previous entry) and ``entry_hash`` (sha256 of its own canonical JSON with
``entry_hash`` removed). A retroactive edit, deletion, or reorder breaks
the chain and is detectable via :func:`verify_chain`.

Principle (改竄防止ログ):
    append-only, detection-oriented. This module does not *prevent*
    tampering; it makes tampering visible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ZERO_HASH: str = "0" * 64
ENTRY_HASH_FIELD: str = "entry_hash"
PREV_HASH_FIELD: str = "prev_hash"


@dataclass(frozen=True)
class ChainViolation:
    """A single detected violation in the chain."""

    path: str
    reason: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.path}: {self.reason}"


def _canonical_json(obj: dict[str, Any]) -> str:
    """Deterministic JSON encoding used for hashing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hash_entry(entry: dict[str, Any]) -> str:
    """Hash an entry dictionary, excluding its own ``entry_hash`` field."""
    stripped = {k: v for k, v in entry.items() if k != ENTRY_HASH_FIELD}
    return _sha256_hex(_canonical_json(stripped))


def _hash_full_entry(entry: dict[str, Any]) -> str:
    """Hash a complete entry (including ``entry_hash``) for prev_hash linkage."""
    return _sha256_hex(_canonical_json(entry))


def _sorted_entry_files(log_dir: Path) -> list[Path]:
    """Return JSON entry files sorted by filename (chronological ISO timestamps)."""
    if not log_dir.exists():
        return []
    return sorted(p for p in log_dir.iterdir() if p.is_file() and p.suffix == ".json")


def _read_entry(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Entry is not a JSON object: {path}")
    return data


def _utc_iso_timestamp() -> str:
    """ISO-8601 UTC timestamp safe for filenames (colons replaced)."""
    return (
        datetime.now(timezone.utc)
        .strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    )


def append_entry(log_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    """Append ``entry`` to the chain in ``log_dir`` and return the written entry.

    Mutation-free: the input dict is not modified. A new dict is written.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    existing = _sorted_entry_files(log_dir)
    if existing:
        last = _read_entry(existing[-1])
        prev_hash = _hash_full_entry(last)
    else:
        prev_hash = ZERO_HASH

    # Build a new entry without mutating caller input.
    new_entry: dict[str, Any] = {k: v for k, v in entry.items() if k != ENTRY_HASH_FIELD}
    new_entry[PREV_HASH_FIELD] = prev_hash
    new_entry[ENTRY_HASH_FIELD] = _hash_entry(new_entry)

    # Collision-avoiding filename: timestamp plus short suffix if needed.
    base = _utc_iso_timestamp()
    candidate = log_dir / f"{base}.json"
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = log_dir / f"{base}-{counter:04d}.json"

    with candidate.open("w", encoding="utf-8") as fh:
        fh.write(_canonical_json(new_entry))

    logger.info("audit_chain: appended entry %s", candidate.name)
    return new_entry


def verify_chain(log_dir: Path) -> tuple[bool, list[str]]:
    """Walk the chain in order and detect tampering.

    Returns ``(is_valid, violations)``. An empty directory is valid.
    """
    violations: list[ChainViolation] = []
    files = _sorted_entry_files(log_dir)

    expected_prev = ZERO_HASH
    for path in files:
        try:
            entry = _read_entry(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            violations.append(ChainViolation(str(path), f"unreadable: {exc}"))
            # Cannot compute prev for downstream; break chain context.
            expected_prev = ""
            continue

        if PREV_HASH_FIELD not in entry or ENTRY_HASH_FIELD not in entry:
            violations.append(
                ChainViolation(str(path), "missing prev_hash or entry_hash field")
            )
            expected_prev = ""
            continue

        if entry[PREV_HASH_FIELD] != expected_prev:
            violations.append(
                ChainViolation(
                    str(path),
                    f"prev_hash mismatch (expected {expected_prev}, "
                    f"got {entry[PREV_HASH_FIELD]})",
                )
            )

        recomputed = _hash_entry(entry)
        if recomputed != entry[ENTRY_HASH_FIELD]:
            violations.append(
                ChainViolation(
                    str(path),
                    f"entry_hash mismatch (expected {recomputed}, "
                    f"got {entry[ENTRY_HASH_FIELD]})",
                )
            )

        expected_prev = _hash_full_entry(entry)

    is_valid = not violations
    return is_valid, [str(v) for v in violations]


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify audit log hash chain.")
    parser.add_argument(
        "--verify",
        metavar="LOG_DIR",
        type=Path,
        required=True,
        help="Directory containing chained audit JSON entries",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    is_valid, violations = verify_chain(args.verify)
    if is_valid:
        print(f"OK: audit chain valid ({args.verify})")
        return 0

    print(f"FAIL: audit chain violations in {args.verify}:")
    for v in violations:
        print(f"  - {v}")
    return 2


if __name__ == "__main__":
    sys.exit(_main())
