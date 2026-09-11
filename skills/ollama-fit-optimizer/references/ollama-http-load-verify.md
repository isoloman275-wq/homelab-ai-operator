# Correct Ollama HTTP API load + spill-verify pattern (reusable)

The ollama-fit tool burned ~3 sessions on a single bug: `json.loads()` on the
`/api/generate` response. Ollama returns STREAMED NDJSON even when you do NOT pass
`stream:true` — the body is multiple JSON objects, one per line. `json.loads` on
the whole body throws `json.decoder.JSONDecodeError: Extra data: line 2 column 1`.
If your load-and-verify function calls `api()` (which does `json.loads(r.read())`),
EVERY load "fails" and your fit stops at the first ctx.

## The correct load (consume the stream, wait for `done`)
```python
import json, urllib.request

def api_stream(host, ep, payload, timeout=600):
    req = urllib.request.Request(
        f"{host}/api/{ep}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:                       # NDJSON: one JSON object per line
            line = line.strip()
            if not line: continue
            yield json.loads(line)

def load_and_verify(host, model, num_gpu, ctx, kv="q4_0"):
    # 1. consume the generate stream until the 'done' chunk arrives
    #    (the response only completes AFTER the model is fully loaded)
    for chunk in api_stream(host, "generate", {
        "model": model, "prompt": "x", "keep_alive": -1,
        "options": {"num_gpu": num_gpu, "num_ctx": ctx, "kv_cache_type": kv},
    }):
        if chunk.get("done"): break
    # 2. read THAT model's spill from /api/ps (filter by name, NOT models[0])
    sp = spill_gb(host, model)
    return sp is not None and sp[0] <= 0.05

def spill_gb(host, model=None):
    d = json.loads(urllib.request.urlopen(f"{host}/api/ps", timeout=15).read())
    for m in d.get("models", []):
        if model is None or m["name"].split(":")[0].startswith(model.split(":")[0]):
            full = m.get("size", 0); vram = m.get("size_vram", 0)
            return ((full - vram) / 1e9, vram / 1e9, full / 1e9, m.get("context_length"))
    return None
```

## Why this matters
- `models[0]` in `/api/ps` is whichever model is FIRST, not your target. If a second
  model is resident (e.g. glm next to qwen), you read the wrong spill → false failure.
  ALWAYS filter `/api/ps` by the target model name.
- Loading is ASYNC (~40s on a 3060). The generate stream's `done` chunk is the only
  reliable "load complete" signal — do not poll a fixed sleep and assume readiness.
- TPS: use `eval_count` + `eval_duration` (ns) from the FINAL `done` chunk, not char counts.

## Run-shape that survives (3060-class GPUs)
- A full `fit` (probe + binary search) is ~12 loads ≈ 10 min > the 600s foreground cap.
  Launch as `terminal(background=true, notify_on_complete=true)`, use `python3 -u`, and
  read `/tmp/fit_*.log` on notification. NEVER `process(wait)` a long fit — the wait timeout
  SIGTERMs the child (exit 143) and discards buffered output.
- With `--nl` (skip the layer-count probe) a fit is ~6 loads ≈ 5 min — fits foreground at 590s.
