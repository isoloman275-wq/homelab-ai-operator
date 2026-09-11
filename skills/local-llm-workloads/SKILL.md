---
name: local-llm-workloads
description: Run LLM workloads on the lab's local Ollama machines (MAIN-NODE/GPU-NODE/AUX-NODE) across the full lifecycle — FIT a model to a GPU (pull, real layer counts, 100% VRAM residency), SERVE it behind a conversational app (/v1 call shape, voice-out, LAN guards), TRAIN/fine-tune small models on GPU-NODE (unsloth, corpora, render-block windows). Use for "pull model X", "will Y fit in VRAM", "build a chat/tutor/quiz app on our local model", "fine-tune on GPU-NODE", "te reo training", or any local-model workload on the lab GPUs.
version: 1.0.0
author: Homelab AI Operator
license: MIT
platforms: [linux, wsl]
---

# Local LLM Workloads (fit → serve → train)

Umbrella for running models on the lab boxes. One lifecycle, three phases; each phase
has a condensed playbook here and the full archived playbook in `references/`.

Tool-depth lives in bundled skills — cross-reference, don't duplicate:
`ollama-models` (GPU-NODE Ollama management), `ollama-fit-optimizer` /
`ollama-model-vram-setup` (100%-VRAM tuning), `llama-cpp` / `serving-llms-vllm`
(alternate runtimes), `home-lab-management` (machine roles, timetable, VRAM-sharing rules,
the `lab-health` model matrix).

## When to use
- User asks to pull/install/run a model on MAIN-NODE/GPU-NODE/AUX-NODE, asks "will X fit", or complains a model is CPU-offloading.
- User wants a chat/quiz/tutor app powered by a local model (P6 Kaitiaki Tamariki family).
- User wants to fine-tune on the lab (e.g. te reo corpora on GPU-NODE).

## HARD RULES (all phases)
- **Check the timetable BEFORE any GPU-NODE LLM work** — renders and crons share the GPUs.
- **Verify before planning**: probe upstream/liveness first; never plan from memory of what's installed.
- Idle ≠ free: confirm no render is running and Ollama is unloaded before grabbing the 24GB pool.

## Phase 1 — FIT (get the model resident at 100% GPU)
1. Does the model exist upstream? Check HF/Ollama library FIRST, not our boxes.
2. Pull it (GPU-NODE is Linux — SSH `llm-user@gpu-node-2` or direct HTTP; never cmd.exe/powershell).
3. Upgrade Ollama via the correct Linux path when needed.
4. READ the real layer count / context length / param count from the model — NEVER guess.
5. Build the fit Modelfile; verify `ollama ps` shows `PROCESSOR = 100% GPU`. 29%/71% or
   7%/93% splits = CPU offload = VIOLATION (fix pattern in
   `references/ollama-load-mode-fix.md`).
6. Re-check the timetable, then load.

## Phase 2 — SERVE (conversational apps on the served model)
- Use the proven `/v1` call shape for small qwen models — do NOT "fix" it; watch the
  "/v1 double path" 404 client-config trap.
- Route plain chat DIRECT to `/v1` — never through the agent loop (latency reality: plan UX around it).
- Voice-out: browser `speechSynthesis` (zero-install, kid-safe).
- Architecture stays thin: static frontend + small HTTP chat backend
  (working example: `scripts/kaitiaki_tutor_backend.py`); quiz/tutor variant turns
  activities into mini-GAMES, age-safety from the start.
- Serving over LAN? ADD the static path-traversal guard.
- Delegation pitfall: sub-agents burned 600s rebuilding what existed — point them at this skill.

## Phase 3 — TRAIN (fine-tune small models on GPU-NODE)
- STEP 0 preflight probes (read-only): GPU-NODE python env + disk, what's pulled vs RESIDENT.
- CRITICAL MISREAD: `/api/tags` lists PULLED models, NOT VRAM residency (`/api/ps` does).
- Disk constraint (real): GPU-NODE root fs is tight (~12–14G free) — stage big bases on the
  `storage` Samba share; check free space before any large transfer.
- Base model: trainable weights ≠ served quant — you cannot fine-tune the served GGUF.
- Corpus reuse: te reo assets already on the WSL box — check before regenerating
- Training window: respect render blocks; long trains go overnight.
- Dependency-matrix trap (verified 2026-08-21): unsloth + transformers + peft + Qwen2
  versions must match exactly — pin the verified matrix, don't float.

## Support files
- `references/ollama-load-mode-fix.md` — repairing CPU-offload load mode to 100% GPU.
- `scripts/kaitiaki_tutor_backend.py` — proven thin quiz/tutor backend.
