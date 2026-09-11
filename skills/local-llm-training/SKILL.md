---
name: local-llm-training
description: Fine-tune small LLMs on lab GPU-NODE.
---

# Local LLM Training (Homelab AI Operator lab)

This skill governs **training** small LLMs on the lab — distinct from
`local-llm-hardware-fit` / `ollama-fit-optimizer`, which only *serve and fit*
already-built models. Training = PyTorch + PEFT/QLoRA + a corpus. That stack is
NOT installed on any lab box by default; this skill covers standing it up.

## HARD RULE — verify before planning (user-explicit)
The user demands plans built from **live-probed facts**, not assumptions.
Before laying out ANY training plan, run the pre-flight probes below and base
the plan on what they return. Do NOT write a plan that assumes "GPU-NODE probably has
torch" or "there's a corpus somewhere" — check, then plan.

## STEP 0 — PRE-FLIGHT PROBES (read-only, no installs, no pulls)
Run these BEFORE proposing a plan. They are the ground truth.

```bash
# GPU-NODE Python env + disk (SSH, Linux box — never cmd.exe/powershell at it)
ssh llm-user@gpu-node-2 'python3 --version; python3 -c "import torch" 2>&1 | head -1; \
  df -h / /data/storage 2>/dev/null | tail -2'

# What models are PULLED on GPU-NODE (NOTE: this is pulled, NOT resident VRAM)
curl -s --max-time 8 http://gpu-node-2:11434/api/tags | python3 -c \
  "import sys,json;d=json.load(sys.stdin);[print(m['name']) for m in d['models']]"

# Te reo / corpus assets already on this WSL box
find /home/user/income-work -iname "*te*reo*" -o -iname "*maori*" 2>/dev/null
ls -la /path/to/projects 2>/dev/null
```

## STEP 1 — CRITICAL MISREAD: /api/tags ≠ VRAM residency
`/api/tags` lists models that are **pulled to disk**, NOT models loaded into
VRAM. Ollama serves ONE model into the pool at a time. Seeing
`qwen3.8:27b` + `qwen3.8:27b-132k` both in `/api/tags` does NOT mean both are in
the 24GB pool — only the currently-loaded one occupies VRAM. Do not conclude
"GPU-NODE is saturated" from the tag list. To see what's actually resident:
`ssh llm-user@gpu-node-2 "ollama ps"` (PROCESSOR column = truth).

## STEP 2 — DISK CONSTRAINT (verified real, 2026-08-20)
GPU-NODE system disk `/dev/sda2` is **92% full (~9GB free)**. A Qwen2.5-2B base
(~4–5GB) + a PyTorch venv + training artifacts will NOT fit on sda2.
**Place the venv + base model + training output on `/data/storage`** (NTFS,
~181GB free). NOTE: NTFS is fine for a PyTorch venv and training files — the
ollama-fit skill's "NTFS breaks ollama blob bakes" warning is UNRELATED (that's
only about `ollama create` blob writes, not Python training).
```bash
ssh llm-user@gpu-node-2 'mkdir -p /data/storage/te-reo-train && python3 -m venv /data/storage/te-reo-train/venv'
```

## STEP 3 — BASE MODEL: trainable vs served-quant
A **served quant is NOT a training base.** `qwen3.5:2b` / `qwen3.5:2b-aux` on
AUX-NODE are q4_K_M GGUF quants — great for inference, cannot be fine-tuned.
Training needs the **full-precision base** from HuggingFace:
- **Qwen2.5-2B-Instruct** (Apache-2.0) — recommended te reo trainable base.
  Train on GPU-NODE (QLoRA ~14–16GB VRAM), then optionally quantize for serving
  (only if the brief requires it — user may NOT want AUX-NODE quantization).
- Do NOT pull or install without explicit user go-ahead (lab hard rule:
  never `ollama pull` / never install on GPU-NODE unasked).

## STEP 4 — CORPUS REUSE (te reo example)
The te reo cleaning toolkit ALREADY EXISTS on this WSL box — reuse it, don't
rebuild:
- `/path/to/projects` — `macrons.py`,
  `spellcheck.py`, `vocab.py` (orthography + macron restoration).
- `/path/to/projects` + `maori_toolkit/` — macOS-built
  version (9/9 tests, per fleet memory).
Clean any public-domain te reo corpus (govt open data, Wikisource Māori, Bible
Society NZ public texts) through these BEFORE training. **Never** bundle
iwi-specific assertions or scrape-affiliated material — user authors cultural
framing; the repo states this explicitly. No training corpus existed on disk as
of 2026-08-20 (`test-te-reo-build.txt` was empty) — collection is step zero of
the actual build.

## STEP 5 — TRAINING WINDOW (respect render blocks)
GPU-NODE has render-blocked windows where LLM inference is OFF-LIMITS:
06:50–09:10, 11:20–13:40, 17:50–20:10 NZT. Train only in FREE windows and
never start a job that would still run at a 10-min buffer cutoff. See
`local-llm-hardware-fit` + `income-work/MASTER_SCHEDULE_TIMETABLE.md` for the
full matrix.

## PITFALLS
- **Don't plan from assumptions.** User will reject a plan not built on live
  probe output ("check before laying out a plan so its accurate").
- **`/api/tags` ≠ resident VRAM** — a long tag list is not saturation.
- **sda2 is full** — always target `/data/storage` for training artifacts.
- **Served quant ≠ trainable base** — `qwen3.5:2b` is AUX-NODE-serve only.
- **No training stack on GPU-NODE by default** — torch/transformers/peft/datasets
  absent until you install (needs user OK).
- **Poker GTO training is on the DO-NOT-MENTION-PUBLICLY list** (user hard
  rule). Te reo training is safe to open-source; poker is not.

## DEPENDENCY-MATRIX TRAP (unsloth + transformers + peft + Qwen2) — verified 2026-08-21
This broke 5 consecutive training attempts. The versions are NOT independent:
- **unsloth 2025.11.1** pins transformers `>=4.51.3, <=4.57.2, !=4.57.0`.
- **trl** (used by unsloth's `get_peft_model` path) needs transformers `>=4.56.1`.
- So the ONLY safe window is **transformers 4.56.1** (satisfies both;
  4.46.2 is too old for trl → `_VALID_DICT_FIELDS` AttributeError; 4.57.2
  breaks unsloth's tokenizer loader → `'dict' object has no attribute 'model_type'`).
- **peft `target_modules`**: `"all-linear"` is NOT accepted by peft 0.23+
  (it iterates the string char-by-char → `Target modules {'a','l','l',...}
  not found`). Use EXPLICIT Qwen2 module names:
  `["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]`.
  Do NOT use `["all-linear"]` either (peft parses it as a 1-element set of the
  string, still fails).
- **Install order**: `pip install 'transformers==4.56.1' unsloth` inside the
  training venv (GPU-NODE `/data/storage` venv, e.g. `/home/llm-user/terea-venv`).
  After install, verify: `python -c "from transformers import AutoTokenizer;
  AutoTokenizer.from_pretrained(BASE)"` returns clean (no `model_type` error)
  BEFORE running the trainer.
- **train.py vs train_unsloth_run.py**: `train.py` only WRITES the run script
  (`train_unsloth_run.py`); it does NOT train. The actual job is
  `python train_unsloth_run.py`. Regenerating via `train.py` is required when
  you patch `target_modules` / base path, then re-run the generated script.
- **VERIFY THE ACTUAL RUN, NOT THE GENERATE-SCRIPT STEP (user-explicit, 2026-08-21).**
  The single biggest source of the 5 failures was reporting "fixed" from the
  WRONG signal: after patching `train.py` and seeing the regenerated
  `train_unsloth_run.py` contain the fix, I claimed victory — but the RUN that
  actually executed was a STALE pre-fix script (cron/background completion
  notices for dead runs drained into the log out of order). The rule: after any
  patch, confirm the LIVE process is running the fixed code AND has passed the
  failing gate (tokenizer load, peft init, first training step printed) before
  declaring success. Read the run log's tail + `nvidia-smi` VRAM climb, never
  the generate-script content. If a background job's completion notice shows an
  OLD error, it is a stale dead run draining — check `pgrep` for the LIVE pid
  and the log's latest step counter, not the last notification.
- **VRAM rule still applies**: unload Ollama (`keep_alive:0`) + confirm no
  ComfyUI render before starting — the 24GB GPU-NODE pool is shared.

## References
  probe results + the te reo toolkit inventory, as a worked example.
