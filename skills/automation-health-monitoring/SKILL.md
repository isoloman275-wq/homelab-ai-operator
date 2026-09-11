---
name: automation-health-monitoring
description: "Design + deploy proactive health watchdogs for unattended automation (Hermes crons, content pipelines, signal daemons) so failures page the user within minutes, not days. Covers the unified-watchdog pattern, why once-daily scans fail, and the common failure modes the watchdog catches + how to fix them. Load whenever you set up or maintain any long-running/unattended job for the operator, or diagnose 'why did X fail for days and nobody noticed'."
category: devops
---

# Automation Health Monitoring (catch failures at the time)

## When to use
- Setting up ANY cron, pipeline, or daemon that runs unattended.
- Diagnosing "why did X fail for 3 days and nobody noticed."
- After fixing an automation bug, to make the same class of failure page the user next time instead of sitting silent.

## Hard requirement (user mandate)
the operator explicitly rejected silent multi-day failures: *"Why don't you catch any of this and fix it at the time."* Treat **"catch failures at the time, not after the user notices"** as a non-negotiable for every unattended job. A job that fails and stays quiet for hours/days is a trust-breaking defect, not an acceptable outcome.

## The principle: a daily scan is not a monitor
A watchdog that runs once a day (or that can itself error silently) will let failures sit 13+ hours. The failure that triggered this skill: the TikTok pipeline failed at 07:00, the once-daily watchdog (20:00) had itself errored, so nothing alerted until the user noticed ~13h later.

A real monitor must:
1. **Run every 10–30 min** (Hermes `no_agent` cron, `*/30 * * * *`).
2. **Be stdlib-only** so it can't fail the way the things it watches do (no venv deps, no pandas/yfinance/feedparser). If the monitor needs the same broken environment, it breaks too.
3. **Check the actual failure signal**, not a proxy:
   - cron `error` state in `~/.agent-home/cron/jobs.json` (not just "did it run")
   - `FAIL` / `ERROR` / `exit status 1` in the pipeline log
   - daemon last-run age / process alive
4. **Page the user on Telegram immediately** on detection (dedupe per-day per-category so it doesn't spam).
5. **Be itself visible** — it's a separate cron, so if it dies, Hermes reports the cron error. Pair it with the general cron-watch so the monitor can't die silent either.

## Reusable artifact (canonical implementation)
`~/.agent-home/scripts/unified_health_watchdog.py` (stdlib-only) + `~/.agent-home/scripts/unified_health_watchdog.sh` wrapper. Reads Telegram creds from `~/.agent-home/.env`, dedupes via `~/.agent-home/scripts/.unified_watchdog_state.json`, sends to `TELEGRAM_HOME_CHANNEL`. **Copy and extend this; do not rewrite from scratch.** Structure documented in `references/watchdog-pattern.md`.

## Common failure modes the watchdog catches + fixes
- cron `script` resolves relative to `~/.agent-home/scripts/` — repo scripts must be copied or wrapped.
- `no_agent` `.py` crons run under SYSTEM python3 (no pandas/yfinance/feedparser) → wrap in `.sh` that `exec`s the project venv python, repoint cron `script` to the `.sh`.
- `cronjob update` tool rejects single-field `script`/`model` edits ("No updates provided") → edit `jobs.json` directly (backup first).
- pipeline references a deleted Ollama model (404 at step [1/5]) → repoint `SCRIPT_MODEL` in `modules/agent.py` to the live model.
- watchdog runs once daily and can error silently → replace with the 30-min unified watchdog.

## Serving processes: availability, not just error state
User-facing dashboards/UIs are served by long-running HTTP processes (e.g.
`python3 -m http.server` behind the dashboard). These die silently on reboots,
WSL session teardown, or OOM — with NO cron error anywhere, because nothing
owns them. A dead server reads as 'feature broken' to the user while every
component-level check passes.
- **Health-check the SERVING ENDPOINT (curl the actual URL) before presenting
  any dashboard/UI to the user** — a collector writing files correctly does not
  mean anything is serving them.
- Restore with a TRACKED background process (`terminal background=true`), then
  verify with a separate readiness check — the shell-level `nohup ... &` form
  is rejected/loses ownership and leaves an untracked orphan.
- Recurring silent deaths of a serving process = a supervision gap: move it to
  a systemd unit / s6 service / scheduled-task watchdog rather than hand-
  restarting it each time it is found down.

## Pitfalls
- Don't rely on a once-daily log scan. 13h blind spots are how you lose trust.
- Don't let the watchdog itself error silently — stdlib-only + separate cron + it should send an all-clear when healthy so you know it's alive.
- Don't double-alert: when you add the unified watchdog, **pause** the old daily watcher (e.g. `cronjob action=pause`) to avoid two Telegram messages.
- Don't page on every tick when healthy — all-clear once/day, problem alerts immediately.
- Don't infer 'service up' from 'its data files are fresh' — the writer and the
  server are separate processes with separate lifetimes; probe the served URL.

## Overlap note
- `tiktok-pipeline-ops` covers *operating/debugging* the TikTok pipeline; this skill covers the *monitoring discipline* that should wrap it (and trading crons + daemons). tiktok-pipeline-ops now points here for the monitoring requirement.
- `hermes-cron-management` covers diagnosing/repairing cron jobs; the cron-failure-modes reference overlaps with it — curator can consolidate the venv-wrapper / script-path gotchas into hermes-cron-management.
- `lab-health` is infra reachability (MAIN-NODE/GPU-NODE/AUX-NODE/Ollama/GPU), a different layer; this skill is automation error-state.
