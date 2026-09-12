---
name: local-llm-hardware-fit
description: Fit/upgrade/verify local LLMs on lab GPUs.
---
# Local LLM Hardware Fit (lab GPUs)

The lab runs Ollama on three boxes. Fitting a model means: it fits 100% in VRAM (ZERO CPU
offload), context is set, thinking is off for workers, and you never touch GPU-NODE during a render
window. This skill is the *technique* layer — lab topology + IPs + timetable live in
`lab-health` (CANONICAL) and `income-work/MASTER_SCHEDULE_TIMETABLE.md`. Read those first for
addresses and render-blocked windows; this skill is how to actually fit a model once you know
where it goes.

<<<<<<< HEAD
- **GPU-NODE** = your-gpu-node, Ubuntu, user `llm-user`. **2× RTX 3060 = 24GB pooled (single VRAM pool, models SPAN both GPUs)**. Reachable directly from WSL via SSH (`ssh llm-user@your-gpu-node` or the `ssh m2` alias) and via HTTP `http://YOUR_OLLAMA_HOST:11434`. **GPU-NODE is LINUX — never use cmd.exe/powershell against it** (that was a 30-min session-wasting mistake: Windows commands at a Linux box return garbage).
- **MAIN-NODE** = this WSL box's Windows host, Ollama at `http://<wsl-gateway-ip>:11434` (WSL gateway), model `ornith:9b`.
=======
- **GPU-NODE** = gpu-node-2, Ubuntu, user `llm-user`. **2× RTX 3060 = 24GB pooled (single VRAM pool, models SPAN both GPUs)**. Reachable directly from WSL via SSH (`ssh llm-user@gpu-node-2` or the `ssh m2` alias) and via HTTP `http://gpu-node-2:11434`. **GPU-NODE is LINUX — never use cmd.exe/powershell against it** (that was a 30-min session-wasting mistake: Windows commands at a Linux box return garbage).
- **MAIN-NODE** = this WSL box's Windows host, Ollama at `http://<wsl-gateway-ip>:11434`, model `ornith:9b`.
>>>>>>> b3cb1c441f96038851366108f1708cee781bcfa3
- **AUX-NODE** = aux-node, now **Radeon RX 580 4GB** (was GTX 960; swapped 2026-09-03), Windows, user `Admin` — SSH key auth WORKS (the old "firewalled" note was stale; run Windows commands via `ssh Admin@aux-node 'powershell -NoProfile -Command ...'`, beware quoting hell: write .ps1 locally, pipe in via `$input | Set-Content`, then execute with `-File`). Ollama models: `granite4.1:3b-q4_K_S` (19.5 tok/s, best tool calling) + `qwen3.5:2b-aux` (28.4 tok/s, 100% VRAM @ 64K) + `2b-q4_K_M` spare. **RX 580 ceiling = 2B-class @ 64K**: gfx803/Polaris ROCm only offloads ~50% of 3-4B models (tested qwen3.5:4b → 7 tok/s, unusable). Ollama on AUX-NODE is now the FULL official install (rocm+vulkan dirs); the old stripped CPU-only copy was the reason GPU never engaged. Known quirk: qwen3.5-aux dumps output into the thinking field (empty response).

## STEP 1 — does the model exist? (check upstream FIRST, not our boxes)
When asked about a model NOT in the current roster, do NOT start by curling GPU-NODE/AUX-NODE Ollama. Most
models are cloud-only. Verify externally:
```bash
curl -s "https://huggingface.co/api/models?search=qwen3.8&limit=10" | python3 -c "import sys,json;[print(m['id']) for m in json.load(sys.stdin)]"
curl -s -A "Mozilla/5.0" https://ollama.com/library/qwen3.8 | python3 -c "import sys,re;h=sys.stdin.read();print(re.findall(r'/library/qwen3\.8:([\w.\-]+)',h))"
```
Only probe our boxes when the question is specifically "is X on our hardware."

## STEP 2 — pull it (GPU-NODE is Linux, use SSH or direct HTTP)
```bash
curl -s --max-time 600 -X POST http://YOUR_OLLAMA_HOST:11434/api/pull -H "Content-Type: application/json" -d '{"name":"qwen3.8:27b"}'
# OR on GPU-NODE itself via SSH:  ssh llm-user@your-gpu-node "ollama pull qwen3.8:27b"
```
If the pull 412s with "requires a newer version of Ollama" → the box's Ollama is too old.

## STEP 3 — UPGRADE Ollama (the correct Linux path)
`ollama.com/download/ollama-linux-amd64.tgz` → 9-byte "Not Found" (404). The real binary is on
GitHub releases as a **`.tar.zst`**, and the asset name/tag must match exactly:
```bash
curl -s "https://api.github.com/repos/ollama/ollama/releases/latest" | python3 -c "import sys,json;d=json.load(sys.stdin);print('TAG',d['tag_name']);[print(a['browser_download_url']) for a in d['assets'] if 'linux-amd64' in a['name'] and a['name'].endswith('.tar.zst')]"
ssh llm-user@your-gpu-node "cd /tmp && curl -L -o ollama.tar.zst <URL> && systemctl stop ollama && sleep 2 && tar -C /usr -xf ollama.tar.zst && systemctl start ollama && sleep 3 && ollama --version"
```
KEY GOTCHA: the extracted binary lands at `/usr/bin/ollama`, but the running service resolves
`which ollama` = `/usr/local/bin/ollama` (old). If `ollama --version` still shows old after
extract, the old binary is "Text file busy" (in use) — `stop` the service FIRST, then copy:
`cp /usr/bin/ollama /usr/local/bin/ollama && chmod +x /usr/local/bin/ollama`.
After upgrade, re-pull the model (the 412 was the blocker).

## STEP 4 — REAL LAYER COUNT (NEVER GUESS — read it)
Assuming "Qwen3-27B = 48 layers" is WRONG. Qwen3.8-27B = **65** (`qwen35.block_count`). Discover it:
```bash
ssh llm-user@your-gpu-node "ollama show qwen3.8:27b --verbose" | grep -iE 'block_count|context length|parameters'
# → qwen35.block_count 65   |   context length 262144   |   parameters 27.3B
```
`num_gpu` for 100% GPU = `block_count` + 1 (the nextn predictor layer). For qwen3.8:27b → **66**.

## STEP 5 — build the fit Modelfile + verify 100% VRAM
```bash
ssh llm-user@your-gpu-node "cat > /tmp/mf <<'EOF'
FROM qwen3.8:27b
PARAMETER num_ctx 135168
PARAMETER num_gpu 66
EOF
ollama create qwen3.8:27b-132k -f /tmp/mf"
curl -s -X POST http://YOUR_OLLAMA_HOST:11434/api/generate -H "Content-Type: application/json" -d '{"model":"qwen3.8:27b-132k","prompt":"hi","stream":false,"think":false,"options":{"num_gpu":66,"num_ctx":135168}}' >/dev/null
ssh llm-user@your-gpu-node "ollama ps"
# TARGET:  PROCESSOR = 100% GPU  (NOT 29%/71% or 7%/93% — those mean CPU offload = VIOLATION)
```
- `thinking` is NOT a valid Modelfile PARAMETER for current Ollama — set `think:false` at query
  time (or `reasoning_effort:none` on the Hermes profile). qwen3.8 IS a thinking model; workers
  MUST have thinking off or they emit reasoning tokens that break the tool handshake.
- If `ollama ps` shows <100% GPU: the KV cache at that context is spilling. Lower `num_ctx`
  (132K→128K→96K) until PROCESSOR = 100% GPU. Do NOT leave it at 93% "it's fine" — the user
  wants 100%.
- Context floor: Hermes HARD-BLOCKS sessions where the model reports <64K. 132K is safe.

## STEP 6 — check the timetable BEFORE any GPU-NODE LLM work
GPU-NODE has render-blocked windows (06:50–09:10, 11:20–13:40, 17:50–20:10 NZT) where LLM
inference is OFF-LIMITS (OOM risk with ComfyUI). Creative blocks (09:30–11:19, 14:30–17:49 M–F)
are reserved for the user, not sub-agents. Read `income-work/MASTER_SCHEDULE_TIMETABLE.md`
(Table A + Table B) before starting any GPU-NODE job. Only run in FREE windows, and never start a job
that would still be running at a 10-min buffer cutoff.

## PITFALLS (from a real session that wasted 30 min)
- **GPU-NODE is Linux. Do NOT run `cmd.exe`/`powershell` against your-gpu-node.** The skill `lab-health`
  already says `ssh m2 'bash -s'` — follow it. Windows commands at a Linux box return "Not Found"
  or silently fail and you'll burn the user's time.
- **Don't assume layer count.** Read `qwen35.block_count` from `ollama show --verbose`. Guessing
  48 for a 65-layer model = 17 layers spilled to CPU.
- **`ollama.com/download/*.tgz` 404s.** Use GitHub releases `.tar.zst` with the exact tag+asset.
- **Old binary "Text file busy" after tar extract** — stop the service before copying over it.
- **`thinking` is not a Modelfile PARAMETER** — set it at query/runtime, not in the Modelfile.
- **`ollama ps` PROCESSOR column is the truth** — 100% GPU = fit, anything less = offload violation.
- **Verify-external-before-probe-local** for any model question about a model not in our roster.
- **`--load-mode` 500 on `/api/generate` (Ollama 0.32.14, qwen3.8):** Root cause = official `qwen3.8:27b` ships `draft_num_predict 4` (MTP speculative decoding). The scheduler emits `--load-mode none --spec-type draft-mtp` to the **bundled llama-server**, which (in 0.32.14's Jul-10 binary) rejects the flag → `error: invalid argument: --load-mode` → HTTP 500 on every generate. Confirmed by Ollama issue #17790 (maintainer: default `draft_num_predict` is 4). **FIX: upgrade Ollama 0.32.14 → 0.32.15 (binary-only swap, see STEP 3). Do NOT strip the model's draft param or recreate the model — that needs a full blob copy which fills the disk and fails.** Full recipe in `references/ollama-load-mode-fix.md`.
- **SEARCH BEFORE THRASHING INFRA.** When a model/server breaks, do not guess-and-experiment (e.g. `ollama create` copies that fill the disk, or blindly stripping params). First: read the live error, check the running version (`ollama --version` + `strings <bin> | grep load-mode` to confirm which component emits/rejects the flag), then SEARCH GitHub issues / the web for the exact error string. The user explicitly wants this — "go fetch more information instead of guessing." A 2-minute issue search beats 30 minutes of disk-filling experiments that repeat a past lab-breaking mistake.
- **Disk is the binding constraint on GPU-NODE, not VRAM.** `ollama create` / `ollama pull` copy ~17GB blobs; if `sda2` is near full it fails mid-copy with `no space left on device` and leaves a half-model. NEVER start a copy/recreate without first checking `df -h /` on GPU-NODE. If low, the fix is the binary upgrade (no model copies), NOT a store move (that previously broke the lab).

## Alternative: llama-server (llama.cpp CUDA) — replacing Ollama as primary server

The lab now runs **llama-server** (llama.cpp compiled with CUDA) as the primary LLM server on GPU-NODE
instead of Ollama. Ollama is kept as a backup/model-management tool. The same fit rules apply:
100% VRAM residency, no CPU spill, 99 GPU layers.

### When to use llama-server vs Ollama
- **llama-server** (port 8080): daily driver — ~10% faster than Ollama, leaner VRAM footprint,
  full control over KV cache type, context size, flash-attention. Hermes OpenAI-compatible API at
  `/v1`. Use for all production inference.
- **Ollama** (port 11434): model management (`ollama pull/list/rm`), quick model swaps,
  uncensored model serving. No model loaded by default — load on demand.

### Building llama-server with CUDA on GPU-NODE
Full reference: `references/llama-server-deploy.md`. Short form:
```bash
# Prerequisites: CUDA 12.8 toolkit installed (cuda-nvcc-12-8 + cuda-nvvm-12-8)
ssh m2
cd /tmp && remove the llama.cpp checkout (`rm -r llama.cpp`) and re-clone: git clone https://github.com/ggml-org/llama.cpp.git --depth 1
cd llama.cpp
export PATH=/usr/local/cuda-12.8/bin:/usr/local/cuda-12.8/nvvm/bin:$PATH
export CUDA_HOME=/usr/local/cuda-12.8
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc
cmake --build build -j2 --target llama-server
# Install binary + shared libs:
cp build/bin/llama-server /usr/local/bin/
cp build/bin/libllama*.so* /usr/local/lib/
ldconfig
```

### Shared library trap
`llama-server` links against `libllama-server-impl.so`, `libllama-common.so`, `libmtmd.so`, and
`libllama.so` — all built in `/tmp/llama.cpp/build/bin/`. If these are not copied to
`/usr/local/lib/` + `ldconfig`, the binary exits with `status=127` (shared library not found).
Copy ALL `.so*` files from the build dir, then run `ldconfig`. Verify with `ldd /usr/local/bin/llama-server | grep "not found"`.

### Per-GPU pinning & split configs (dual-card boxes)
Cards without NVLink are a HARD per-card wall (12GB on a 3060): a 27B dense (~21.5GB) can
NEVER pin to one card — only models that fit one card can live one-per-card. Pinning is a
llama-server flag change (no engine swap): separate instances/ports, each in
`CUDA_VISIBLE_DEVICES=<n>` or `-ts 1,0`/`-ts 0,1`. Fit math (Q4): 13-14B dense ≈ 9-10.5G+KV
→ one card @ 8-16K ctx; 8B VL + mmproj ≈ 8G → one card w/ headroom; MoE 30B-A3B ≈ 19G of
weights → does NOT fit one card (weights, not active params, bind) — BUT KV-light MoE is
the exception: FV Qwen3.6-14B-A3B Q4_K_M measured 10.9G on ONE 3060 at **192K ctx** (needle
3/3), because its KV is tiny. Per-model, measure-per-model. Verify layouts with
`nvidia-smi --query-compute-apps=...` (same pid on two GPUs = one split model), per-port
`/v1/models`, and `ps -o cmd -p <pid>`. GPU-NODE preset configs + camera-node plan:
`references/m2-split-gpu-configs-2026-09-03.md`.

### VRAM budgeting for 27B hybrid-attention models (Qwen3.8 architecture)
This is the critical calculation for fitting a 27B model on 24GB:
- **Qwen3.8-27B has 64 layers, but only 16 are full-attention.** The remaining 48 are
  Gated DeltaNet (linear-attention) with a fixed-size state that does NOT grow with context.
- **KV cache only scales with the 16 full-attention layers.** At q4_0 KV cache with 128K ctx:
  ~2.2GB total. At q8_0: ~4.3GB. This is why a 27B model fits in 24GB at 128K — a full-attention
  27B would need ~8-9GB for the same KV cache.
- **Unsloth UD-Q4_K_XL** (17.9GB) + 128K q4_0 KV cache (~2.2GB) + inference buffers (~1.5GB) =
  **~21.4GB total** — 2.4GB headroom on 24GB. Verified working.
- **KV cache type matters more than weight quant.** Switching q4_0 → q8_0 at 128K adds ~2GB;
  switching Q4_K_XL → Q5_K_XL adds ~2.3GB. For this model: prefer q4_0 KV cache + better
  weight quant every time.

### MoE models (Qwen3.8-Flash-Next) — consumer GPU ceiling
MoE models have a fundamentally different VRAM profile from dense models:
- **Weight footprint is TOTAL params, not active params.** Qwen3.8-Flash-Next is 125B total,
  so even at Q4 quant the GGUF is ~75 GB. The 6B active-per-token only affects latency/throughput,
  not the static weight size on disk or in VRAM.
- **Token SPEED is the reverse: set by ACTIVE params, not total.** Per token only the active
  experts' weights move through memory (tok/s ≈ bandwidth ÷ active-params Q4 footprint); a dense
  model moves ALL weights every token. Same silicon, measured: gpt-oss-120b (5.1B active) ≈ 45
  tok/s vs dense Qwen3.6-27B ≈ 14 tok/s on Strix Halo's 256 GB/s → Flash-Next (6B active)
  realistically 35-45 tok/s. NEVER quote dense-model tok/s for a MoE model. Prefill of long
  prompts stays the slow phase regardless.
- **Single 24GB card CANNOT run Flash.** Even Q2 quant (~42 GB) exceeds any single consumer GPU.
  Dual 24GB cards (48GB pooled) can fit Q3_K_M (~55 GB) with ~7GB spill into system RAM.
- **Intel Arc workaround:** SYCL oneAPI backend supports llama-server inference on Arc GPUs,
  but NO ComfyUI/training/CUDA tooling. Tradeoff: LLM-only box vs dual-purpose. Dual Arc Pro
  B60 (2×24GB) build ≈ NZ$4.9K: Flash runs with ~27GB expert-spill to DDR5 (that spill's speed
  = RAM speed — spec DDR5-6400, not 5600), but two INDEPENDENT cards run daily 27B/14B lanes
  simultaneously faster than any unified-memory box (no shared bus), and a 3rd B60 (~$1.1K)
  lifts Flash fully into VRAM later. Platform rule: unified-capacity boxes win ONLY on models
  that don't fit discrete VRAM; for ≤32B dense workloads dedicated-bandwidth cards are 3-4× faster.
- **Strix Halo (AMD Ryzen AI Max+ 395):** 128GB unified memory → 96GB GPU-addressable. Runs
  Flash Q4 at ~35-45 tok/s (MoE speed = active params — the "~10-15" figure was the DENSE case).
  128GB configs now $3.5-3.65K USD post-DRAM-shortage (≈NZ$7.2K landed). No CUDA. See
  `references/strix-halo-local-llm.md` for full guide.
- **Mac Mini M4 Pro (48GB):** 546 GB/s bandwidth → ~25-30 tok/s on large models. Faster than
  Strix Halo but macOS-only ecosystem. Does NOT fit 125B (48GB < 55GB minimum).
- Full spec sheet, benchmarks, and quant table: `references/moe-hardware-fit.md`.
- **Bottom line for this lab:** GPU-NODE (2× RTX 3060 / 24GB) cannot run Flash. STANDING CONSTRAINT:
  the primary local LLM must do 1M context (user-mandatory) → Flash-Next + YaRN is the target,
  not a bigger dense model. Verified buying picture: GMKtec EVO-X2 128GB/2TB $3,649 USD in
  stock (Newegg/GMKtec direct match) ≈ NZ$7.2K landed via Amazon US (ships to NZ, GST-inclusive);
  ASUS Ascent GX10 (CUDA, 128GB, GB10, ARM-only DGX OS) is $3,999 at NVIDIA Marketplace but NOT
  Amazon-shippable to NZ → NZ$11K at PB Tech = dead at that price. Decision shape: EVO-X2 =
  turnkey inference brain (Flash 35-45 tok/s, x86 everything-just-works); Arc B60×2 build =
  NZ$4.9K, slower Flash but faster daily lanes + upgrade path. Either way GPU-NODE stays the
  ComfyUI/render node — the split-box architecture ends the shared-VRAM collision that kills renders.

### Correct llama-server flags for 24GB / 27B
```bash
llama-server \
  -m /path/to/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  --host 0.0.0.0 --port 8080 \
  -ngl 99 \
  -c 131072 \
  --flash-attn 1 \
  --cache-type-k q4_0 \
  --cache-type-v q4_0 \
  --jinja \
  --temp 0.7 --top-p 0.95 --top-k 40 \
  --cont-batching
```
**DO NOT use `--fa 1`** (older flag name, now `--flash-attn 1`).
**DO NOT use `--no-think`** (does not exist in llama.cpp).
**DO NOT enable MTP/speculative decoding** (`--spec-type draft-mtp`) — the MTP head adds ~1.5GB
VRAM overhead and pushes the 17.9GB + 128K q4_0 KV cache past 24GB. The Unsloth UD-Q4_K_XL
GGUF already has the MTP head stripped for size.

### 100% VRAM rule — verified
After loading, verify with `nvidia-smi`:
- GPU0: ~9-10GB used (weights + KV cache split)
- GPU1: ~10-11GB used
- **Total: 21-22GB of 24GB — all GPU, zero CPU spill.**
- If `nvidia-smi` shows less than 90% of the model's weight size on GPU, reduce `-c` (context)
  or switch to q4_0 KV cache. Do NOT leave partial offload.

## PITFALLS (continued)

- **Upstream config.json OVERSTATES fit — measure, don't model.** KV math from the HF
  config.json predicted FV 14B-A3B Q4 wouldn't fit a 3060 even at 64K (12.2G); the real
  GGUF measured 9.1G @64K and 192K fit at 10.9G. Paper geometry ≠ quantized reality.
  Live ladder: load → nvidia-smi → smoke prompt → kill, ascending ctx, guard-reject rungs
  >11.5G. Method + numbers: `references/ctx-ladder-bench-method.md`.

- **Partial Ollama blobs fill root disk.** Failed `ollama pull` leaves `-partial` files at
  `/var/lib/ollama/blobs/sha256-*-partial*` that can consume 17GB+ and fill the root disk to
  100%. Check `df -h /` after any failed pull. Clean up with:
  `rm -f /var/lib/ollama/blobs/sha256-*-partial*`
  This is the #1 cause of "root disk full" on GPU-NODE after failed model pulls.

- **llama-server restart storm.** If the unit file has wrong flags, llama-server exits
  immediately and systemd restarts it every 10s — the restart counter climbs to 100+ in
  minutes. Always `systemctl stop` before editing the unit file, then `daemon-reload` + start.
  Check the journal immediately after start: `journalctl -u llama-server.service --no-pager -n 20`.

## OVERLAP NOTE
This skill overlaps with `lab-health` (topology/timetable) and `hermes-kanban-fleet` (worker
model routing). `lab-health` is the canonical topology source; this skill is the *fit technique*
layer. The background curator should consolidate if desired — they share the "GPU-NODE is Linux /
single VRAM pool" truth but this skill adds the layer-count + upgrade-URL + PROCESSOR-check
recipe that neither currently holds explicitly.

## Reference files
- `references/moe-hardware-fit.md` — Qwen3.8-Flash-Next MoE model specs, quant sizes, VRAM minimums, consumer GPU ceiling, economics vs API.
- `references/strix-halo-local-llm.md` — AMD Strix Halo (Ryzen AI Max+ 395) unified memory architecture, BIOS setup, product examples, token speed, pitfalls.
- `references/llama-server-deploy.md` — full llama-server build + deploy + systemd service playbook for GPU-NODE
- `references/ollama-load-mode-fix.md` — repairing CPU-offload load mode to 100% GPU
- `references/rx580-amd-fit-2026-09-03.md` — AMD Radeon (gfx803) on Ollama: full-install fix, RX 580 fit ceilings, 2-4B tool-calling bake-off
- `references/m2-split-gpu-configs-2026-09-03.md` — per-GPU pinning / split-config technique + GPU-NODE layout presets (R/A/B), verified 2026-09-03
- `references/ctx-ladder-bench-method.md` — single-card ctx ladder + needle benchmark (measure-don't-model), FV@192K worked example, verified 2026-09-03


## Privileges note

Some system-level commands (package installs, service restarts, writing to /usr) may need elevated privileges. Prefix those specific commands with your privilege tool of choice if your user is not already privileged.

## Network endpoints used

This skill reads public catalog data to size models correctly:
- `https://huggingface.co/api/models?search=<term>` — model metadata (parameter counts, file sizes) for VRAM math
- `https://ollama.com/library/<model>` — Ollama model catalog pages (sizes, quant variants)

It also talks to YOUR OWN local inference server (e.g. `http://YOUR_OLLAMA_HOST:11434` — the standard Ollama port on your machine or LAN). No data leaves your network except the public catalog reads above. No API keys are required for any endpoint.
