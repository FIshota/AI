# Environment Snapshot — 2026-04-24

Taken before Mac migration (M2 Pro → new workstation).

## Files
| File | Purpose |
|---|---|
| `python_version.txt` | `python3 -VV` output |
| `pip_freeze.txt` | 181 packages pinned |
| `mac_env.txt` | Hardware (MBP M2 Pro 16GB) + macOS |
| `.zshrc.copy` / `.bash_profile.copy` | Shell rc backups |
| `claude_dir_listing.txt` | `~/.claude/` top-level contents |
| `launchagents_listing.txt` | `~/Library/LaunchAgents/` inventory |
| `launchctl_list.txt` | Running daemons matching ai-chan/hinomoto (empty = none running now) |
| `cleanup_log.txt` | Cache purge before/after sizes |

## Restoration on new Mac
```bash
# 1. Install Python 3.13.2 (matching python_version.txt)
# 2. Restore shell rc
cp .zshrc.copy ~/.zshrc
# 3. Restore venv
python3 -m pip install -r pip_freeze.txt
# 4. Copy launchd plists to ~/Library/LaunchAgents/
#    (see launchagents_listing.txt for filenames, and launchd/ in repo for sources)
# 5. Install Claude Code and restore ~/.claude/ from backup
```

## NOT included (copy manually)
- `~/.claude/` full tree (has API keys — copy via encrypted external drive)
- `~/.ssh/` (none present this time, but check)
- Keychain items
- Homebrew (not installed here; new Mac will need `/bin/bash -c "$(curl ...)"`)
- VSCode/Cursor CLI not installed → extensions not captured
