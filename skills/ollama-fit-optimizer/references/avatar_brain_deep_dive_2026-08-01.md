# Avatar brain — finely-tuned model deep dive (2026-08-01)

Goal: find the most adequate finely-tuned conversational LLM that fits GPU-NODE VRAM AND is
substantially faster than qwen3.8:27b-132k (~18 TPS) for a live avatar chat loop
(LLM → Kokoro TTS → VB-Cable → OBS → VSeeFace → TikTok LIVE). qwen3.8:27b-132k stays GPU-NODE's
MAIN LLM; the avatar gets a SEPARATE resident model during streams.

## Baseline (measured, not assumed)
- qwen3.8:27b-132k on GPU-NODE, 198K context, 100% VRAM both GPUs: **18.1 decode TPS**
  (150-tok warm gen, eval_duration 8.27s). Confirmed too slow for snappy live chat.

## Candidates considered (HF real GGUF sizes via Range request)
- qwen3-14b Q4_K_M ........ 9.00 GB
- qwen3-8b Q4_K_M ......... 5.03 GB
- qwen3-30b-a3b Q4_K_M .... 18.56 GB (MoE, ~3B active — but 18.5GB, thin margin on 24GB)
- gemma3-12b Q4_K_M ...... 7.30 GB
- gemma3-4b Q4_K_M ....... ~3 GB est. (even faster, less depth)
- ornith-1.0-9b Q4_K_M ... 5.70 GB (coding/agent flavor — not conversational)
- ornith-1.0-35B ........ ~20 GB (fits both GPUs but ~20-25 TPS, NOT faster)
- magnum-v4-12b (bartowski) — top roleplay/companion fine-tune; Ollama pull with tag
  `Q4_K_M` FAILED (repo uses a different quant-tag scheme) — retry with correct tag if
  max-persona is wanted.

## Pulled + benchmarked (GPU-NODE, dual RTX 3060, thinking off)
| Model | Size | Decode TPS | Sample quality |
| qwen3.8:27b-132k (main) | 17 GB | 18.1 | baseline, too slow |
| gemma3:12b | 7.3 GB | 34.6 | natural, on-topic ("Start by installing LM Studio…") |
| qwen3:14b | 9.3 GB | 34.5 | task-oriented, slightly more technical depth |

## Decision
- RECOMMENDED avatar brain: **gemma3:12b** (34.6 TPS, 7.3 GB, fits one 3060 with headroom,
  natural voice, brand-safe, multimodal for future scene cues).
- ALTERNATIVE: **qwen3:14b** (34.5 TPS, 9.3 GB) if the AI-tools persona needs more technical
  depth / Qwen-family consistency.
- NOT chosen: Ornith-35B (slower despite being "finer"); 8B would be faster (~50-60 TPS) but
  less depth — optional if max speed is wanted.
- Both gemma3:12b + qwen3:14b are PULLED + live on GPU-NODE but NOT yet wired into the avatar loop.
  Awaiting user ratification of the pick, then update AVATAR_INTEGRATION_ARCH.md LLM section
  + memory, then build the loop.

## Method reused (see ollama-fit-optimizer SKILL.md "Latency-sensitive model selection")
1. measure baseline TPS via /api/generate (eval_count/eval_duration)
2. HF Range request for real GGUF bytes before pulling
3. pull + benchmark candidates, pick smallest that clears the latency bar

## FINAL OUTCOME (2026-08-01, end of session — SUPERSEDES Decision above)
- User REJECTED gemma3:12b + qwen3:14b ("remove both") and directed ornith:35b.
- Verified: `ollama pull ornith:35b` (21 GB) → loads 100% VRAM (21 GB, ~3.4 GB headroom across
  the two 3060s, 0 offload). Decode TPS = **66.5 TPS think-off** (3.7× the 18.1 main, FASTER than
  the 12-14B ~34 TPS options). Empty `content` on first call = thinking block; `think:false` yields
  the real answer.
- CHOSEN avatar brain = **ornith:35b** (user-validated fit + speed). gemma3:12b + qwen3:14b were
  removed from GPU-NODE. qwen3.8:27b-132k stays MAIN LLM.
- CORRECTION: the "Ornith-35B slower despite being finer" claim in Decision + candidates was an
  UNMEASURED estimate — it is actually the FASTEST option tested. See ollama-fit-optimizer SKILL.md
  "Latency-sensitive model selection" pitfall (now corrected).
- `ollama fit` is NOT a subcommand (≤0.32.1); verify fit via `ollama ps` + `nvidia-smi`.
