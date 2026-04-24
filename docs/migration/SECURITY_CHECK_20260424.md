# Pre-Migration Security Check — 2026-04-24

## ✅ Passed
| Check | Result |
|---|---|
| World-writable files in `ai-chan/` | None found |
| `.env` actual file (ai-chan) | Only `.env.example` exists (template, safe 0644) |
| `.env` actual file (hinomoto) | None |
| Sensitive config permissions | 0600 (persona, access_control, voice_auth) |
| MLX / Metal | `is_available() = True` on arm64 |
| pip-audit (hinomoto) | No known vulnerabilities |
| pip-audit (ai-chan) | 1 finding — CVE-2025-69872 diskcache, **mitigated in core/llm.py** |
| bandit High severity | 0 |

## ⚠️ Action Required (user manual)
| Finding | Severity | Action |
|---|---|---|
| **FileVault is Off** | HIGH | Enable on new Mac before first login with data. Store recovery key in 1Password. |
| **Time Machine backup unreachable** | MEDIUM | Reconnect backup disk, verify `tmutil latestbackup` before migrating. Without recent backup = no rollback. |
| bandit B104 `0.0.0.0` bind in `web_main.py:22,78` | MEDIUM | Tracked in `docs/KNOWN_ISSUES.md`, parametrize via settings post-migration |
| 46 outdated non-security deps | LOW | Bulk update post-migration with F8 baseline comparison |

## Evidence paths
- `/Users/fujihiranoborudai/Downloads/agent/ai-chan/logs/security_audit/pre-migration-20260424_*`
- `/Users/fujihiranoborudai/Downloads/agent/ai-chan/docs/migration/env_20260424/pytest_baseline.txt`
