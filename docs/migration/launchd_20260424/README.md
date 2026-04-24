# §6 launchd / Scheduled Task Inventory — 2026-04-24

## Running daemons
| Label | Status | PID |
|---|---|---|
| `com.aichan.security-audit` | Loaded, not running | 0 (scheduled) |
| `com.aichan.security-weekly` | Loaded, not running | 0 (scheduled) |

## Plist files (backed up here)
- `com.aichan.security-audit.plist` (2703 bytes)
- `com.aichan.security-weekly.plist` (1715 bytes)

## PII findings in plists
Both plists contain hardcoded PII:
- Email: `honnsipittu@gmail.com` (in StandardErrorPath / notification target)
- Absolute paths: `/Users/fujihiranoborudai/Downloads/agent/ai-chan/...`

**Option A (move to external env file):** see `PLIST_PII_REMOVAL_PROPOSAL.md`
**Option B (inline regeneration script):** keep inline, use `scripts/render_plist.sh` to regenerate per-machine

→ Decision pending from user.

## Migration plan
1. Copy both plists to `/Volumes/MigrationDisk/launchd/` before wipe
2. On new Mac:
   ```bash
   cp launchd/*.plist ~/Library/LaunchAgents/
   # Edit hardcoded paths if user home path changed
   launchctl load ~/Library/LaunchAgents/com.aichan.*.plist
   launchctl list | grep aichan  # verify
   ```
3. Optionally migrate PII to `~/.config/ai-chan/admin.env` (Option A)

## Claude Code scheduled tasks
3 deprecated tasks remain listed — delete via https://claude.ai/code/scheduled per `DEPRECATED_SCHEDULED_TASKS.md`:
- (names listed in `SCHEDULED_TASKS_EXPORT_20260424.md`)

Active schedule:
- `ai-chan-daily-security-audit` (9am JST daily) — keep for new Mac
