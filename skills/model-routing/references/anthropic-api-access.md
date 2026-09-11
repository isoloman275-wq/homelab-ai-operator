# Anthropic API Access from Hermes (verified 2026-07-24)

## Key facts
- The Anthropic API (`https://api.anthropic.com`) is reachable from this environment via `curl` with the API key. This is SEPARATE from `claude.ai` web, which is Cloudflare-gated: both browser automation AND a raw `curl` of a `claude.ai` URL return the CF challenge shell. Tell-tale sign in the HTML: a `window.__CF$cv$params={r:'...'}` token near the bottom — that page is the challenge, NOT real content.
- The `ANTHROPIC_API_KEY` lives in `~/.agent-home/.env` (var name `ANTHROPIC_API_KEY`). Hermes config does NOT currently wire an Anthropic provider (main brain = OpenRouter `tencent/hy3` + local Ollama), so the key is only used where explicitly invoked.
- **Credit separation (CRITICAL):** Anthropic keeps two billing meters:
  1. Web/app **Pro & Max** subscriptions + their **Sage/free credit grants** → valid ONLY inside claude.ai web & mobile.
  2. The **Anthropic API** → billed on its own account balance (prepaid API credits or pay-as-you-go).
  There is no crossover. Web-plan credits can NEVER be spent by an API call, so Hermes (API or local) cannot consume them. Only API-account credits bill API calls.
- Model ids advance over time. As of 2026-07-24 the live `GET /v1/models` list included: `claude-fable-5`, `claude-sonnet-5`, `claude-opus-4-8`, `claude-opus-4-7`, `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-opus-4-5-20251101`, `claude-haiku-4-5-20251001`, `claude-sonnet-4-5-20250929`, `claude-opus-4-1-20250805`. Always verify with `GET /v1/models` rather than hardcoding.

## Verify a model is callable (deterministic probe)
```bash
# pull the key into a shell var WITHOUT echoing it
KEY=$(grep '^ANTHROPIC_API_KEY=' ~/.agent-home/.env | head -1 | cut -d= -f2-)
# 1) list available models (confirms API access + shows live ids)
curl -sS -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" \
  "https://api.anthropic.com/v1/models" | grep -oE '"id":"[^"]+"'
# 2) tiny generate to prove a specific model bills/responds
curl -sS -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-fable-5","max_tokens":24,"messages":[{"role":"user","content":"reply with exactly: ok"}]}' \
  "https://api.anthropic.com/v1/messages"
```
Notes:
- The generate call spends a few tokens (~sub-cent). If the account has API prepaid credits, it draws from those; if none, it bills the linked card.
- There is NO public "check balance / check credits" endpoint — you cannot read the credit balance or terms (e.g. whether a free grant is model-restricted) from the API. The user must confirm credit type in Anthropic Console → Billing.

## Wiring Hermes to use an Anthropic model (only if the user wants)
Add to `config.yaml` under `providers`:
```yaml
providers:
  anthropic:
    provider: custom
    base_url: https://api.anthropic.com/v1
    api_key: ${ANTHROPIC_API_KEY}
```
Then assign a tier/model to it. Remember the credit-separation rule above: this spends API-account credits, NOT web Pro/Max credits.
