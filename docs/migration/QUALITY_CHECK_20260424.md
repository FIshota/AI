# §9 ai-chan Quality Check — 2026-04-24

All smoke-level import/roundtrip verifications before migration.

| # | Check | Result |
|---|---|---|
| 9-1 | `settings_schema.json` JSON roundtrip | ✅ 19 property keys, equal after dump/load |
| 9-2 | `scripts/tenant_admin.py --help` (R13-5) | ✅ CLI loads, 6 subcommands visible |
| 9-3 | `from core import mlx_engine` (R13-4) | ✅ Imported |
| 9-4 | `from core import kill_switch, kill_switch_policy` (R13-5) | ✅ Both imported |
| 9-5 | `core.a11y_announcer.A11yAnnouncer` (5.5) | ✅ Import OK |
| 9-6 | `core.emotion_drift` (5.1) | ✅ Exposes EmotionAggregate, CONTINUOUS_EMOTION_KEYS |
| 9-7 | `core.conversation_search` (5.7) | ✅ Module loads |

## Additional smoke evidence
- MLX Metal: `mx.metal.is_available() = True` (from §5)
- pytest baseline: 1437 pass (from §5)
- FTS5 synthetic DB: VACUUM succeeded (from §3)

## Not executed (require runtime env / interactive)
- Desktop pet full window render (requires display)
- VoiceOver audible announcement (requires user verification)
- Tenant create/purge flow (destructive, deferred to new Mac)
- Kill-switch trigger drill (requires privileged context)

Post-migration re-run: same checklist, expect identical results. Any new ImportError → investigate before loading launchd.
