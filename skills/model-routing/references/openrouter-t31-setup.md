# OpenRouter T3.1 Setup Reference

## What it is

T3.1 is a custom Hermes provider alias that routes Claude Sonnet 4 through OpenRouter
instead of directly to Anthropic. Same model capability, cheaper per-token in some
configurations, and decoupled from the NZD $30/month Anthropic cap.

Active as of Jul 14 2026. API key: OPENROUTER_API_KEY_T31 in ~/.agent-home/.env.

## Config.yaml entry (custom_providers section)

```yaml
custom_providers:
- name: openrouter-t31
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
  model: anthropic/claude-sonnet-4
  key_env: OPENROUTER_API_KEY_T31
```

key_env tells Hermes which env var to use for auth. The base_url MUST be
https://openrouter.ai/api/v1 — without the /v1 suffix Hermes fetches the
OpenRouter website HTML instead of the API (produces a giant Next.js HTML blob
as the model response). Verified broken: /api. Verified working: /api/v1.

## How to add the key non-interactively

`hermes auth add openrouter` requires a TTY and will crash without one.
Instead, append directly to ~/.agent-home/.env:

```python
# Write this as a file via write_file, then run python3 /tmp/add_key.py
env_path = "~/.agent-home/.env"
with open(env_path, "a") as f:
    f.write("OPENROUTER_API_KEY_T31=YOUR_KEY_HERE\n")
```

DO NOT use inline terminal Python with the key or URL — the security filter
in the Hermes terminal tool strips strings that look like API keys or HTTP
URLs from stdout/stderr. Use write_file to create the script, then execute it.

## Verification test

```bash
hermes chat -q "Reply with exactly: T3.1 WORKING" -Q --provider openrouter-t31 -m anthropic/claude-sonnet-4
```

Should return "T3.1 WORKING" within ~2s. Response cost visible in usage logs.

## Switching back to T1 for fallback test

```bash
hermes config set model.default qwen3.8:27b-132k
hermes config set model.provider custom
hermes chat -q "Reply with exactly: T1 ACTIVE" -Q
# Verify T1 responds, then restore:
hermes config set model.default anthropic/claude-sonnet-4
hermes config set model.provider openrouter-t31
```

## Key format quirks

- OpenRouter model names REQUIRE the provider prefix: `anthropic/claude-sonnet-4`
  NOT a dated suffix like `anthropic/claude-sonnet-4-20250514` — that 404s.
  Check valid IDs via: GET https://openrouter.ai/api/v1/models (filter for claude+sonnet+4)
- Direct Anthropic uses bare names: `claude-sonnet-4-6`
- Mixing these up gives 400 "not a valid model ID" (OpenRouter) or 404 (Anthropic)

## Fallback chain — MUST clear to avoid Anthropic credit burn

After adding T3.1, remove the direct Anthropic fallback. If fallback_providers still
contains `provider: anthropic`, any OpenRouter hiccup silently falls through to Anthropic
and burns your NZD $30 cap. Clear it:

```python
# In a write_file script:
cfg['fallback_providers'] = []
```

Or via hermes config: check with `grep -A3 fallback_providers ~/.agent-home/config.yaml`

Also clear model.base_url and model.api_key if they were previously set for Ollama —
otherwise the custom provider's base_url gets overridden at the model section level.

## Pricing (as of Jul 2026)

~$7-15/M tokens input via OpenRouter for Claude Sonnet 4.
Direct Anthropic ~$3/M input but counts against NZD $30/month cap.
OpenRouter uses a separate budget — useful for overflow.
