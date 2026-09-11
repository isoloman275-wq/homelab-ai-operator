# Unified Health Watchdog — pattern

Canonical file: `~/.agent-home/scripts/unified_health_watchdog.py` (stdlib-only: `json`, `urllib.request`, `os`, `re`, `datetime`, `pathlib`).

## What it checks (extend per deployment)
1. **Trading crons in ERROR** — parse `~/.agent-home/cron/jobs.json`, for each job with `state == "error"`, read its latest `cron/output/<id>/*.md` error file; report.
2. **TikTok pipeline FAIL-in-log** — tail `/path/to/pipeline/logs/pipeline.log` (Windows `C:\pipeline\logs\pipeline.log`); if it contains `FAIL` / `did not post` / `0 posts` since last alert, report. Also detect "cookies expire in 2 days" as a warning.
3. **Project4 daemon down** — check last signal-daemon activity / process; if stale > N min, report.

## State + dedup
`~/.agent-home/scripts/.unified_watchdog_state.json`: per-category last-alert date. Suppress re-alerts same day; send all-clear once/day when everything is green.

## Telegram send (stdlib)
Read `TELEGRAM_BOT_TOKEN` + `TELEGRAM_HOME_CHANNEL` from `~/.agent-home/.env`; POST `https://api.telegram.org/bot<token>/sendMessage` with `urllib.request`. No external deps.

## Cron spec
```
cronjob action=create name="Unified Health Watchdog" schedule="*/30 * * * *" no_agent=true script="unified_health_watchdog.sh" deliver=local
```
`deliver=local` because the script itself sends to Telegram (don't double-deliver). When adding this, **pause** the old daily watchdog to avoid duplicates.

## Why stdlib-only
The things it monitors break precisely because they need venv deps / model servers. If the watchdog needed those too, it would break at the same time and you'd get zero alerts. Stdlib = it always runs.
