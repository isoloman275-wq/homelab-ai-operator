---
name: llama-server-ops
description: Use when serving local LLMs with llama.cpp llama-server.
version: 1.0.0
author: Homelab AI Operator
license: MIT
platforms: [linux, wsl]
---

# llama-server Ops (fit → serve → verify)

Class-level playbook for running llama.cpp `llama-server` as a persistent inference
endpoint (systemd or manual) on multi-GPU boxes. Complements fit/serve/train umbrellas
(`local-llm-workloads` on this lab) — this one covers the llama-server runtime itself.

## Endpoint contract
- OpenAI-compatible: `/v1/chat/completions`, `/v1/models`.
- Liveness: `/health` (returns `{"status":"ok"}`; 503 'Loading model' while weights load).
- Effective params: `/props` — **`n_ctx` is PER-SLOT, not total**; `total_slots` shows parallelism.
- No Ollama API here: `/api/tags` / `/api/ps` don't exist on this endpoint.

## Context/concurrency ceiling (measured: 27B Q4_K_XL on 2x12GB = 24GB pool)
- Ceiling: **`-c 196608 --parallel 1`** = 192K per-request, single slot.
- 256K and 240K OOM **even at parallel 1** — the limiter is COMPUTE BUFFERS (activation
  memory), not KV cache. KV already q4_0-quantized, nothing left to squeeze.
  More context ⇒ smaller quant/model; no retry loop fixes it.
- `--parallel N` divides ctx across slots (parallel 2 = 2x96K). Long-context solo work ⇒ parallel 1.

## Model swap recipe (same-size GGUF)
1. Inventory files on disk FIRST (`ls -lh <model-dir>/`) — never assume what's there.
2. Snapshot the unit: `sudo cp <unit> <unit>.bak.<date>-<tag>`.
3. `sudo sed -i 's|<old>.gguf|<new>.gguf|' <unit>`.
4. `sudo systemctl daemon-reload && sudo systemctl restart llama-server` —
   **daemon-reload BEFORE restart, always** (old unit keeps running otherwise, hit twice).
5. Wait ~90-100s per 17GB of weights, then verify (below).

## Verification: smoke ≠ done
- Smoke (one small inference) proves liveness only.
- For any context-size claim, run a SOAK: push a large prompt (~150K tokens) through
  `/v1/chat/completions`, confirm completion + service healthy after (~267s for 150K on 27B
  Q4 — timeout ≥300s).
- Char-based token estimates UNDERCOUNT badly (est. 150K → actual 384K tokens). Read
  `n_prompt_tokens` from the 400 exceed-context error body and re-scale the prompt.

## Sampling defaults for security/red-team workloads
- Server default: **`--temp 0.4 --top-p 0.92 --top-k 40`** — exploit/payload/counter work
  needs accuracy + reproducibility. 0.9 drifts; 0.1 is rigid/brittle.
- Per-request `temperature` overrides the baked default — raise to 0.6-0.8 only for
  attack-surface brainstorming.

## Fit ladder & context push (measure, don't model)
- NEVER decide fit from config.json geometry math — upstream configs OVERSTATE. Live proof:
  Qwen3.6-14B-A3B per-token math said ~12.2G @64K, real GGUF measured 9.1G (sliding-window/gated
  layers compress KV far below naive math). Load the real GGUF and measure.
- Ladder protocol (single-GPU pin): stop the resident LLM service FIRST (safety gate: render
  queue 0/0, no resident models, GPU util 0%, render-window only, go-flag written), then per
  ctx rung: `CUDA_VISIBLE_DEVICES=1 llama-server -m <gguf> -ngl 99 -c <ctx> -fa on \
  --cache-type-k q8_0 --cache-type-v q8_0 --port 18081`, wait for `listening` IN THE LOG
  (process-alive proves nothing), read VRAM via nvidia-smi on that GPU, smoke-prompt, kill by PID.
  Marginal threshold: >95% of card (11500/12288 MiB) = no usable headroom → step down. Track BEST.
- Measured ceilings (12GB RTX 3060): FableVibes Qwen3.6-14B-A3B Q4_K_M: 64K=9.1G, 98K=9.6G,
  128K=10.0G, **192K=10.9G BEST**, 256K=11.7G reject. Qwen3-VL-8B + mmproj @64K = 11.4G fits.
- Needle benchmark = the only real long-ctx proof: synthetic filler + secret code inserted at
  10/50/90% depth, demand exact retrieval at FULL target ctx; read `timings.prompt_ms` /
  `prompt_per_second` from the response for true pp/tg. Reference result: 3/3 @192K, pp ~886 t/s,
  196K prefill ~222s, gen ~27 t/s. Rerunnable harness: scripts/fittest.sh + scripts/needle_bench.py.
- Vision GGUFs: add `--mmproj <proj.gguf>`; verify BOTH text and image paths (POST a base64
  image_url) — a 200 on text-only proves nothing about the vision path.

## Thinking models: silence reasoning per request
- Thinking distills (Qwen3.x/3.6 Fable-style) dump output into reasoning tokens and eat the
  generation budget. Per request on /v1/chat/completions: `"reasoning_effort":"none"` and/or
  `"chat_template_kwargs":{"enable_thinking":false}`. Verify content is non-empty on a smoke
  prompt before declaring the model usable.

## Verification traps (false HEALTH_OK, false background launch)
- `curl -s .../health` exits 0 even when the body is 503 'Loading model' — a naive
  `&& echo HEALTH_OK` lies. Verify: body contains `"status":"ok"` AND one real inference
  round-trips AND `systemctl is-active` + VRAM back to expected.
- Background launch over ssh: `cat f | ssh host 'cat > f && nohup f ... &'` — the trailing `&`
  backgrounds the WHOLE chain, ssh EOF empties `cat >`, and the script lands 0 bytes (silent
  no-op, empty log). ALWAYS split into two calls: (1) transfer + `wc -c` confirm, (2) launch
  with `nohup ... </dev/null & disown; echo pid=$!`.

## MoE models (sparse activation)
- **Qwen3.8-Flash-Next (125B-A6B)**: 125B total params, 6B active per token, routed across
  512 experts. Same serving flags as dense (`-ngl 99`, `-c`, `--cache-type-k/v`).
  Quant sizes: Q4_K_M ≈ 75 GB, Q3_K_M ≈ 55 GB, Q2_K ≈ 42 GB. Needs multi-GPU offload
  (llama-server shards layers across all visible GPUs automatically).
- **VRAM reality**: even Q2 (~42 GB) needs an 80GB GPU or dual-consumer cards. A single
  24GB card CANNOT run Flash — the weight footprint alone exceeds it. Dual 24GB cards
  (48GB pooled) can fit Q3_K_M with ~3GB headroom for KV cache at modest context.
- **Intel Arc gotcha**: SYCL oneAPI backend works for llama-server inference but does NOT
  support ComfyUI, training, or most CUDA tooling. Your current RTX 3060s serve both LLM
  AND video gen; Arc = LLM only. Consider this tradeoff before building an Arc workstation.
- **System RAM spill**: llama-server offloads layers beyond VRAM capacity into host DDR5
  automatically. This works but incurs PCIe bandwidth penalty vs on-card. The speed gap
  between "all layers on GPU" and "spill to RAM" is measurable — prefer configs that keep
  weights on-card.

## Failure modes
- Found DEAD (inactive, GPUs empty) ≠ wedged — just restart; then `journalctl -u llama-server`
for the death cause.
- OOM at load shows as `failed to allocate CUDA buffer` / `graph_reserve` in journalctl →
  lower ctx (compute-buffer failure), don't retry.
- 'Loading model' 503s are normal for the first minute+ on big GGUFs — wait before probing.
- Shared-GPU boxes: renders/training need the whole pool — stop llama-server first,
restart after (single-pool serialization rule).
