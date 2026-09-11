# Ollama `--load-mode` 500 on qwen3.8 — root cause + fix

## Symptom
Every `POST /api/generate` to `qwen3.8:27b-132k` on GPU-NODE returns:
```
HTTP 500
{"error":"llama-server process has terminated: exit status 1: error: invalid argument: --load-mode"}
```
Journal shows the scheduler launches llama-server with
`--load-mode none --spec-type draft-mtp --spec-draft-n-max 4` and the server dies on
`--load-mode`.

## Root cause (verified, not guessed)
- Official `qwen3.8:27b` Modelfile ships `PARAMETER draft_num_predict 4` → **MTP speculative
  decoding** (per Ollama maintainer in issue #17790: "the default value for `draft_num_predict`
  is 4").
- Ollama 0.32.14's scheduler emits `--load-mode none --spec-type draft-mtp` to the bundled
  `llama-server` for any MTP-enabled model.
- The `llama-server` binary bundled with 0.32.14 (dated Jul 10) does NOT accept `--load-mode`
  (`strings /usr/local/lib/ollama/llama-server | grep -c load-mode` → 0), while the `ollama`
  core binary DOES contain it (count 1). Version skew between the two components.
- Net: scheduler emits a flag the server can't parse → server exits 1 → 500.

## Confirm which component is at fault (diagnostic)
```bash
ssh llm-user@gpu-node-2 "strings /usr/local/bin/ollama | grep -c load-mode"        # expect 1 (emits)
ssh llm-user@gpu-node-2 "strings /usr/local/lib/ollama/llama-server | grep -c load-mode"  # expect 0 (rejects)
```

## Fix — upgrade Ollama binary only (NO model copies, NO store move)
0.32.15 (published 2026-08-19, one day after 0.32.14) bundles a llama-server that accepts the
flag. Binary-only swap:
```bash
ssh llm-user@gpu-node-2 "
cd /tmp
curl -sL -o ollama3215.tar.zst https://github.com/ollama/ollama/releases/download/v0.32.15/ollama-linux-amd64.tar.zst
sudo systemctl stop ollama
tar --zstd -xf ollama3215.tar.zst
sudo cp /usr/local/bin/ollama /usr/local/bin/ollama.bak.3214
sudo cp -r /usr/local/lib/ollama /usr/local/lib/ollama.bak.3214
sudo cp bin/ollama /usr/local/bin/ollama
sudo rm -rf /usr/local/lib/ollama
sudo cp -r lib/ollama /usr/local/lib/ollama
sudo chown -R root:root /usr/local/lib/ollama /usr/local/bin/ollama
sudo systemctl restart ollama
"
# Verify
curl -s -X POST http://gpu-node-2:11434/api/generate -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8:27b-132k","prompt":"say OK","stream":false,"think":false,"options":{"num_ctx":8192}}'
# → HTTP 200, response "OK"
```

## What NOT to do (each wasted a real session)
- **Do NOT `ollama create` a no-draft copy** to strip `draft_num_predict`. It copies ~17GB of
  blobs; on a near-full `sda2` it fails mid-copy with `no space left on device` and leaves a
  half-model. The upgrade fixes the bug without touching the model.
- **Do NOT move the Ollama store to `/data/storage`** to "make room." A previous store-move
  broke the whole lab. GPU-NODE has 26G free on `sda2` as of 2026-08-20; the binary upgrade needs
  ~1.4GB temp in `/tmp` only.
- **Do NOT assume `ornith:35b` or any other model is a fallback** — verify with
  `curl http://gpu-node-2:11434/api/tags` first. Stale memory claimed `ornith:35b` was live;
  it was NOT (only `qwen3.8:27b-132k` exists).

## Search-first discipline (user correction)
Before experimenting, run the issue search that would have found #17790 in 2 minutes:
```bash
curl -s "https://api.github.com/search/issues?q=repo:ollama/ollama+%22load-mode%22"
curl -s "https://api.github.com/repos/ollama/ollama/releases?per_page=8"  # find newer version
```
The user's words: "go fetch more information about the model instead of guessing" and
"I just asked google and can see a bunch of solutions maybe you could do a search."
