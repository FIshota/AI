# §2 Secrets / Credentials Inventory — 2026-04-24

## Findings

### ~/.ssh (present but no private keys)
- `config` (210 bytes, 0644) — SSH config, no secrets
- `known_hosts` (1020 bytes, 0600) — server fingerprints
- `known_hosts.old` (280 bytes, 0644) — rotate/delete
- **No id_rsa / id_ed25519** → no private key migration needed

### ~/.claude/ (contains API key, encrypted backup required)
- `~/.claude.json` — 29,600 bytes, 0600 ✅ — project-level Claude state
- `~/.claude/settings.json` — 29,674 bytes, **0644** ⚠️ — recommend `chmod 600`
- **Action:** copy whole `~/.claude/` tree to encrypted external drive before wipe

### Keychain
- 2 entries: `gh:github.com` (GitHub CLI auth tokens)
- No ai-chan / hinomoto / anthropic / openai / huggingface entries
- **Action:** re-authenticate `gh auth login` on new Mac (token stays on old machine)

### Shell credentials (~/.netrc, .pypirc, .npmrc)
- None present ✅

### admin.env for launchd (MISSING)
- `~/.config/ai-chan/admin.env` **does not exist**
- Launchd plists expect `AICHAN_ADMIN_EMAIL` env → currently PII is hardcoded in plists instead
- **Action:** create `~/.config/ai-chan/admin.env` post-migration (see `PLIST_PII_REMOVAL_PROPOSAL.md`)

## Pre-migration checklist

- [ ] `chmod 600 ~/.claude/settings.json`
- [ ] Copy `~/.claude/` to encrypted USB drive
- [ ] Copy `~/.ssh/` to encrypted USB drive
- [ ] Export Keychain items: `security export -k login.keychain -o keychain_backup.p12` (password-protect)
- [ ] Note GitHub CLI token location → plan `gh auth login` on new Mac
- [ ] Rotate any API keys you no longer need (Anthropic console, HuggingFace tokens page)
