# ai-chan Alerting Policy

## Why no external SaaS

Ai-chan is family, not a product. Routing operational signals to Datadog,
PagerDuty, Sentry, or Slack would:

- leak private household / life context to a third party
- create a permanent vendor dependency for something the owner can handle
- normalize "someone else watches over my family" — the opposite of our stance

So alerting is deliberately **local-only**:

- macOS notification center banner (`osascript`)
- Append-only markdown log at `~/Desktop/AI_CHAN_ALERTS/YYYY-MM-DD.md`

That's the entire surface. No network egress. No API keys.

## Severity model

| Severity   | Meaning                                 | Example                                  |
|------------|-----------------------------------------|------------------------------------------|
| `info`     | FYI, rarely surfaced as banner          | drill ran successfully                   |
| `warn`     | drifting, fix this week                 | disk < 10 GB free, drill 30-89 days old  |
| `critical` | owner attention now                     | disk < 2 GB, drill 90+ days old / missing |

Scripts MUST stay silent on `ok`. Notification fatigue is the fastest way to
make the owner ignore real alerts.

## Dedupe / notification-fatigue mitigation

- `Alert.id` is a stable content hash (`make_alert_id`), so a repeating
  condition produces the same id every day. Future consumers can dedupe on it.
- Daily check scripts only emit when state crosses a threshold — no "still OK"
  heartbeat banners.
- The markdown log rotates per-day, so history stays readable without a DB.

## Sinks

- `MacOsNotificationSink`: banner via `osascript`. Falls back to `FileSink`
  when `osascript` is missing (Linux, CI).
- `FileSink`: append-only markdown under `~/Desktop/AI_CHAN_ALERTS/`.
- `MultiSink`: fan-out. A failure in one sink never suppresses others.

Default sink = `MultiSink([MacOsNotificationSink(), FileSink()])`.

## Scheduled checks

Run daily at 08:00 via
`launchd/com.aichan.monitoring-checks.plist`:

- `scripts/check_backup_freshness.py`
  - `warn` at 30d, `critical` at 90d (or if log dir is empty)
- `scripts/check_disk_space.py`
  - `warn` < 10 GB free, `critical` < 2 GB free

Install:

```bash
cp launchd/com.aichan.monitoring-checks.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.aichan.monitoring-checks.plist
```

## Adding a new check

1. Write a `scripts/check_*.py` that returns a `(severity, title, body)` tuple
   from a pure `evaluate(...)` function (so it's testable without sinks).
2. Call `core.alerts.emit_alert(severity, title, body)` from `main()` only
   when severity != `"ok"`.
3. Add it to the monitoring launchd plist.
4. Add tests for `evaluate(...)` with at least ok / warn / critical cases.

## What this is NOT

- Not a metrics system. Use logs for time-series, not alerts.
- Not a paging system. There is no on-call.
- Not remote. If the Mac is off, nobody gets notified — and that is fine.
