# Changelog

All notable changes to ai-chan are documented here.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Dates use ISO 8601 (YYYY-MM-DD).

## [pre-migration-20260424] — Workstation migration checkpoint (2026-04-24)

### Migration
- Tagged `pre-migration-20260424` on both `ai-chan` and `hinomoto-model` before M2 Pro → new Mac migration
- Env snapshot captured: `docs/migration/env_20260424/` (Python 3.13.2 / arm64 / macOS 15.5 / MLX 0.31.2)
- Backups: `docs/migration/backups_20260424/` (logs, config, data tarballs)
- Security: `chmod 600` on `config/persona.json`, `access_control.json`, `voice_auth_challenges.yaml`
- Dependencies: `cryptography` 46.0.5→46.0.7, `pillow` 12.1.1→12.2.0 (security updates)
- CVE-2025-69872 (diskcache pickle RCE): mitigated in `core/llm.py` (cache dir hardening, not exploitable)
- pip cache purged: 1,518 MB / 2,958 files freed

## [Unreleased] — Cat 5: Family-oriented UX & Safety (2026-04-24)

### Added
- 5.1 Emotion drift visualization (core/emotion_drift.py, ui/emotion_drift_window.py)
- 5.2 Memory forgetting curve with pinning (core/memory_forgetting.py)
- 5.3 Anniversary importance auto-estimation (core/anniversary_importance.py)
- 5.4 Voice ID fallback with challenge/response (core/voice_id_fallback.py)
- 5.5 Desktop Pet accessibility: colorblind palettes, VoiceOver, keyboard (ui/desktop_pet_a11y.py, core/a11y_announcer.py)
- 5.6 Multi-tenant isolation (core/tenant_context.py)
- 5.7 Conversation search UX with SQLite FTS5 + bigram hybrid (core/conversation_search.py, ui/search_window.py)
- 5.8 Silence-aware token — HinoMoto 四本柱 #4 (core/silence_token.py)
- 5.9 iCal export for anniversaries RFC 5545 (core/ical_export.py)
- 5.10 Screenshot sensitive-screen detection & blur (core/screenshot_sensitive.py, core/screenshot_blur.py)

### Tests
- 183 new tests added across Cat 5
- All passing on Python 3.13.2 / Apple Silicon M2 Pro (arm64) / stdlib-only

### Docs
- docs/quality/EMOTION_DRIFT.md, docs/design/MEMORY_FORGETTING.md, docs/design/ANNIVERSARY_IMPORTANCE.md
- docs/security/VOICE_ID_FALLBACK.md, docs/security/MULTI_TENANT.md, docs/security/SCREENSHOT_SENSITIVE.md
- docs/ux/ACCESSIBILITY.md, docs/ux/CONVERSATION_SEARCH.md, docs/ux/ICAL_EXPORT.md
- docs/design/SILENCE_AWARE.md
