# T3 Troubleshooting Reference

## 404 / "not found" Error

**Root Cause:** Agent routed claude-sonnet-4 through the custom Ollama provider instead of Anthropic's API directly. Ollama does not have Claude models. 

**Fix Sequence:**
1. Check `hermes config show` - must show `provider=anthropic` for T3, NOT `provider=custom` 
2. Model name is `claude-sonnet-4-6` (NOT `claude-sonnet-4`)
3. Do NOT prefix with `anthropic/` when setting via `hermes config set model.default`
```bash
# Correct T3 switch:
hermes config set model default claude-sonnet-4-6
hermes config set model provider anthropic

# After testing, restore T1:
hermes config set model default qwen3.8:27b-132k
hermes config set model provider custom
```

## Current Model Name (2026-07-13)
- `claude-sonnet-4-6` - VERIFIED WORKING via direct API call
- `claude-sonnet-4` - Returns 404 "not_found_error"

Also Claude Code CLI not installed. Anthropic provider is configured with ANTHROPIC_API_KEY. Verify directly:
```bash
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```
