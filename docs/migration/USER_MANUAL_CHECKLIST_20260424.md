# §12 User Manual Checklist — Pre-Migration

Items Claude cannot execute. Do before wiping / handing over the old Mac.

## 🔐 Accounts

- [ ] **Apple ID**: System Settings → Apple ID → verify 2FA enabled
- [ ] **iCloud**: confirm sync completed (Photos / Notes / Keychain if used)
- [ ] **iCloud Keychain**: if enabled, verify it's syncing (new Mac picks it up automatically)
- [ ] **FileVault**: Turn ON (System Settings → Privacy & Security → FileVault). Store recovery key in 1Password.

## 🔑 2FA / Password Managers

- [ ] **1Password**: note the device-authorization status. New Mac will need re-authorize + master password.
- [ ] **Authy / Google Authenticator / other TOTP**: enable cloud backup OR transfer per-entry. Most TOTPs cannot be re-added from scratch without the original QR — check each account's "recovery codes".
- [ ] **Passkeys**: macOS passkeys sync via iCloud Keychain automatically. Confirm iCloud Keychain is on.
- [ ] **GitHub CLI token**: `gh auth login` will be needed on new Mac (current token stays on old Mac).
- [ ] **Anthropic console**: API keys in `~/.claude/` — back up with encrypted external drive.
- [ ] **HuggingFace token**: `~/.cache/huggingface/token` if present → migrate or re-issue.
- [ ] **npm/PyPI tokens**: none detected in §2, but check settings of any personal publishers.

## 💾 Backups

- [ ] **Time Machine**: reconnect external disk, verify `tmutil latestbackup` succeeds. Run one fresh backup.
- [ ] **Encrypted external drive** (for non-Time-Machine items):
  - `~/.claude/` (API keys)
  - `~/.ssh/` (even if no private keys, restore config + known_hosts)
  - `~/.cache/huggingface/` (10 GB — see MODEL_CACHE_INVENTORY)
  - `ai-chan/models/sarashina2-7b.Q4_K_M.gguf`
  - `hinomoto-model/artifacts/` (8.2 GB)
  - Keychain export: `security export -k login.keychain -o keychain_backup.p12` (password-protect!)

## 🖥️ Apps / Licensing

- [ ] **Xcode**: deauthorize / sign out if signed in
- [ ] **JetBrains IDEs**: deactivate license on old machine
- [ ] **Adobe / Figma / etc.**: sign out (most have device-seat limits)
- [ ] **Office / iWork**: note product keys if any
- [ ] **Homebrew** (if ever installed): `brew bundle dump` before wipe — reinstall list handy

## 🌐 Browsers

- [ ] **Safari**: iCloud sync on = bookmarks/history auto-transfer
- [ ] **Chrome / Edge / Firefox**: sign in on new Mac, verify bookmark sync
- [ ] Export bookmarks as HTML from each browser as fallback

## 📨 Messaging / Communication

- [ ] **Slack / Discord / Teams**: re-login on new Mac
- [ ] **LINE / Signal / WhatsApp Desktop**: re-link via phone

## 🎛️ Developer settings

- [ ] Note terminal preferences: `defaults export com.apple.Terminal ~/Desktop/terminal_prefs.plist`
- [ ] If using iTerm2: iTerm2 → Preferences → General → Preferences → "Save current settings to folder"
- [ ] VSCode settings sync (GitHub or Microsoft account) — enable and wait for sync
- [ ] `.config/` tarball: `tar czf ~/Desktop/config_backup.tar.gz -C ~ .config`

## ✅ Final verification

- [ ] Boot from Time Machine test (optional, if doing migration assistant)
- [ ] Keep old Mac bootable for at least 7 days post-migration as rollback
- [ ] Photograph recovery codes / QR codes onto encrypted device (1Password supports attachments)
