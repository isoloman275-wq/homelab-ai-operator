---
name: hermes-process-reaper
description: Prevents and cleans up stale/duplicate background processes (a single
  research pass once leaked ~12 stale procs that trickle-polled context for hours).
  Registers every spawned background job; reaps orphans by TTL.
triggers: [background spawn, research pass start/end, session end]
requires: []
---

## Context
During the 2026-07-29/30 market-research pass, ~12 background processes were spawned
(redaction + thinking-budget mishaps). Several had placeholder/invalid keys and kept
running, late-arriving with noise that polluted context. A registry + reaper stops
this class of leak.

## Steps
1. Every background spawn registers: (pid, purpose_hash, parent_task, ttl, started_at)
   in a local registry (SQLite or JSON on MAIN-NODE, e.g. ~/.agent-home/reaper_registry.json).
2. BEFORE spawning: check registry for a live process with the same purpose_hash →
   reuse its output instead of spawning a duplicate (this alone fixes the 12x incident).
3. Reap pass (session end + every 30 min): kill processes past ttl or whose
   parent_task is done/archived. Log kills to fact_store entity type `reap`.
4. Late-arriving output from a reaped/orphaned process: discard, do NOT inject into
   active context.

## Pitfalls
- Default ttl for research spawns: 10 min. No infinite ttl allowed.
- PROTECTED allowlist — never reap: ai-api (:8080), Mission Control (:8777),
  Ollama (any :11434), the Hermes gateway, the systemd user services. Match by port
  or by parent cmdline before killing.
- Key-redaction must run at SPAWN time (mask the API key in any log/registry entry),
  not at collect time — that was the original leak vector.
- Use `process(action='list')` / `process(action='kill', session_id=...)` for
  Hermes-tracked background jobs; use `kill <pid>` only for untracked orphans after
  allowlist check.
