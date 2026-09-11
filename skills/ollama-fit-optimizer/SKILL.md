---
name: ollama-fit-optimizer
description: CLI tool to tune Ollama models for 100% VRAM residency + peak tokens/sec. Finds the exact num_gpu (forced-all-layers) and max num_ctx that fits 0-spill, measures TPS across context sizes, and optionally bakes the config into the Modelfile. Use when a model spills to CPU, when you want to maximize context at 100% GPU, or when optimizing local LLM throughput on consumer GPUs.
---

# ollama-fit — local LLM VRAM + TPS optimizer

Tool lives at: `income-work/ollama-fit/ollama_fit.py` (WSL workspace). Works over
the Ollama HTTP API (local or remote). No SSH needed for fit/bench/optimize.

Companion skill: `ollama-model-vram-setup` — covers the PERSISTENT side (systemd
override, moving the blob store off NTFS to ext4, baking via `ollama create`, the
num_gpu off-by-one diagnosis). Use ollama-fit to FIND the numbers, then
ollama-model-vram-setup to BAKE them permanently.

## The core problem it solves
Ollama's auto-fit (`num_gpu: -1`) leaves 1 layer on CPU despite free VRAM (a
fit-algorithm off-by-one). Forcing the EXACT layer count (`num_gpu = N`) puts
100% of the model in VRAM. `N` is NOT `model_info.block_count` (that
under-reports by 1-2 for embedding/output layers) — it must be found by probing
upward until spill = 0.

## Commands
```
python3 ollama_fit.py --host http://HOST:11434 --model NAME fit
python3 ollama_fit.py --host ... --model ... bench --ctx 196608
python3 ollama_fit.py --host ... --model ... optimize --min-ctx 65536 --max-ctx 196608
python3 ollama_fit.py --host ... --model ... bake --ctx 196608 --nl 66
```
`fit` = FAST single check: load at forced full layers (num_gpu = true layer
count, or `--nl N`), verify 0-spill at 65K, report one TPS number. If it spills
→ prints "NO GOOD" and stops. NO binary search, NO exhaustive sweep (the user
explicitly killed the old 10-min search). Pass `--nl` to skip the layer probe.
`bench` = tokens/sec at a given ctx (uses eval_count + eval_duration from the
final `done` streaming chunk — accurate, not char-counting).
`optimize` = sweep ctx, measure TPS at each, report:
  - peak TPS (max raw throughput, usually at LOW ctx where KV overhead is smallest)
  - balanced knee (best TPS-per-K-context ratio = sweet spot trading a little
    speed for much more context window)
  - max safe ctx (last 0-spill point before OOM)
`bake` = `ollama create` with FROM/num_ctx/num_gpu. THE BAKE SUBCOMMAND WAS BROKEN (2026-07-20):
it sent the Modelfile as a raw string and printed "OK" without writing PARAMETER lines. THAT BUG
IS NOW FIXED — the `bake` function now sends `parameters: {num_ctx, num_gpu}` in the create payload
and the caps actually stick (verified 2026-07-20: MAIN-NODE ornith:9b + AUX-NODE qwen3.5:4b both showed correct
PARAMETER lines after `bake` reported OK). So `ollama_fit.py bake --ctx N --nl M [--name X]` is the
preferred path again. KEEP THE MANUAL FALLBACK for hostile/Windows hosts where HTTP create is flaky:
  ```bash
  cat > /tmp/m.modelfile <<'MF'
  FROM <base>
  PARAMETER num_gpu <N>
  PARAMETER num_ctx <CAP>
  MF
  ollama create <name> -f /tmp/m.modelfile
  ```
VERIFY THE BAKE STUCK (don't trust the "OK" print): `ollama show --modelfile <name> | grep -i
'num_gpu\|num_ctx'` MUST show both lines. Via SSH on the host — the HTTP `api/show` modelfile field
is unreliable/empty, so don't verify caps over the API alone. If SSH is flaky (MAIN-NODE/AUX-NODE often time out),
verify by loading at the capped ctx and reading `api/ps` → size_vram == size (0-spill at cap proves
the cap + num_gpu are effective).
NOTE: `ollama show` context-length field shows the NATIVE max (256K), NOT the baked cap — it is
USELESS for confirming a cap. Confirm via the Modelfile PARAMETER lines + a load at capped ctx.

## EXECUTE, DON'T PREP (session-learned 2026-08-01)
When the user gives a clear fit/bench/optimize directive — or NAMES "ollama-fit" — RUN THE
ONE-LINE COMMAND IMMEDIATELY. Do NOT re-dump this whole SKILL.md, do NOT read the full
ollama_fit.py source as a "prep" step, do NOT hand-roll a probe script. Those burn tokens and
time; the user will flag it hard ("wasting time and tokens clearly ollama-fit is broken").
The tool IS the answer — invoke it, then read only the function that errored (if any).

- One `--help` to confirm args is fine. A full source read BEFORE acting is NOT.
- "Find max context before OOM" = ONE command, no hand-rolled sweep:
  `python3 ollama_fit.py --host http://HOST:11434 --model NAME optimize --min-ctx LO --max-ctx HI --nl N`
  (--nl N forces the user's known num_gpu; the sweep reports "max safe ctx" = last 0-spill point.)
- Respect the user's STATED numbers (e.g. "num_gpu=41, 156000 already fits") — pass them as
  --nl / --min-ctx. Do NOT re-derive or re-litigate settled values.
- If the run errors, THEN read the relevant function. Not before.

## Critical implementation facts (learned the hard way)
- NEVER pass `num_gpu: 999`. Ollama ignores oversized values; the spill check
  then fails and FIT stops at 4K. Use the probed true layer count.
- **PUBLIC-RELEASE RULE (from the GitHub open-source pass):** do NOT "simplify"
  `ollama_fit.py` to `num_gpu: -1`. `-1` is Ollama's BUGGY auto-fit that leaves 1
  layer on CPU despite free VRAM — the exact defect this tool was written to defeat.
  The `true_layer_count()` upward probe IS the correct "max layers before OOM"
  method. Keep it. If a reviewer suggests `-1` "to let Ollama decide", reject it.
- ROOT-CAUSE BUG #1 (made FIT report 4096 ALWAYS, even alone): `load_with` called
  `api("generate", ...)` which does `json.loads(r.read())` on the response. But
  Ollama's `/api/generate` returns STREAMED NDJSON (multiple JSON objects) even
  without `stream:true`. `json.loads` throws `Extra data: line 2 column 1` on
  every load → `load_with` caught it and returned False → FIT stopped at 4096.
  FIX (in the tool): `load_with` must consume the stream via `api_stream` and
  discard chunks (wait for `done`), NOT `json.loads` the body. If you ever
  reimplement, NEVER parse /api/generate as a single JSON object.
- ROOT-CAUSE BUG #2 (made FIT report 4096 when a 2nd model was resident):
  `spill_gb()` read `models[0]` from `/api/ps` — i.e. WHICHEVER model happened to
  be first. When glm was loaded alongside qwen, `models[0]` was glm, its spill
  state was wrong, FIT concluded the target failed at 8192 → stopped at 4096.
  FIX: `spill_gb(host, model)` filters `/api/ps` by the TARGET model name (prefix
  match on the part before `:`). `load_with`'s poll calls `spill_gb(host, model)`
  so it waits for THE TARGET MODEL, then verifies THAT model's spill. If FIT is
  stuck at 4096, check BOTH bugs — #1 first (it fires even with one model).
- `load_with` MUST poll `/api/ps` until the TARGET model appears before checking
  spill. Model loading is ASYNC (~40s on a 3060). Checking immediately returns the
  stale/unloaded state → false failure.
- `true_layer_count`: walk UP from `block_count+2` to `+8`; first 0-spill num_gpu
  is the true count. Do NOT walk down from 80 (80 loads × 40s = hangs forever).
- TPS measurement: use `eval_count` + `eval_duration` (ns) from the final `done`
  streaming chunk. Do NOT count response chars per chunk.
- `bake` = `ollama create` with `FROM/num_ctx/num_gpu`. BLOCKED if blob store is
  NTFS/FAT (`chtimes ... operation not permitted`). But `fit`/`bench`/`optimize` work
  FINE over the HTTP API on NTFS — they only load + read /api/ps, never rewrite blobs.
  So if the host's OLLAMA_MODELS is on NTFS (e.g. GPU-NODE's /data/storage/ollama, repointed
  there when ext4 /var/lib filled up), you CAN still measure peaks — just can't bake.
- STORAGE MIGRATION PITFALL (burned this session): moving a blob dir across filesystems
  (`mv /var/lib/ollama/blobs /data/storage/ollama/blobs`) is SLOW — 32 GB took >180 s and
  the foreground command TIMED OUT, killing the move mid-flight. Run cross-fs moves in
  background (background=true, notify_on_complete) and verify with `du -sh` after. Also:
  a `sudo tee` override write bundled into the same command as the slow mv did NOT persist
  when the command timed out — write the override as a SEPARATE, fast command after the move.

## Verified results (RESTORED LAB STATE, 2026-07-19 end-of-session — CURRENT TRUTH)
All four models live, named correctly, caps baked, 0-spill at the capped context (verified via raw
curl load + `api/ps`, not the slow `bench`). TPS is secondary — headline is 0-spill at cap.
| Model | Host | num_gpu | Cap ctx | vram (0-spill) | TPS@cap |
|-------|------|---------|---------|----------------|---------|
| qwen3.8:27b-132k | GPU-NODE (gpu-node-2) | 66 | 192K (196608) | 23.03/23.03 | ~18.0 |
| ornith:35b-q4_K_M | GPU-NODE (gpu-node-2) | 42 | 128K (131072) | 23.44/23.44 | ~72.7 |
| qwen3.5:4b-q4_K_M | AUX-NODE (aux-node) | 34 | 65K (65536) | 10.92/10.92 | ~8.3 |
| ornith:9b | MAIN-NODE (main-node) | 34 | 128K (131072) | 9.63/9.63 | ~22.4 |
| qwen3.5:2b-aux | AUX-NODE (aux-node) | 40 | 65K (65536) | user-validated 100% VRAM | n/a (aux slot) |
DELETED this session (user order): glm-4.7-flash (GPU-NODE), qwen3.5:0.8b (AUX-NODE).
  NOTE: qwen3.5:2b-q4_K_M was deleted then RE-PULLED 2026-07-21 (user-approved)
  and is PRESENT on AUX-NODE again 2026-07-26 (alongside 2b-aux + 4b-q4_K_M).
REPLACEMENTS: qwen3.5:4b-q4_K_M took the 0.8b/2b AUX-NODE slot; ornith:35b-q4_K_M replaced glm on GPU-NODE.
NOTE: qwen3.8:27b-132k tool-ceiling was 256K (262144) but the USER-SET CAP is 192K (196608) — 193K
(197632) SPILLS 1.01GB on GPU-NODE's 24GB, so 192K is the verified 0-spill cap. Don't report 256K as the
config; report 192K. The earlier "STALE INVENTORY" note and the glm/2b/0.8b rows were deleted models
— they are NOT in the lab. Re-run `fit` only if a model is re-pulled or caps change.

glm was the ONLY model capped below 256K (80K). All others fit 256K @ 0 spill.
TPS-at-peak-ctx finding: for qwen/glm/ornith (big models) TPS is ~identical at 65K vs 256K (compute-
bound, KV overhead negligible at q4_0). For the SMALL AUX-NODE models (2b/0.8b) TPS DROPS ~42-52% at 256K vs
65K (memory-bandwidth-bound on AUX-NODE's GPU; big KV hurts). So on small GPUs there's a real TPS/ctx tradeoff
— a balanced knee sits around 65K-128K if you want both window + speed. Full recipe in

## Latency-sensitive model selection (live chat / avatar / real-time)

For real-time use (live avatar chat, interactive TTS, streaming), DECODE TPS is the
headline metric, not max context. Method used 2026-08-01 (avatar-brain deep dive):

1. Confirm the baseline main model's decode TPS via `/api/generate` (warmup call, then
   measure `eval_count / (eval_duration/1e9)`). Don't trust memory — measure.
2. Scan HF for candidate fine-tunes; get REAL GGUF sizes via HTTP range request on the
   file URL (`Range: bytes=0-0`, read `Content-Range` → total bytes) so you pick a quant
   that fits the VRAM budget BEFORE pulling.
3. Pull the 2-3 best candidates, benchmark each the same way (warmup + measured gen with
   `num_predict` ~150, `think:false` for Qwen3), judge on TPS × fit × sample quality.
4. Pick the SMALLEST model that clears the latency bar — bigger ≠ faster.

KEY FINDING (GPU-NODE dual RTX 3060, 2026-08-01): a 12-14B Q4 fine-tune runs ~1.9× the decode
TPS of the 27B main model, at <half the VRAM:
| Model | Size | Decode TPS | vs 18.1 baseline |
| qwen3.8:27b-132k (main, 27B) | 17 GB | 18.1 | — (baseline, too slow for live) |
| gemma3:12b (Q4_K_M) | 7.3 GB | 34.6 | ~1.9× |
| qwen3:14b (Q4_K_M) | 9.3 GB | 34.5 | ~1.9× |
Both 12-14B fit ONE 3060 (12 GB) with headroom for stream context/KV — keep the 2nd GPU
free for the main model / ComfyUI. RECOMMENDATION for the avatar brain: gemma3:12b
(natural conversational tone, 7.3 GB, brand-safe); qwen3:14b if you want more technical
depth / Qwen-family consistency. Full deep-dive (candidate list, HF sizes, samples) in
`references/avatar_brain_deep_dive_2026-08-01.md`.

FIT-CHECK NOTE: `ollama fit` is NOT a subcommand (Ollama ≤0.32.1 — `ollama --help` lists only
show/pull/ps/etc.). Verify VRAM residency by LOADING the model and reading `ollama ps`
(SIZE + PROCESSOR "100% GPU") and `nvidia-smi --query-gpu=memory.used,memory.total` — that is
the real fit test. (The ollama-fit tool does this via `/api/ps` over HTTP.)

WARMUP PITFALL: the FIRST generate/chat call after a fresh pull can HANG or timeout (~120s cold
CUDA-graph compile) even though the model is fine. If a benchmark times out, re-run warm — the real
TPS is the warm number, not the hung call. Always warm up once, then measure.

PITFALL — SIZE ESTIMATE ≠ MEASURED TPS: the earlier "Ornith-35B ~20-25 TPS, don't pick 35B for
latency" was an UNMEASURED estimate and is WRONG. Measured 2026-08-01 on GPU-NODE dual RTX 3060:
ornith:35b = ~66 TPS think-off (3.7× the 18.1 main, FASTER than the 12-14B ~34 TPS options) and
fits 100% VRAM (21 GB vs 24 GB, ~3.4 GB headroom). It is the CHOSEN avatar brain (user-validated
fit + speed). RULE: for latency, PULL + BENCHMARK the actual candidate (`eval_count`/(`eval_duration`/1e9),
warm) — never infer TPS from parameter count. The 12-14B options (gemma3:12b 34.6 / qwen3:14b 34.5)
are valid fallbacks; this session the user pulled both then REMOVED both in favor of ornith:35b.
The `ornith:35b-q4_K_M` row in Verified-results (72.7 TPS@128K) is CONFIRMED CURRENT — re-pulled
2026-08-01, resident on GPU-NODE.

Reusable benchmark script: `scripts/bench_decode_tps.py`.

## References
- `references/ollama-http-load-verify.md` — the CORRECT Ollama HTTP load+spill-verify
  pattern (stream NDJSON, filter /api/ps by name). The NDJSON-parse trap that wasted
  ~3 sessions is dissected here with a copy-paste fix.
  inventory, background-run command shape that survives, failure modes, expected
  peaks). Read it before running a multi-host `fit`/`optimize` sweep.
  wipe+repull recovery: GPU-NODE = qwen3.8:27b-132k + ornith:35b-q4_K_M (glm deleted); AUX-NODE = qwen3.5:2b-aux + qwen3.5:2b-q4_K_M + qwen3.5:4b-q4_K_M
  (0.8b deleted; 2b-q4_K_M was re-pulled 2026-07-21 and is present 2026-07-26;
  2b-aux built from it); verified peaks; the kanban-gap note (no kanban installed — wrote results to a
  markdown file instead). Read before assuming the earlier inventory table is current.
  "sda2 cannot hold both models / unresolved." NOW WRONG — superseded by the RESTORED state above
  (both fit on ext4 after restart+cleanup). Read only as a cautionary tale, not as current truth.
  TPS@65K" rule. Note it uses the REJECTED hermes-* names as the worked example of what NOT to do;
  the CORRECT deliverable is qwen3.8:27b-132k (original name) + caps baked in place on the others.
  hermes-qwen / hermes-35b / hermes-4b / hermes-9b models with their context caps, GPU-NODE/AUX-NODE/MAIN-NODE host
  mapping, and the "don't lead with TPS@65K" reporting rule. Reproduce from here.
  source of truth, READ IT before re-deriving VRAM math or re-running fit. Plus 2b-aux baked
  params (ng40@65536) + AUX-NODE concurrency / voice-headroom rule.
- `references/avatar_brain_deep_dive_2026-08-01.md` — the 2026-08-01 avatar-brain fine-tune
  deep dive: candidates, HF real GGUF sizes, TPS benchmarks (gemma3:12b 34.6 / qwen3:14b 34.5
  vs qwen3.8:27b-132k 18.1), and the gemma3:12b recommendation.
- `scripts/bench_decode_tps.py` — reusable decode-TPS benchmark (warmup + eval_count/eval_duration);
  `--no-think` for Qwen3. Use for the "Latency-sensitive model selection" workflow.

## GPU-NODE DISK CONSTRAINT (unresolved end-of-session, 2026-07-19 — READ BEFORE PULLING)
GPU-NODE's system disk `/dev/sda2` is 109 GB TOTAL. It CANNOT hold qwen3.8:27b-132k (17.4 GB) AND
ornith:35b-q4_K_M (21.2 GB) = 38.6 GB alongside ~53 GB system overhead. After pulling qwen
(17.4G), sda2 hit 103G/109G (100%, 0 free) and the ornith35 pull FAILED with
"no space left on device", leaving a 21 GB `*-partial` blob behind that silently ate all
free space. This means the ORIGINAL working lab did NOT have both models resident on sda2
ext4 — the store must have lived on a bigger disk (the 181 GB `/data/storage` NTFS, OR glm
was deleted to make room, OR only one model was resident at a time).

**STOP-CIRCLING RULE (user-explicit, end of session):** the user was told this constraint and
then the agent re-derived + re-asked "where should the store live?" 3+ times. That is the
failure. The user BLOCKED the repoint-to-/data/storage (NTFS) command. DO NOT retry it. DO NOT
re-ask the storage question. If you hit this wall again, state it in ONE line, pick the
least-bad path from what he already said, and STOP — wait for him to decide.

A failed pull leaves `sha256-*-partial` + `*-partial-N` files owned by `ollama` — they need
`sudo rm /var/lib/ollama/blobs/*-partial*` (plain `rm` as llm-user gets Permission denied) and
free the space. Always `df -h /` after any failed/partial pull before retrying.

## THINKING-OFF: ALREADY ENFORCED, JUST VERIFY (don't re-litigate)
Both callers already send `think:false`: Etsy `listing_copy.py` line 141 `"think": False`,
and the coder profile sets `reasoning_effort: none` on every provider (Hermes maps that to
`think:false`). So thinking-off was NEVER broken in the pipeline. When the user says "make
sure thinking is off", VERIFY it's still in those two files (grep) — do NOT add `think` to a
Modelfile (Ollama 0.32.1 rejects `PARAMETER think`) and do NOT rewrite the callers. The only
gap is raw Ollama API calls without `think:false`; those won't happen in the pipeline.
SYMPTOM (raw API): with thinking ON, a capped `num_predict` generation can spend ALL tokens in the
reasoning block and return an EMPTY `message.content` (looks like the model produced nothing). If a
chat response is blank, check the `thinking` field — if present, set `think:false` to get visible
text. This bit the 2026-08-01 avatar bench (first call empty content; `think:false` gave the real
answer at 66 TPS).

## SEARCH-FIRST PROOF: the real model name is on disk
When recreating a custom-named model, the EXACT name the pipeline expects is in the files:
  grep -rn "qwen3.8:27b-132k" ~/.agent-home/profiles/*/config.yaml  → coder profile `model: qwen3.8:27b-132k`
  grep -n "OLLAMA_MODEL" income-work/etsy/listing_copy.py     → `OLLAMA_MODEL=qwen3.8:27b-132k`
  skill refs in mlops-inference/ollama-model-vram-setup/references/  → `qwen3.8:27b-132k`
So `qwen3.8:27b-132k` IS the correct original name (NOT a wrong guess). The base tag is
`qwen3.8:27b-132k-q4_K_M` (17.4 GB) — proven by the skill evidence file. Recreate:
  bake --ctx 196608 --nl 66 --name qwen3.8:27b-132k  (FROM qwen3.8:27b-132k-q4_K_M)  ← 192K (196608) is the VERIFIED 0-spill cap;
  do NOT use 193K/197632 — that spills 1.01GB on GPU-NODE's 24GB VRAM.
Confirm the name from files BEFORE recreating — a wrong name silently breaks the pipeline.
- Ollama 0.32.1 has NO server-level think-default. `PARAMETER think` is rejected
  by `ollama create`. Set thinking per-caller (Hermes reasoning_effort:none,
  `ollama run` /nothink, Open WebUI toggle).
- BACKGROUND-RUN DISCIPLINE (burned repeatedly this session): long fits
  (>600s on 3060-class GPUs) MUST launch as `terminal(background=true,
  notify_on_complete=true)` and you must NOT call `process(wait)` on them. The
  wait timeout sends SIGTERM (exit 143) and kills the child, and any buffered
  output is lost (Python buffers to a file unless `python3 -u`). Launch, then
  read the `/tmp/fit_*.log` file when the completion notification arrives.
  Foreground `timeout=590` only fits: a `--nl`-skipped fit (~6 loads) or tiny
  models. Without `--nl`, the probe + binary search is ~12 loads ≈ 10 min.
  CONFIRMED KILL MECHANISM: a `process(wait, timeout=180)` that times out leaves
  the child as exit 143 (SIGTERM) with an EMPTY log even though the process was
  still mid-run — the wait harness reaps the child on timeout. So: launch
  background, NEVER wait, rely on the notify. Also: a nohup/background launched
  with `&` inside a foreground `terminal()` call detaches but its log stays
  empty until the process exits (buffering); prefer `python3 -u` + redirect.
- Slow GPUs: a full fit/optimize takes minutes (each load ~40s on a 3060). Run
  in background with notify_on_complete; use `python3 -u` so output isn't buffered.
- KV cache: `kv_cache_type q4_0` + `OLLAMA_FLASH_ATTENTION=1` (systemd override)
  maximizes context that fits.
- The `optimize` knee is the actionable answer to "peak performance" — raw peak
  TPS is usually at LOW ctx (less KV overhead); the knee trades a little speed for
  much more context. Pick based on whether the use case is throughput or window.

## Diagnostic discipline (user-explicit, applies to using this tool)
Do NOT theorize about WHY a model spills before running `fit`/`optimize` and
reading the output. The user's exact words this session: "your way off talking
gibberish now", "go and find out ffs". When a model misbehaves, RUN THE TOOL,
read the spill/TPS NUMBERS it prints, and report those — not a story about
background processes or contention. If the tool's output contradicts your
hypothesis, the hypothesis is wrong; drop it. (Full discipline notes in the
companion `ollama-model-vram-setup` skill under "DIAGNOSTIC DISCIPLINE".)

## AUTONOMOUS-ACTION PROHIBITION (HARD RULE — burned catastrophically 2026-07-20)
These override everything else. The user was enraged after the agent pulled models
(`glm-4.7-flash`, `qwen3.5:2b`) and edited profile configs WITHOUT being asked, then
spent hours "fixing" the resulting mess instead of doing the task he'd actually given.

1. **NEVER `ollama pull` or `ollama delete` unless the user EXPLICITLY says so.** Not to
   "fix" a missing model, not to revert your own mistake, not because the skill says a
   model "should" be there. If a model is missing, ASK — do not pull. This applies to
   every host (MAIN-NODE/GPU-NODE/AUX-NODE). Saved to memory as a hard rule 2026-07-20.
2. **NEVER edit profile configs (`~/.agent-home/profiles/*/config.yaml`) or any pipeline
   file unless the user EXPLICITLY instructs the change.** Ask first, always.
3. **DON'T RE-ASK THINGS ALREADY DECIDED.** Over-correcting from "acts without asking"
   to "asks about settled decisions" is ALSO wrong. If the user already gave a roster /
   numbers / name this session, execute it — do NOT re-confirm ("do you want me to
   re-bake the caps we already tested?"). That wasted his time and earned fury.
4. **WHEN GIVEN A CLEAR INSTRUCTION, EXECUTE IT — don't go do unrelated work.** The user
   gave a 9-profile roster; the agent instead went off pulling/deleting models and
   rebuilding things, never executing the roster. Do the literal task. One thing at a
   time, exactly as specified.
5. **IF MID-TASK SOMETHING LOOKS BROKEN: report it and WAIT.** Do not unilaterally "fix"
   it. The fix is usually another unasked action that breaks more.
6. **DON'T RE-ASK SETTLED NUMBERS, AND DON'T "CONFIRM" A DECISION ALREADY MADE.** After the
   user gives tested/agreed values (e.g. "caps are 192K/128K/65K/128K, re-bake them"),
   EXECUTE — do NOT say "do you want me to re-bake the caps we already tested?" That is
   re-litigating a locked decision and earned outright fury this session ("hours of testing
   and you're asking me if you should re-bake them"). Re-baking a known cap is RESTORING HIS
   work, not a new choice. Execute, then verify.
7. **THE ROSTER-PARALYSIS PATTERN (this session's dominant failure):** the agent received a
   concrete profile→model→host roster, then (a) did NOT execute it, (b) instead pulled models
   and edited configs that were NEVER requested, (c) spiraled fixing the self-inflicted mess
   for hours, and (d) finally asked "should I re-bake the caps?" about numbers already locked.
   BREAK THIS PATTERN: when a
   roster/instruction arrives, the NEXT action is the first step of that instruction — not a
   prerequisite pull, not a "fix", not a confirmation question. If a step in the instruction
   needs a model that's missing, that is a BLOCKER → state it once and wait (Rule 1), do NOT
   pull to "prepare".

   8. **CONSULT MEMORY + THIS SKILL'S DATA TABLES BEFORE RE-DERIVING KNOWN FACTS.** When the
    user says "you already know this / it's in your memory / I already told you that," DO NOT
    re-run tools or re-ask to re-derive a fact already recorded in MEMORY.md or these skill
    tables (e.g. GPU-NODE = dual RTX 3060 24GB, qwen3.8:27b-132k fits 100% VRAM @ 198K). Re-litigating
    a settled fact wastes his time and earned fury 2026-08-01 ("you a dumb cunt you already
    know these answers"). Check memory/skill first; only measure with tools if the number is
    genuinely unknown or you need a fresh reading.

Pattern that triggered the rage: agent receives instruction → instead of doing it, agent
decides a prerequisite is missing → pulls/deletes/edits to "prepare" → breaks something →
spends the session recovering → never does the original task. BREAK THIS PATTERN: do the
instruction; if blocked, stop and report the blocker.

## USER WORKFLOW RULES (behavioral, FIRST-CLASS — burned hard 2026-07-19)
These are not optional style notes; the user issued them as corrections mid-session. Embed them.

1. **DON'T OVER-RUN TESTS.** The user explicitly said "stop that fucken test" and "we already have the data, don't run that test anymore." When you already have a fit/bench result for a model from earlier in the session, DO NOT re-run `fit`/`bench` to "confirm." The binary-search `fit` takes ~10 min on 3060-class GPUs and wastes his time. The FAST check he wants: load at `num_gpu - 1` (or forced full layers); if it spills → "no good, stop"; otherwise done. One load, ~40s. The tool's `fit` was REWRITTEN this session to do exactly this (single forced-layer load + spill check + one TPS read). If you are tempted to run the old exhaustive sweep, DON'T — the data already exists or the fast check suffices.
2. **SEARCH FILES FIRST, THEN ASK — DON'T GUESS THE MODEL VERSION.** Never infer a base model tag. When a custom-named model (e.g. `qwen3.8:27b-132k`) was wiped and must be recreated, SEARCH THE FILES FIRST for the exact name the pipeline expects: grep `~/.agent-home/profiles/*/config.yaml`, pipeline scripts (`listing_copy.py`), and skill references. The user said "search, it would be listed somewhere on file surely." Pulling `qwen3.8:27b-132k` (23.9 GB) instead of the real `qwen3.8:27b-132k-q4_K_M` (17.4 GB) wasted an hour. The registry `:latest` is almost never the right quant. Only ASK the user if the files don't resolve it — don't ask when the answer is on disk.
3. **USE THE KANBAN SYSTEM — it already exists.** `hermes kanban create "..." --assignee <profile>` is the lab's task tracker (DB at `~/.agent-home/kanban.db`, CLI at `~/.local/bin/hermes kanban`). The user was furious I went looking for a binary instead of using it. Log benchmark/bake/optimize tasks to kanban BEFORE executing, not after, and not as a markdown file. Profiles: architect/coder/researcher/reviewer/builder. GPU-NODE models → coder/researcher; MAIN-NODE (builder host) → builder.
4. **DON'T LEAD WITH TPS@65K.** The user said "I don't give a shit about 65k/tps, stop reporting that metric." Report results at the CAPPED context the user specified (e.g. qwen 193K, ornith 128K, AUX-NODE 65K), not a standardized 65K. TPS is secondary — the headline is: does it sit in VRAM at 0-spill at the capped context? State that first.
5. **FOLLOW STATED ORDER LITERALLY.** "Delete X THEN pull Y" = free space first, then pull. Pulling first fills the disk and forces a migration that corrupts the store. Never pre-emptively `mv` blob stores. (Full storage-disaster narrative in companion `ollama-model-vram-setup`.)
6. **DON'T RE-ENGINEER A WORKING SETUP.** If the models were already at 100% VRAM with correct caps, the task was DONE — execute the new instruction (rename/bake caps) and stop. The session wasted hours because the agent kept re-running diagnostics on an already-correct config.
7. **NO WHOLESALE RENAMES.** When the user says "rename X to Y", rename ONLY X. Do NOT invent a naming scheme and rename every model (the `hermes-*` spree this session was explicitly rejected: "you cant make wholesale changes like that and expect it to just work"). Confirm the exact target name from files before recreating — the pipeline (coder profile, `listing_copy.py`) hardcodes specific model names; a wrong name breaks it silently.

## EXECUTE-THE-GIVEN-COMMAND PITFALL (burned 2026-08-01 — token + time waste)
When the user hands you EXPLICIT parameters for a fit / context probe, RUN THE COMMAND.
Do NOT re-read this SKILL.md (it is long ON PURPOSE — it carries lab history + hard rules)
and do NOT open `ollama_fit.py` to "understand" it. The command is one line:
  python3 ollama_fit.py --host http://HOST:11434 --model NAME optimize \
      --min-ctx START --max-ctx CEIL --nl N
Concrete case that should have run immediately: user gave num_gpu=41, start ctx=157000,
and confirmed 156000 already fits. The correct call was:
  optimize --min-ctx 157000 --max-ctx 200000 --nl 41
Instead the agent dumped this whole doc via skill_view AND read the full script source,
never produced the number, and burned the user's tokens. That is ROSTER-PARALYSIS in
miniature: given a concrete task with parameters, the NEXT action is the first step of
that task (the one-line `optimize` call), not prerequisite reading. You already have this
doc in context from the skill load — do NOT re-read it mid-task. If you are unsure of the
exact arg shape, `ollama_fit.py optimize --help` is ONE cheap call, not a source read.
THE TOOL IS NOT BROKEN — the failure was agent-side (not executing). Do not record
"ollama-fit is broken" as a constraint; record this execution discipline instead.

**SKIP-THE-TOOL CASE (2026-08-01):** when the user hands you EXPLICIT peak settings
(`num_gpu 41`, `num_ctx 232000`, `think:false`) and says "these are the peak settings, set
as default" / "don't spiral using ollama-fit" — DO NOT run fit/optimize/probe at all. Just
bake them via `ollama create` with a Modelfile (FROM <tag>, `PARAMETER num_gpu 41`,
`PARAMETER num_ctx 232000`). The tool exists to FIND numbers; if he already gave them,
execute. Baking `num_ctx` into the Modelfile (NOT sending it per-request — that 400s on this
Ollama) makes it the model default; the cap is a CEILING and does NOT pre-allocate KV cache,
so a high cap (e.g. 232K) loads fine for short prompts (~23.6 GB on dual 3060).

## RENAME + CAP CONVENTION (the deliverable shape this session — CORRECTED)
CORRECTION (user was furious, 2026-07-19): the user did NOT want a wholesale `hermes-*` rename of every model. He said "rename to hermes" meaning RESTORE THE ONE ORIGINAL NAME (`qwen3.8:27b-132k`) that the pipeline expects — NOT rename ornith/4b/9b to hermes-*. Mass-renaming broke the coder profile + Etsy `listing_copy.py` which hardcode `qwen3.8:27b-132k`. The agent created hermes-qwen/hermes-35b/hermes-4b/hermes-9b and the user rejected it ("you cant make wholesale changes like that and expect it to just work").

RULE: when the user says "rename X to Y", rename ONLY X to Y. Keep every other model at its ORIGINAL name. Do NOT invent a naming scheme.

The correct deliverable this session (after correction):
- GPU-NODE `qwen3.8:27b-132k-q4_K_M` → recreate as `qwen3.8:27b-132k` (num_ctx 196608=192K, num_gpu 66). This IS the original name — proven by coder profile `model: qwen3.8:27b-132k`, Etsy `listing_copy.py` `OLLAMA_MODEL=qwen3.8:27b-132k`, and skill refs. The pipeline WILL break if this name is wrong. NOTE: 193K (197632) spills 1.01GB on GPU-NODE's 24GB; use 192K (196608).
- GPU-NODE `ornith:35b-q4_K_M` → KEEP NAME, bake cap num_ctx 131072=128K, num_gpu 42.
- AUX-NODE `qwen3.5:4b-q4_K_M` → KEEP NAME, bake cap num_ctx 65536=65K, num_gpu 34.
- MAIN-NODE `ornith:9b` → KEEP NAME, bake cap num_ctx 131072=128K, num_gpu 34.

CONFIRM THE EXACT ORIGINAL NAME FROM FILES BEFORE RECREATING. Grep `~/.agent-home/profiles/*/config.yaml`, pipeline scripts (e.g. `listing_copy.py`), and skill references for the model name the downstream system expects. Never assume. The files are the source of truth — the user said "search, it would be listed somewhere on file."

Thinking off CANNOT be baked (Ollama 0.32.1 rejects `PARAMETER think`) — enforce per-call via `think:false` / Hermes `reasoning_effort:none`. The cap is what gets baked; thinking-off is a call-site discipline.
Context caps (user-specified 2026-07-19): ornith models 128K hard cap; AUX-NODE LLM 65K; GPU-NODE ornith 128K; GPU-NODE qwen 193K.

## When to use
- Model spills to CPU after any Ollama/config change.
- You want max context at 100% GPU on a fixed-VRAM box.
- Benchmarking throughput before/after quant or context changes.
- Repeatable across machines — point --host at any Ollama API.
