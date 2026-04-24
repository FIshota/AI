# Known Issues — ai-chan

Last updated: 2026-04-24 (pre-migration)

## Security

### CVE-2025-69872 — diskcache pickle RCE (mitigated)
- **Status:** Mitigated, not exploitable
- **Dependency:** `diskcache` 5.6.3 (transitive via `llama-cpp-python`)
- **Fix version:** Not yet released upstream
- **Mitigation:** `core/llm.py:28-83, 433` enforces:
  - Cache dir confined to `~/.cache/ai-chan/` (user-only)
  - Directory mode `0700`
  - Owner uid verification before load
- **Action on fix release:** pin `diskcache>=<fix>` in `requirements.txt`, drop mitigation comments

### `0.0.0.0` bind in `web_main.py:22,78` (B104)
- **Status:** Accepted TODO
- **Risk:** Medium — exposes FastAPI on all interfaces if deployed
- **Current use:** Local dev only
- **Fix plan:** parametrize via `settings.web.bind_host` (default `127.0.0.1`)

### FileVault is Off
- **Status:** ⚠️ Requires user action
- **Recommendation:** Enable on new workstation via System Settings → Privacy & Security → FileVault
- **Impact:** Disk-at-rest encryption. Without it, stolen laptop = plaintext user data.

### Time Machine backup destination unreachable
- **Status:** ⚠️ Requires user action
- **Finding:** `tmutil latestbackup` fails to mount destination
- **Recommendation:** Reconnect backup disk before migration, verify last successful backup timestamp

## Configuration

### Config file permissions
- Sensitive configs now `0600` (persona.json, access_control.json, voice_auth_challenges.yaml)
- Other `config/*.json` still `0644` — acceptable (non-secret schemas, examples)

## Dependencies

### 46 outdated packages (non-security)
- See `logs/security_audit/pre-migration-20260424_outdated.txt`
- Bulk update deferred to post-migration to avoid conflating regressions with environment change
- Plan: on new Mac, `pip install -U -r requirements.txt` → run F8 golden baseline → commit lock
