# AMD Strix Halo (Ryzen AI Max+ 395) for local LLMs

## Architecture overview

The Ryzen AI Max+ 395 (codename "Strix Halo") is an APU combining:
- **16 Zen 5 CPU cores** (up to 5.1 GHz boost)
- **Radeon 8060S GPU** — 40 RDNA 3.5 compute units
- **XDNA 2 NPU** — 50 TOPS (not useful for llama-server today)
- **Unified memory:** up to 128GB LPDDR5X-8000, shared between CPU + GPU
- **Memory bandwidth:** ~256 GB/s theoretical, ~212-276 GB/s measured
- **TDP:** 120-140W under sustained load
- **Form factors:** Mini PCs (4-5L) and laptops

## Unified memory architecture

Unlike discrete GPUs with separate VRAM, Strix Halo shares one physical RAM pool:
- GPU can access up to **96GB** via Variable Graphics Memory (VGM)
- Remaining ~32GB reserved for OS + CPU tasks
- No PCIe bottleneck — GPU sees all memory at full bandwidth
- This is the same concept as Apple Silicon unified memory, but on x86

### BIOS allocation (Windows)
1. Enter BIOS (F2 or DEL at boot)
2. Advanced → AMD CBS → NBIO → GFX Configuration
3. Set UMA Frame Buffer Size to maximum (typically 96GB on 128GB systems)
4. Save and reboot

Or use AMD Adrenalin: Performance → Tuning → Variable Graphics Memory → Custom → 96GB.
Must reboot for changes to take effect.

### Linux allocation
On Linux, set kernel boot parameters like `amdgpu.gttsize` to control GPU memory access.
Keep BIOS UMA small (Auto or 4-8 GB) and let GTT shared pool handle heavy lifting.

## Counterintuitive VRAM split lesson

Setting dedicated VRAM too HIGH can CRASH model loading:
- With only 16GB main memory, the staging "hallway" during load is too narrow
- Data passes through main memory before transferring to VRAM
- **Recommended split: 8-16GB dedicated VRAM / 48-56GB main memory**
- mmap = OFF (frees main memory copy after loading)
- Keep model in memory = OFF (no backup in main memory)

See lilting.ch article for detailed measurements.

## Model fit guide

| Model | Q4 size | Fits on Strix Halo? | Notes |
|-------|---------|-------------------|-------|
| Qwen3.8-27B dense | ~18GB | Yes, easily | Runs fast on single card equivalent |
| Qwen3.8-Flash-Next 125B-A6B | ~75GB Q4 | Yes (96GB alloc) | ~35-45 tok/s (MoE speed = ACTIVE params; dense 27B on this box ≈ 14) |
| Llama 3.3 70B | ~42-48GB | Yes | Room for context headroom |
| GPT-OSS 120B | ~65-70GB | Tight | Fits but limited KV cache space |
| DeepSeek R1 671B | ~380GB | No | Needs multi-node |

## Token speed comparison

Bandwidth is the binding constraint, not compute — but tok/s ≈ bandwidth ÷ ACTIVE-params footprint (per token only the active experts' weights stream through memory), so MoE models run 3-4× the dense rate on the same box:
- **Strix Halo: ~212-276 GB/s** → MoE 5-6B active: gpt-oss-120b measured ≈45 tok/s, Flash ≈35-45; DENSE 27B ≈ 14 tok/s
- **RTX 4090: ~1,008 GB/s** → ~80-100 tok/s (but can't fit 70B without spill)
- **RTX 5090: ~1,792 GB/s** → fastest, but 32GB VRAM ceiling
- **Mac M4 Max: ~546 GB/s** → ~25-30 tok/s on large models

For models that fit comfortably on a 24GB discrete GPU, that GPU will beat Strix Halo 3-4x in speed. Strix Halo's advantage is **capacity**, not speed — it runs models that physically don't fit on any single consumer GPU.

## Software ecosystem

- **Linux:** ROCm improving, Vulkan backend works for llama.cpp/Ollama
- **Windows:** Adrenalin drivers, LM Studio, Ollama support
- **No CUDA:** Can't run ComfyUI, training frameworks, or CUDA-dependent tools
- **Best for:** Large-model inference, coding assistants, agent workloads
- **Not for:** Video generation, training, real-time interactive chat at high speed

## Product examples (128GB configs)

DRAM shortage repriced 128GB boxes hard — 2025-era guides quoting $1,500-2,500 are dead prices; re-verify every quoting session. Verified buying picture (128GB configs, USD):

| Product | Price (USD) | Stock/notes |
|---------|-------------|-------------|
| GMKtec EVO-X2 | $3,499 (128/1TB) – $3,649 (128/2TB) | In stock; cheapest; Newegg matches GMKtec direct to the cent |
| Minisforum MS-S1 Max | $3,639-3,799 (128/2TB) | In stock; only Strix Halo box with dual 10GbE |
| Framework Desktop | $3,449 | Pre-order only; most repairable |
| Beelink GTR9 Pro | $4,349 | 35-day pre-sale; overpriced for identical silicon |
| ASUS Ascent GX10 | $3,999 (1TB) at NVIDIA Marketplace ONLY | NOT Strix Halo — NVIDIA GB10: 128GB + full CUDA, but DGX OS = Ubuntu ARM (x86-only wheels/apps won't run natively). ASUS eShop $6K, NZ retail $11K |

Rules: price per memory tier (64GB ≈ $2K, 128GB ≈ $3.5-3.65K; the 2TB-SSD step is ~$150), match vendor-direct vs marketplace to the cent (scalper listings hit $3.6K+ on sold-out SKUs), and verify NZ shipability per product — Amazon US ships EVO-X2 to NZ but NOT the GX10.

## Economics vs API

Anchor the payback on the user's ACTUAL API bill, never on invented token volumes — an estimated-volume analysis once inverted the verdict ("never pays off" vs the real ~3-5yr payback). Real bill ≈ $120/month = $1,440/year → a ~NZ$7.2K landed box pays back in ~5 years; the purchase is justified by CAPABILITY (1M context locally, sovereignty, no rate limits), not savings.

## Pitfalls

- **Bandwidth ≠ speed.** Don't buy Strix Halo expecting discrete-GPU token rates. It's slower than an RTX 4090 for models that fit, but runs models that DON'T fit anywhere.
- **Quote MoE tok/s from ACTIVE params.** The ~10-15 tok/s figures floating in reviews come from dense models; a 6B-active MoE runs ~35-45 on the same box. Using a dense number in a purchase comparison inverts the recommendation.
- **Re-check NZ shipability and price per product per session.** Same-class boxes differ wildly by channel (NVIDIA Marketplace $3,999 vs NZ retail $11K for the same unit); Amazon's ship-to-NZ flag is per-listing, not per-brand.
- **NPU is marketing.** The 50 TOPS XDNA 2 NPU has no llama.cpp/ROCm integration yet. Ignore it for LLM work.
- **macOS alternative.** Mac Mini M4 Pro 48GB offers 2x bandwidth (546 GB/s) at similar price, but macOS-only ecosystem limits tooling.
- **Thermal throttling on laptops.** Desktop/mini PC forms sustain performance better than thin laptops.
- **VRAM allocation is NOT hot-swappable.** Changing VGM requires a reboot — plan maintenance windows.
