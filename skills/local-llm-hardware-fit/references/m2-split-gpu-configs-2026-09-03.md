# Split-GPU / per-GPU LLM configs on dual-card boxes (12GB-class)

## Class-level technique

- **Cards without NVLink are a HARD per-card wall.** Two 12GB cards = 24GB total but NOT
  poolable for a single instance beyond tensor-split. A 27B dense model (~21.5GB resident)
  can NEVER be pinned to one 12GB card. Only models that fit one card can live one-per-card.
- **Pinning is a llama-server flag change, not an engine swap.** Run separate instances on
  separate ports, each wrapped in `CUDA_VISIBLE_DEVICES=<n>` (cleanest) or weight-split via
  `-ts 1,0` / `-ts 0,1`. Same binary, same service framework; systemd target presets per
  layout + a switcher script keep configs reproducible.
- **Fit math (Q4 quants, 12GB card):**
  - 13-14B dense ≈ 9-10.5G + KV → fits ONE card at 8-16K ctx (biggest true dual-instance class)
  - 8B vision LM + mmproj projector ≈ 6.5G + 1.4G → fits ONE card with large headroom; a CUDA
    card gives ~2-3× the usable context of an 8GB AMD card for the same model
  - MoE 30B-A3B ≈ 19G of weights → does NOT fit one card despite tiny active params —
    **weights, not active params, are the binding cost**
- **Verify a split layout, don't assume it:**
  - `nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv`
    attributes VRAM per GPU per PID (one model split across both cards shows as the SAME pid
    on two rows — not two models)
  - `curl :PORT/v1/models` per instance confirms which port serves which model
  - `ps -o cmd -p <pid>` reveals the actual flags a running instance was launched with
- Guard scripts should enforce **per-GPU lanes** (render lane vs LLM lane), not global
  "whole box locked" rules — that is what makes heavy-render boxes partially usable.

## GPU-NODE worked example (state verified live 2026-09-03)

- Engine: `llama-server.service` serving **Huihui-Qwen3.8-27B-abliterated-UD-Q4_K_XL**
  (17G GGUF at `/data/storage/models/gguf/`), :8080, 192K ctx single slot, resident
  ~21.5/24GB (GPU0 10.1G + GPU1 11.4G). `comfyui.service` is a PERMANENT resident (idle
  ≈104MB on GPU0). Ollama :11434 still runs but its store is EMPTY (`ollama list` = none).
- Per-GPU wall = 12GB → the resident 27B cannot pin to one card; any split config pairs
  SMALL models one-per-card instead.
- **PROPOSED configs (design only — NOT built, NOT user-approved to build yet):**
  - **R (default, current):** 27B spanned across both GPUs — main brain as today
  - **A (fleet brain):** VL-8B :8080 on GPU0 (camera/vision node) + 14B :8081 on GPU1
    (swarm lane + verifier); swarm goes 2→4-5 lanes with MAIN-NODE+AUX-NODE aux nodes
  - **B (light render):** ComfyUI GPU0 (SDXL/Flux-class fits 12G) + 14B GPU1 — box stays
    partially usable during light renders; Wan 14B video renders still need both GPUs →
    serialize (stop LLM instances) exactly as today
  - 27B remains the default main brain in every config; splits are opt-in layouts.
- Staging plan if approved: qwen3-vl 8B GGUF + mmproj + a 14B Q4 (~10G total) to
  `/data/storage` (110G free at review time — RE-CHECK `df` immediately before any download
  per disk-rule). Models NOT downloaded as of 2026-09-03.
- Camera-node fit (why VL belongs on GPU-NODE): RTSP cam → ffmpeg on MAIN-NODE → frame → GPU-NODE VL endpoint
  → person check → Telegram alert. GPU-NODE stays LLM-only; the MAIN-NODE 8GB AMD card was judged too
  small by the user for serious vision duty.
