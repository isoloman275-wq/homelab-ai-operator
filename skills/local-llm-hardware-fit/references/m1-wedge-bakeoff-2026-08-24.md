# MAIN-NODE wedge + bake-off (2026-08-24 session) — verified on Windows-host Ollama

Session detail backing the fit technique. MAIN-NODE = RX 5700XT 8GB, Ollama runs on
the WINDOWS host, driven from WSL via `http://172.21.192.1:11434` and
powershell.exe one-liners.

## 1. The MAIN-NODE OLLAMA WEDGE — root cause + working fix

SYMPTOM: base `ornith:9b` (128K ctx, 9.6GB) resident forever; generate calls
time out; killing llama-server respawns it within seconds WITH THE MODEL
RELOADED; per-model `keep_alive:0` unload attempts never stick.

ROOT CAUSE: timed-out/cancelled requests SIT IN OLLAMA'S REQUEST QUEUE. Each
llama-server kill → next queued job re-requests the model → reload-loop at
`-c 131072` (128K KV on an 8GB card) → wedged again. An "unload" prompt is
itself another queued request that re-pins the model.

WORKING FIX PROTOCOL (verified twice in one session):
1. `Stop-Process -Name llama-server -Force` AND `Stop-Process -Name ollama -Force`
   (kills serve → wipes the queue — this is the actual point).
2. Restart serve (`Start-Process ...ollama.exe -ArgumentList 'serve' -Hidden`).
3. IMMEDIATELY load the intended target with `keep_alive:-1` so IT owns VRAM.
4. Verify `/api/ps`: target resident, correct context_length, nothing else.

DO NOT fight it with per-model unloads — they feed the loop.

## 2. Max-fit numbers measured on MAIN-NODE (8GB)

- ornith:9b-64k @ num_ctx 65536: **7.4GB** — fits, max-fit.
- qwen38-9b (Qwen3.8-9B-Distill Q5_K_M, 6.6GB weights): @64K wants **8.1GB** —
  over-committed vs 8GB physical → KV spillover → measurable accuracy loss.
- num_gpu probe for a 9B Q5 on this card: **41 OK, 42 OOM** (probe upward).

## 3. Bake-off result (20-task deterministic-oracle battery, serial)

| Model @true 64K | Pass | Avg/task | Fails |
|---|---|---|---|
| ornith:9b-64k | **19/20** | ~1.9s | t09 reverse-typo quirk |
| qwen38-9b | 17/20 | ~2.2s | t08 letter-count, t09, t19 decimals |

- Speed parity warm (~40+ tok/s both). Failure sets DON'T overlap between the
  models → each is a useful cross-model verifier for the other (observer
  independence).
- BENCH HYGIENE LESSON (user caught this): request-level `options.num_ctx`
  SILENTLY OVERRIDES the baked Modelfile cap. First bench round ran both
  models at 8K while believing they were at 64K ("the ornith:9b-64k reads only
  8k context in ollama ps"). ALWAYS read `/api/ps` context_length BEFORE
  trusting benchmark numbers, and bench at the OPERATING config.

## 4. Installing an HF GGUF onto remote Windows-host Ollama

The HTTP blob-upload path (`POST /api/blobs/sha256:<digest>`) fails here even
with a matching hash (digest-format error), and `api/create FROM sha256:` then
errors "pull model manifest: file does not exist". WORKING PATH:
1. Download the GGUF to a Windows-visible path (e.g. `C:\Users\Admin\hf_models\`).
   Resume support works: `curl -sL -C - -H "Authorization: Bearer $HF_TOKEN"`.
2. Write a plain-LF Modelfile there (CRLF breaks create — write from WSL,
   `tr -d '\r'`):
   ```
   FROM C:\Users\Admin\hf_models\<file>.gguf
   PARAMETER num_ctx 65536
   PARAMETER num_gpu 41
   ```
3. Create via PowerShell:
   `& 'C:\Users\Admin\AppData\Local\Programs\Ollama\ollama.exe' create <name> -f C:\...\Modelfile`
4. Verify `/api/tags`.

## 5. MAIN-NODE concurrency finding (kanban fleet implication)

Two simultaneous builder workers on MAIN-NODE: artifacts get written correctly but
workers die before protocol-complete under contention (~26K-token sessions
sharing one GPU → multi-minute turns → internal timeouts). SOLO worker =
reliable (~7 min/card). Rule: cap MAIN-NODE dispatch at ONE concurrent worker;
worker→verifier swarm stages are fine because they're sequential by design.
