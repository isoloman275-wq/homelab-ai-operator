# Auxiliary Task Routing — Session Notes (2026-07-13, corrected 2026-07-21)

## Fallback YAML Type Bug

The `fallback_providers` field was stored as a JSON string instead of a native YAML list:

```yaml
# BAD - string that looks like a list
fallback_providers: '[{"provider": "anthropic", "model": "claude-sonnet-4-6"}]'

# GOOD - actual YAML list
fallback_providers:
  - provider: anthropic
    model: claude-sonnet-4-6
```

The Python helper `_iter_fallback_entries` does `isinstance(raw, list)` so a string silently passes through as non-list → empty fallback chain. Verify with `hermes fallback list`.

**Fix procedure:** Read config.yaml with the `file` tool or `yaml.safe_load()`, change the type to a real list, write back via Python script (the `patch` tool and `hermes config set` CLI don't handle YAML well for this). If using `write_file`, the file is protected so you MUST use a Python script with `yaml.dump()` instead.

## Auxiliary Offload Pattern

Problem: title_generation was timing out on T1 (27B model) with "Auxiliary title_generation: connection error".

Solution: Created named provider `ollama-m3`, pointed lightweight auxiliary slots at qwen3.5 2b on AUX-NODE (aux-node). This gives fast response for metadata tasks while main models focus on user-facing work.

> **NOTE (2026-07-21):** AUX-NODE now runs `qwen3.5:4b-q4_K_M`; the `2b` model was removed. Any aux slot still referencing `2b` 404s with `model '...' not found` — update the slot `model` to `4b`. Also the `reasoning_effort: none` CoT fix below is WRONG for Ollama — use `think: false` (see `references/aux-debugging.md`).

## ⚠️ CoT Token Burn — CORRECTED 2026-07-21

qwen3.5 models have built-in chain-of-thought ("thinking") that consumes the `max_tokens` budget BEFORE producing visible content → empty `content`, `finish_reason=length`, despite HTTP 200.

**THE OLD FIX IS WRONG.** `reasoning_effort: none` in `extra_body` does NOT disable thinking on Ollama. `reasoning_effort` is an **OpenAI-official** parameter; Ollama's OpenAI-compat `/v1/chat/completions` endpoint **silently ignores** unknown fields, so the model still emits a hidden `reasoning` block and returns empty content. (`reasoning: false` as a bool is actively REJECTED by Ollama: "cannot unmarshal bool into ... Reasoning" — it expects an object.)

**Correct fix — `think: false`** (Ollama accepts `think` on both `/api/chat` and the OpenAI-compat endpoint as a passthrough):
```yaml
auxiliary:
  title_generation:
    provider: ollama-m3
    model: qwen3.5:4b-q4_K_M      # match what's ACTUALLY pulled on AUX-NODE (2b removed → 404)
    extra_body:
      think: false                # CORRECT knob — disables Qwen3.5 thinking on Ollama
```
```bash
# Verified working (2026-07-21): think:false returns real content; reasoning_effort:none does not
curl -s http://aux-node:11434/v1/chat/completions \
  -d '{"model":"qwen3.5:4b-q4_K_M","messages":[{"role":"user","content":"Reply: TITLE: hi"}],"max_tokens":30,"think":false}'
```

## Testing AUX-NODE Auxiliary Tasks

Direct curl won't work for testing Hermes-internal slots (they use gateway auth). Instead:
1. Trigger an actual task that exercises the slot (e.g., file a cron job that needs title generation)
2. Check gateway logs for successful connections to aux-node:11434
3. Or test the Ollama API directly with `think:false` in the request body:
   ```bash
   curl -s http://aux-node:11434/v1/chat/completions \
     -d '{"model":"qwen3.5:4b-q4_K_M","messages":[{"role":"user","content":"Test"}],"max_tokens":64,"think":false}'
   ```

## Anthropic API Version Pitfall

When testing Anthropic directly via curl, use `anthropic-version: 2023-06-01` — the version `2025-04-19` was rejected with `invalid_request_error`. Hermes handles this internally for fallback routing, so manual tests need a valid current version.

## Named Provider Syntax

Named custom providers go in `providers:` dict at config root:

```yaml
providers:
  ollama-m3:
    provider: custom
    base_url: http://aux-node:11434/v1
```

Referenced by simple name (`ollama-m3`) in auxiliary task provider fields — NO prefix needed for named providers (the `custom:` prefix is only for inline configuration, not named lookups). Configured via Python script that reads/writes the YAML directly.
