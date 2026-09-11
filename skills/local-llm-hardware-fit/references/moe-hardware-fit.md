# Qwen3.8-Flash-Next MoE — hardware fit guide

## Model specs (Qwen3.8-Flash-Next, open-weight)

| Property | Value |
|----------|-------|
| Architecture | Mixture-of-Experts (MoE), preview of Qwen4 |
| Total params | 125B |
| Active per token | 6B (512 experts: 10 routed + 1 shared) |
| N-gram embeddings | 51B (20M-entry bigram/trigram table) |
| Native context | 262K tokens (extensible to 1M with YaRN) |
| Multimodal | Text, images, video native |
| License | Qwen Community License 1.0 |

### Quant sizes (GGUF, approximate)

| Quant | Weight size | VRAM needed | Fits single 24GB card? |
|-------|-------------|-------------|----------------------|
| Q4_K_M | ~75 GB | 75 GB + KV cache | NO — needs multi-GPU or system RAM spill |
| Q3_K_M | ~55 GB | 55 GB + KV cache | Tight on dual 24GB (spill ~7GB to RAM) |
| Q2_K | ~42 GB | 42 GB + KV cache | Tight on dual 24GB (spill ~6GB to RAM) |
| F16 | ~250 GB | 250 GB | Server-grade only |

### Key benchmarks (vs competitors)

| Benchmark | Flash-Next | Qwen3.8-27B | Claude Opus 4.6 | DeepSeek-V4-Flash |
|-----------|------------|-------------|-----------------|-------------------|
| SWE-bench Pro | 62.5 | 61.7 | 53.4 | 56.0 |
| DeepSWE 1.1 | 58.7 | 42.2 | — | 54.4 |
| Toolathlon Verified | 73.5 | 67.1 | — | 70.3 |
| GPQA Diamond | 91.7 | 89.2 | — | 90.8 |
| LiveCodeBench v6 | 91.9 | 90.3 | — | 90.6 |

## Consumer GPU ceiling

**Single 24GB card (RTX 3060/4060 Ti 16GB/etc.): CANNOT run Flash.** Even Q2 quant (~42GB) exceeds any single consumer GPU. The 6B active-per-token only affects latency/throughput, not the static weight footprint.

**Dual 24GB cards (48GB pooled):** Can fit Q3_K_M (~55GB) with ~7GB spill into system RAM via llama-server multi-GPU offload. Inference speed drops from PCIe inter-card traffic.

**Intel Arc workaround:** SYCL oneAPI backend supports llama-server inference on Arc GPUs. Tradeoff: LLM-only box, no ComfyUI/training/CUDA tooling.

## Hardware paths to local Flash

### Strix Halo (AMD Ryzen AI Max+ 395)
- **128GB unified memory → 96GB GPU-addressable**
- **Bandwidth: ~256 GB/s** (LPDDR5X-8000)
- **Fits:** Flash Q4_K_M (~75GB) comfortably, Q3_K_M even more headroom
- **Token speed:** Flash (6B active) ~35-45 tok/s measured-analog (gpt-oss-120b ≈ 45 on this silicon). DENSE models are the slow case: 27B dense ≈ 14 tok/s — "~10-15" applies to dense, not MoE
- **Form factor:** Mini PC or laptop. POST-DRAM-SHORTAGE pricing: 128GB configs $3.5-3.65K USD (GMKtec EVO-X2 128GB/1TB $3,499 / 128GB/2TB $3,649, in stock; Framework $3,449 pre-order; Minisforum $3,639-3,799). 2025-era "$1,500-2,500" guides are dead prices
- **No CUDA** — no ComfyUI, no training, no video gen
- **Linux support:** ROCm improving, Vulkan backend works for llama.cpp/Ollama
- **Gotcha:** BIOS UMA allocation matters — set to max (96GB) for LLM workloads

### Mac Mini M4 Pro (48GB unified)
- **Bandwidth: 546 GB/s** — double Strix Halo
- **MLX framework** — optimized for Apple Silicon
- **Can run 70B Q4 at ~25-35 tok/s** — noticeably faster
- **macOS only** — no Linux, no Docker, no Ollama CLI
- **Does NOT fit 125B** — 48GB < 55GB minimum

### Dual Intel Arc Pro B60 (2×24GB = 48GB)
- **PCIe-bound between cards** — for Flash's ~27GB spilled experts, speed = system RAM bandwidth → spec DDR5-6400 (2×48GB), not DDR5-5600
- **SYCL oneAPI** — llama-server works, no ComfyUI
- **Fits:** Flash Q4 with spill; daily 27B/14B lanes run one-per-card and BEAT unified boxes (independent bandwidth per card)
- **Build cost:** ~$4.5K AUD as specced (PCPartPicker: 2× B60 @$999, X870 Taichi Creator, 64GB DDR5) ≈ NZ$4.9K
- **Upgrade path:** 3rd B60 (~$1.1K) → 72GB → Flash fully in VRAM, ≈ matches/beats Strix Halo at ~$6K total; verify the board has a 3rd x16 slot BEFORE committing to this story

### Desktop discrete GPU path
- **RTX 6000 Ada ×2 (48GB pooled):** Runs Q3_K_M with minimal spill. Cost: ~$10K+ AUD.
- **RTX 5090 (32GB):** Cannot fit full model — needs spill or lower quant.
- **A100 80GB ×1:** Fits Q4, but server-grade hardware, expensive.

## Speed comparison (Flash-Next Q4, single stream)

| Platform | Bandwidth | Est. tok/s | Notes |
|----------|-----------|------------|-------|
| RTX 5090 (32GB) | 1,792 GB/s | ~80-100 | Can't fit full model — needs Q3 or spill |
| Strix Halo (128GB) | 256 GB/s | ~35-45 | Fits entirely; MoE-active-params rule (dense 27B on same box ≈ 14) |
| Mac M4 Max (128GB) | 546 GB/s | ~20-30 | Faster than Strix, fits 125B |
| Dual Arc B60 (48GB) | PCIe-bound | ~8-12 | Needs RAM spill for 75GB model |
| GPU-NODE RTX 3060s (24GB) | ~336 GB/s | N/A | Doesn't fit — runs 27B at 18 tok/s |

## Economics: local vs API

Flash-Next API pricing: $0.16/M input, $0.47/M output (Qwen Cloud).

Anchor on the user's ACTUAL bill, not estimated token volumes — an assumption once inverted the verdict ("never pays off" → ~3-5yr payback). Actual: ~$120/month API ≈ $1,440/year. Also pin mandatory capability constraints BEFORE comparing: 1M context is user-MANDATORY and favors Flash.
- **Strix Halo / EVO-X2 (≈NZ$7.2K landed):** ~5yr payback at current spend — justified by capability (1M ctx local, sovereignty, no rate limits), not savings
- **Dual Arc build (≈NZ$4.9K):** ~3.4yr payback, faster daily models, 3rd-card upgrade path

The hardware only wins if you need:
1. Data sovereignty (offline inference)
2. Zero latency for interactive fleet workers
3. 1M context window (API has limits)
4. Fine-tuning capability on the base weights
5. Volume that makes API costs significant

## Bottom line for this lab

Current GPU-NODE (2× RTX 3060 / 24GB) cannot run Flash. The nearest feasible paths are:
- **Strix Halo mini PC** — cheapest way to run 125B locally, acceptable speed for batch tasks
- **Mac Mini M4 Pro** — fastest large-model inference, but macOS-only ecosystem
- **Dual Arc Pro B60** — cheaper upgrade path, but still needs RAM spill

For day-to-day fleet work, the current 27B dense model handles most tasks fine. The 125B-A6B shows its edge on long-horizon coding chains and complex tool-use where the bigger parameter count matters. If hitting the 27B ceiling on agent tasks, the jump justifies the hardware investment.
