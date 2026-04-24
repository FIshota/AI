# Pre-Migration Actions — 2026-04-25 Execution Log

Items 1–8 from `USER_MANUAL_CHECKLIST_20260424.md` summary (remaining follow-ups).

## ✅ Completed automatically

### Item 6 — plist PII removal (Option A executed)
- Created `~/.config/ai-chan/admin.env` (mode 0600) with `AICHAN_ADMIN_EMAIL`
- Removed `AICHAN_ADMIN_EMAIL` key from both plists:
  - `~/Library/LaunchAgents/com.aichan.security-audit.plist`
  - `~/Library/LaunchAgents/com.aichan.security-weekly.plist`
- Updated both scripts to source `admin.env` at the top:
  - `scripts/daily_security_audit.sh`
  - `scripts/weekly_security_summary.sh`
- Reloaded launchd (`unload`+`load`) — both daemons re-registered
- Verified: `grep -c honnsipittu ~/Library/LaunchAgents/com.aichan.*.plist` → 0

### Item 8 — `.zshrc` anaconda3 cleanup
- Backup: `~/.zshrc.pre-migration-20260425.bak`
- Removed entire conda initialize block (lines 2–15)
- Verified: `zsh -c 'source ~/.zshrc'` loads cleanly
- Note: anaconda3 directory (`~/opt/anaconda3/`) is not installed, so block was dead code

## ⚠️ Requires user (interactive / GUI / external)

### Item 1 — FileVault (currently OFF)
```
System Settings → Privacy & Security → FileVault → Turn On
```
Record recovery key in 1Password immediately. Initial encryption runs 30–60 min.

### Item 2 — Time Machine (no destination configured)
```
System Settings → General → Time Machine → Add Backup Disk...
```
Connect external disk first. Verify with:
```
tmutil destinationinfo
tmutil latestbackup
```

### Item 3 — Encrypted USB copy (no external disk mounted now)
Connect an encrypted external SSD, then run these in a terminal:
```bash
# Key stuff (keep order — smallest/most-critical first)
rsync -av ~/.claude/ /Volumes/MigrationDisk/claude/
rsync -av ~/.ssh/ /Volumes/MigrationDisk/ssh/
rsync -av ~/.config/ai-chan/ /Volumes/MigrationDisk/config-ai-chan/
cp ~/.zshrc ~/.bash_profile /Volumes/MigrationDisk/dotfiles/

# Bulk caches (~10 GB + 8 GB)
rsync -av ~/.cache/huggingface/ /Volumes/MigrationDisk/hf_cache/
rsync -av /Users/fujihiranoborudai/Downloads/agent/hinomoto-model/artifacts/ /Volumes/MigrationDisk/hinomoto_artifacts/

# Model
cp /Users/fujihiranoborudai/Downloads/agent/ai-chan/models/sarashina2-7b.Q4_K_M.gguf /Volumes/MigrationDisk/models/

# Verify
cd /Volumes/MigrationDisk && find . -type f | wc -l
```

### Item 4 — Keychain export (interactive GUI prompt required)
Run in Terminal (will prompt for login password):
```bash
security export -k ~/Library/Keychains/login.keychain-db \
  -t certs -f pkcs12 -P "$(security find-generic-password -gl 'kc-export-temp' -w 2>/dev/null || echo 'SET_YOUR_PASSWORD')" \
  -o ~/Desktop/keychain_certs_20260425.p12
```
Or simpler GUI path: **Keychain Access.app → File → Export Items...**
Store the `.p12` in 1Password as an attached file.

### Item 5 — 2FA migration planning (pure user work)
- [ ] 1Password: ensure master password is memorized/stored
- [ ] Authy/GA: check cloud backup is enabled (Authy) or manually transfer each TOTP (GA)
- [ ] Recovery codes: download fresh codes for GitHub, Anthropic, HuggingFace, npm, Google, iCloud
- [ ] Apple Passkeys: iCloud Keychain must be ON (it is — verified by Keychain sync)

### Item 7 — 3 deprecated scheduled tasks (Web UI only)
Open https://claude.ai/code/scheduled and delete:
1. `ai-chan-daily-learning`
2. `ai-chan-daily-security-scan`
3. `ai-chan-test-regression`

After deletion, verify with scheduled-tasks MCP list shows only active `ai-chan-daily-security-audit` (+ any other intentional entries).
