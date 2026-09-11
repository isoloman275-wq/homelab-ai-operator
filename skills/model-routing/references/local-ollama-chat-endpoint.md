# Wiring a chat endpoint to local Ollama (and the `hermes -z` hang)

## Problem (Mission Control war-room chat, 2026-07-27)
A dashboard chat button routed user prompts to local Ollama models. Two failures:

1. **Silent hang via `hermes -z`.** Routing the prompt through `hermes -z "<prompt>"`
   (full Hermes agent loop) against a local *thinking* model (`qwen3.5:4b`) returns
   `rc=124` (timeout) with NO output after >180s. The full agent loop over-thinks /
   loops on local reasoning models and never completes a short chat reply.
2. **CUDA OOM via `/v1` at `num_ctx 65536`.** The model was baked at `PARAMETER num_ctx 65536`.
   Ollama's OpenAI-compat `/v1/chat/completions` pre-allocates the full KV cache, and
   on AUX-NODE's 4GB GTX 960 that tips into `CUDA error: out of memory` on every call.

## Fix
- **Bake 4b at `num_ctx 64000` (NOT 65536).** 64000 is exactly hermes's
  `MINIMUM_CONTEXT_LENGTH` floor (so the bake satisfies the agent floor) AND sits under
  the `/v1` OOM line on the 4GB card. Verified: re-bake + `/v1` call returned `M3OK`.
- **Don't call local models through `hermes -z`.** In the server, route `ollama-*` providers
  through a DIRECT `/v1/chat/completions` POST with `reasoning_effort: "none"` (thinking off —
  remember `/v1` IGNORES native `think:false`) and a capped `max_tokens` (~800).
- **Cloud (OpenRouter / openrouter-t31) KEEPS `hermes -z`** — the full agent (memory + tools)
  is what you want for real agent turns. Only LOCAL models get the direct-/v1 fast path.

## server.py pattern (`_ollama_chat`)
```python
OLLAMA_BASE = {
    "ollama-m1": "http://main-node:11434/v1",
    "ollama-m2": "http://gpu-node-2:11434/v1",
    "ollama-m3": "http://aux-node:11434/v1",
}
CTX_CAPS = {"qwen3.5:4b-q4_K_M": 64000, "qwen3.5:2b-aux": 64000}

def _ollama_chat(model, provider, message, timeout=120):
    import requests
    base = OLLAMA_BASE.get(provider, "http://aux-node:11434/v1")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "max_tokens": 800,
        "extra_body": {"reasoning_effort": "none"},  # /v1 ignores native think:false
    }
    r = requests.post(f"{base}/chat/completions", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
```

And `hermes_operator_reply(msg, model, provider)`:
- if `provider.startswith("ollama-")`: call `_ollama_chat(...)`
- else (Cloud): `hermes -z "<msg>" -m <model> --provider <provider>`

Wrap the call in a single-flight lock (threading.Lock) so concurrent `hermes -z`
calls don't collide / interleave (a second `hermes -z` started while one is running
will hang the server's single-flight slot for minutes).

## Re-bake recipe (AUX-NODE, Windows host — `ollama create` works, no chtimes block)
```bash
# unload first
curl -sS http://aux-node:11434/api/generate -d '{"model":"qwen3.5:4b-q4_K_M","keep_alive":0}'
# re-bake at 64000
curl -sS http://aux-node:11434/api/create -d '{
  "name":"qwen3.5:4b-q4_K_M",
  "from":"qwen3.5:4b-q4_K_M",
  "parameters":{"num_ctx":64000,"num_gpu":34}
}'
```

## Verify
```bash
curl -s -X POST http://localhost:8777/api/operator/message \
  -H "Content-Type: application/json" \
  -d '{"message":"reply with exactly: M3OK","model":"qwen3.5:4b-q4_K_M","provider":"ollama-m3"}' \
  --max-time 175
# expect: {"ok": true, "reply": "M3OK"}
```

## Caveats
- **2b-aux@64000 unverified this session.** 2b-aux was re-baked at `num_ctx 64000` analogously,
  but its `/v1` forward pass on the 4GB GTX 960 was NOT re-tested. Prior evidence: 2b-aux@65536
  reserves ~6.6GB > 4GB and HANGS; 16384 was the workable cap. Verify before relying on 2b-aux at
  64000 through `/v1` — it may still need <=16384 for the forward pass (the 64000 bake only matters
  if aux tasks actually use that context).
- Single-flight lock is mandatory if the same server also serves Cloud (`hermes -z`) routes.
- `reasoning_effort:"none"` is the OpenAI-standard key `/v1` honors; native `/api/chat` uses `think:false`.
- The hermes 64K floor is hardcoded (`agent/model_metadata.py:133`) and NOT configurable — 64000 is the minimum.
