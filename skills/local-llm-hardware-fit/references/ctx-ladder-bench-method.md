# Context-ladder + needle benchmark on a single card (measure, don't model)

Method + measured results from the 2026-09-03 FableVibes bring-up. The technique is the
skill; the numbers are the worked example.

## Why: upstream config.json geometry LIED
KV math from the HF config.json (40 layers × 2 KV heads × head_dim 256 = 80 KiB/token)
predicted Q4_K_M @64K ≈ 12.2G = "doesn't fit a 12GB card". The real GGUF measured **9.1G**.
Published geometry ≠ quantized-GGUF reality (arch nuances, quantized KV, effective layers).
NEVER reject a quant on paper math — measure it live.

## Ladder method (~30 min)
Ascending rungs (e.g. 64K → 98K → 128K → 192K → 256K); per rung:
1. **Safety gate first**: downstream GPU consumers idle (ComfyUI queue 0/0). On a shared
   box whose main model must be stopped for the test: stop → test → restore via EXIT trap,
   and verify restore with a REAL inference answer, not just `systemctl active` (a 503
   "Loading model" body still returns curl success).
2. `CUDA_VISIBLE_DEVICES=<card> llama-server -m <gguf> --port 18081 -ngl 99 -c $CTX -fa on
   --cache-type-k q8_0 --cache-type-v q8_0` (measure WITH the KV-quant flags you'll run).
3. No "listening" → process died → ceiling is the previous rung. **Guard: reject any rung
   with nvidia-smi used > ~11.5G on a 12G card** (fits-at-rest ≠ survives-under-load).
4. Smoke prompt: `17*23`, max_tokens 200, `reasoning_effort:none` + `chat_template_kwargs
   {"enable_thinking": false}` for thinking models (else reasoning eats the answer).
5. Kill, next rung. Best ctx = highest passing rung.

## Needle benchmark at best ctx
Build ~N−4000 tokens of mundane filler (templated sentences with random numbers, ~3.5
chars/token), insert one secret code at depth 10/50/90%, ask for ONLY the code. Grade by
exact substring. Record usage/timings: prompt_n, prefill t/s, gen t/s.

### Measured (one RTX 3060 12G, q8_0 KV, flash-attn)
- **FableVibes Qwen3.6-14B-A3B (MoE, Q4_K_M, 8.5G weights):** 64K=9.1G · 98K=9.6G ·
  128K=10.0G · **192K=10.9G ← best operating point** · 256K=11.7G (guard-rejected).
  Needle 3/3 at 10/50/90% depth @196K; prefill ~886 t/s (~222s for 196K); gen ~27 t/s.
  KV-light MoE goes ~3× the ctx a dense 14B's math suggests — same context as the 27B.
- **Qwen3-VL-8B + mmproj-F16 @64K:** 11.4G; text + vision paths both verified live.

## Notes
- Rigs were /tmp scripts on the box (ephemeral): ladder = stop/gate/loop/load/smoke/kill;
  bench = the filler+needle generator. Regenerate from this spec; keep the EXIT-trap
  restore + health-verify pattern.
- KV-light MoE exception to dense fit-math is the headline: weights bind, but the KV of an
  A3B-class model is tiny — plan per-model, measure per-model.
