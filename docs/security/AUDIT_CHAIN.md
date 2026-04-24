# Audit Log Hash Chain (改竄防止ログ)

Tamper-evident hash chain for ai-chan's daily security audit logs. Any
retroactive edit, deletion, or reorder inside `logs/security/` (or any
chain directory) is detectable via `core.audit_chain.verify_chain`.

## Mechanics

Each entry is a single JSON file whose filename is an ISO-8601 UTC
timestamp. The filenames sort chronologically, which defines the chain
order.

Every entry carries two special fields:

- `prev_hash`: `sha256(canonical_json(previous_entry))` — the full
  previous entry, including its own `entry_hash`. For the first entry
  in a chain, `prev_hash` is 64 zero characters.
- `entry_hash`: `sha256(canonical_json(entry_without_entry_hash))`.
  Computed over the entry with `entry_hash` stripped, so the field can
  be written into the same JSON object it describes.

### Canonical JSON

All hashes are computed over a deterministic encoding:

```python
json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
```

Key ordering, whitespace, and non-ASCII handling are all fixed, so two
identical objects always hash identically regardless of writer.

### Why two hashes

- `entry_hash` detects edits within a single entry (including edits to
  `prev_hash` itself).
- `prev_hash` ties each entry to its predecessor. Deleting or reordering
  entries leaves the chain internally consistent at the edit site but
  breaks the link at the next entry.

## Usage

### Append an entry

```python
from pathlib import Path
from core.audit_chain import append_entry

append_entry(
    Path("logs/security"),
    {"event": "security_scan", "tool": "bandit", "findings": 0},
)
```

The returned dict contains the injected `prev_hash` and `entry_hash`.

### Verify a chain

```python
from pathlib import Path
from core.audit_chain import verify_chain

is_valid, violations = verify_chain(Path("logs/security"))
```

### Verify from the shell

```bash
./scripts/verify_audit_chain.sh logs/security
# Exit 0 = valid, Exit 2 = violations printed to stdout
```

Or directly:

```bash
python -m core.audit_chain --verify logs/security
```

## Known Limitations

This chain **detects** tampering; it does not **prevent** it. An
attacker with write access to the log directory and the ability to run
code can simply recompute the whole chain after modifying any entry,
and no internal check will notice.

Mitigations require an **off-machine anchor** — something outside the
attacker's control that commits to the chain state at a known point in
time:

- Periodically commit the current chain tip (`entry_hash` of the latest
  entry) to a git repository with signed commits.
- Publish the tip hash to a tamper-evident timestamping service such as
  [OpenTimestamps](https://opentimestamps.org/), which anchors the hash
  into the Bitcoin blockchain.
- Ship the tip hash to a remote append-only store (e.g. an S3 bucket
  with object lock, or a transparency log).

With an anchor in place, a retroactive rewrite is still detectable
because the rewritten tip will not match the previously anchored hash.

## Future Work: OpenTimestamps Integration

Roadmap sketch:

1. After each successful daily `scripts/audit.sh`, call `ots stamp` on
   a file containing the current tip hash.
2. Store the resulting `.ots` receipt alongside the log directory.
3. Add a `verify_anchors.sh` step that upgrades pending attestations
   (`ots upgrade`) and verifies them against the current chain tip
   (`ots verify`).
4. On verification failure, raise a `CRITICAL` security event through
   the existing `core/audit_log.py` severity channel.

Until OpenTimestamps is wired up, manual anchoring via a signed git
commit of the tip hash is the recommended stopgap.
