# Fallback Configuration Reference

## Correct Format in config.yaml

```yaml
fallback_providers:
  - provider: anthropic
    model: claude-sonnet-4-6
```

**This MUST be a YAML list of objects.** If `hermes config set fallback_providers '[{"provider": "anthropic", "model": "claude-sonnet-4-6"}]'` stores it as a JSON string, the gateway's `_iter_fallback_entries` will see `isinstance(raw, list) == False` and return an empty chain. The fallback is silently dead.

Verify with:
```bash
hermes fallback list   # should show at least one entry
```

## T3 404 Troubleshooting Checklist

1. **Provider must be `anthropic`** — `hermes config show` must display `provider=anthropic`. If it shows `custom`, Claude model names go through Ollama = 404.
2. **Model name:** `claude-sonnet-4-6` (NOT `claude-sonnet-4`, NOT prefixed with `anthropic/`)
3. **Set both config keys together** — setting only `model.default` without also setting `model.provider` is a common mistake.
4. **Verify API key directly:**
```bash
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```