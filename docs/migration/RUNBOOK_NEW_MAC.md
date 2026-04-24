# New Mac Runbook — ai-chan / hinomoto-model

Procedure to restore both projects on a fresh macOS workstation from the `pre-migration-20260424` tag.

## Pre-checks

- [ ] macOS arm64 (Apple Silicon). Intel is out of scope — MLX is arm64-only.
- [ ] User account created with same UID/username if possible (simplifies launchd plist paths)
- [ ] External disk with migration snapshot attached (`docs/migration/backups_20260424/`, `~/.claude/` copy, model caches)

## 1. System foundations

```bash
# Xcode CLI tools (git, cc)
xcode-select --install

# Homebrew (optional but recommended)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.13.2 — match docs/migration/env_20260424/python_version.txt
# Option A: python.org installer (matches previous env)
# Option B: brew install python@3.13
```

## 2. FileVault (required before first login with data)

```
System Settings → Privacy & Security → FileVault → Turn On
```

Record the recovery key in 1Password / password manager.

## 3. Clone repositories

```bash
mkdir -p ~/Downloads/agent && cd ~/Downloads/agent
git clone https://github.com/FIshota/YAMATO-Project.git ai-chan
git clone https://github.com/FIshota/hinomoto-model.git
cd ai-chan && git checkout pre-migration-20260424
cd ../hinomoto-model && git checkout pre-migration-20260424
```

## 4. Python dependencies

```bash
cd ~/Downloads/agent/ai-chan
python3 -m pip install -r requirements.txt

# Verify MLX + Metal
python3 -c "import mlx.core as mx; assert mx.metal.is_available(); print('MLX OK')"

cd ../hinomoto-model
python3 -m pip install -r requirements.txt
```

## 5. Restore configuration

```bash
cd ~/Downloads/agent/ai-chan

# From external disk backup
cp /Volumes/MigrationDisk/config/persona.json config/
cp /Volumes/MigrationDisk/config/access_control.json config/
cp /Volumes/MigrationDisk/config/voice_auth_challenges.yaml config/

# Harden permissions (re-run — migration often loses them)
chmod 600 config/persona.json config/access_control.json config/voice_auth_challenges.yaml

# Restore data/logs if needed
tar xzf docs/migration/backups_20260424/logs.tar.gz
tar xzf docs/migration/backups_20260424/data.tar.gz
tar xzf docs/migration/backups_20260424/config.tar.gz
```

## 6. Shell environment

```bash
cp docs/migration/env_20260424/.zshrc.copy ~/.zshrc
cp docs/migration/env_20260424/.bash_profile.copy ~/.bash_profile

# Before `source`, review and remove the anaconda3 block
# (see docs/migration/ZSHRC_CLEANUP_PROPOSAL.md)
```

## 7. Claude Code + `~/.claude/`

1. Install Claude Code (https://claude.com/claude-code)
2. Restore `~/.claude/` from encrypted external backup (contains API keys, rules, skills, agents, commands)
3. Verify with `claude --version`

## 8. launchd agents

```bash
cp launchd/com.aichan.security-audit.plist ~/Library/LaunchAgents/
cp launchd/com.aichan.security-weekly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.aichan.*.plist
launchctl list | grep aichan  # verify loaded
```

Also create `~/.config/ai-chan/admin.env` from the migration inventory (see
`docs/migration/SECRETS_INVENTORY_20260424.md`) — plist PII is externalized here.

## 9. git identity

```bash
git config --global user.name "Nobordai Fujihira"
git config --global user.email "honnsipittu@gmail.com"
```

## 10. Baseline verification

```bash
cd ~/Downloads/agent/ai-chan
python3 -m pytest -q
# Compare test count & duration against docs/migration/env_20260424/pytest_baseline.txt
```

## 11. Post-migration bulk updates

Only after baseline green:

```bash
python3 -m pip install -U -r requirements.txt
python3 -m pytest -q  # catch regressions
# If green, commit requirements.lock refresh
```

## Known gotchas

- **Python location drift:** old absolute paths (`/usr/local/bin/python3` vs `/opt/homebrew/bin/python3`) can break launchd plists. Check `which python3` and update plist `ProgramArguments`.
- **`~/.config/ai-chan/admin.env`:** empty file on new Mac = plists will fail silently. Restore before loading launchd.
- **FileVault migration:** if enabled mid-session, first reboot may take 30-60min for initial encryption.
