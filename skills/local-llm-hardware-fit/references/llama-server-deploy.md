# llama-server Build + Deploy on GPU-NODE

Full build-to-running playbook for llama.cpp llama-server with CUDA on GPU-NODE
(gpu-node-2, Ubuntu 24.04, 2× RTX 3060 = 24GB pool).

## Prerequisites

- CUDA 12.8 toolkit: `cuda-toolkit-12-8` + `cuda-nvvm-12-8` (nvvm provides `cicc` —
  cmake/CUDACompilerId fails without it)
- Driver 595.84 (or any 5xx that supports CUDA 12.8)
- 20GB+ free on root disk before build (CUDA compiler temp files can fill it)

### CUDA 12.8 install (if not present)
```bash
# Remove old partial CUDA
sudo rm -rf /usr/local/cuda-12.8 /usr/local/cuda-12 /usr/local/cuda

# Add NVIDIA repo
cd /tmp && wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb && sudo apt-get update

# Install full toolkit
sudo apt-get install -o Dpkg::Options::="--force-overwrite" -y cuda-toolkit-12-8 build-essential cmake
```

The `--force-overwrite` is needed because the `cuda-nvvm-12-8` package shares
`/usr/local/cuda-12.8/lib64` with other CUDA packages. Without it, dpkg errors.

## Build llama-server

```bash
# Clone (shallow, one commit)
cd /tmp && rm -rf llama.cpp && git clone https://github.com/ggml-org/llama.cpp.git --depth 1
cd llama.cpp

# Set CUDA 12.8 paths
export PATH=/usr/local/cuda-12.8/bin:/usr/local/cuda-12.8/nvvm/bin:$PATH
export CUDA_HOME=/usr/local/cuda-12.8

# Configure with CUDA
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc

# Build (use -j2 on 31GB RAM — full -j can OOM during compilation)
cmake --build build -j2 --target llama-server
```

**Expected output:** `[100%] Built target llama-server`

## Install binary + shared libraries

Building with CUDA produces shared libraries that `llama-server` links against dynamically.
These must be copied to the system library path.

```bash
# Install binary
sudo cp /tmp/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server
sudo chmod +x /usr/local/bin/llama-server

# Install ALL shared libs (critical — missing any causes status=127)
sudo cp /tmp/llama.cpp/build/bin/libllama*.so* /usr/local/lib/
sudo cp /tmp/llama.cpp/build/bin/libmtmd.so* /usr/local/lib/
sudo ldconfig

# Verify
ldd /usr/local/bin/llama-server | grep "not found"
# Should produce NO output — all libs resolved
```

### Shared library checklist
`llama-server` needs these at runtime:
- `libllama-server-impl.so`
- `libllama-common.so.0`
- `libmtmd.so.0`
- `libllama.so.0`

If any show as "not found", the binary was not linked or `ldconfig` didn't find the path.
Check `/usr/local/lib/` has the symlinks set up correctly:
```bash
# Example: libllama-common.so.0 -> libllama-common.so.0.3.0
ls -la /usr/local/lib/libllama*so* | grep -v "\.0\.3\.0$"
```

## Systemd service

```ini
[Unit]
Description=llama-server — LLM inference engine
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/llama-server \
  -m /data/storage/models/gguf/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  --host 0.0.0.0 --port 8080 \
  -ngl 99 \
  -c 131072 \
  --flash-attn 1 \
  --cache-type-k q4_0 \
  --cache-type-v q4_0 \
  --jinja \
  --temp 0.7 --top-p 0.95 --top-k 40 \
  --cont-batching

Restart=on-failure
RestartSec=10
User=llm-user
Group=llm-user
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### Flag reference
| Flag | Purpose | Notes |
|---|---|---|
| `-m <path>` | Model GGUF | Use absolute path |
| `-ngl 99` | GPU layers | 99 = all layers on GPU |
| `-c 131072` | Context size | 128K for this model. At 64K use `-c 65536` |
| `--flash-attn 1` | Flash attention | Was `--fa 1` in older versions |
| `--cache-type-k q4_0` | KV cache quant | Saves ~2GB vs q8_0 at 128K |
| `--cache-type-v q4_0` | KV cache quant | Same as above |
| `--jinja` | Jinja2 template | Needed for chat template in Hermes |
| `--cont-batching` | Continuous batching | Allows multiple concurrent requests |

### Flags to AVOID
- `--fa 1` — renamed to `--flash-attn 1`; will error
- `--no-think` — does not exist in llama.cpp
- `--spec-type draft-mtp` — MTP head adds ~1.5GB VRAM; only use if headroom permits
- `--spec-draft-n-max 2` — same as above, pairs with MTP

## Startup/shutdown

```bash
# Stop the restart storm (always stop before editing unit file)
sudo systemctl stop llama-server.service

# After editing unit file:
sudo systemctl daemon-reload
sudo systemctl start llama-server.service

# Check status
sudo systemctl status llama-server.service
systemctl is-active llama-server.service

# View logs (do this first when debugging)
sudo journalctl -u llama-server.service --no-pager -n 20
```

## Verification

1. Service is `active` (not `activating`)
2. `/v1/models` endpoint responds:
   ```bash
   curl -s http://127.0.0.1:8080/v1/models
   # → {"models":[{"name":"/data/storage/models/gguf/..."}]}
   ```
3. GPU VRAM shows weights loaded:
   ```bash
   nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader
   # GPU0: ~9-10GB used, GPU1: ~10-11GB used = 21-22GB total
   # Free: 2-3GB for inference buffers
   ```
4. Inference works:
   ```bash
   curl -s --max-time 30 http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"/data/storage/models/gguf/Qwen3.8-27B-UD-Q4_K_XL.gguf","messages":[{"role":"user","content":"Reply with ONLY: hello"}],"temperature":0.1,"max_tokens":50}'
   # → {"choices":[{"finish_reason":"stop","index":0,"message":{"role":"assistant","content":"hello"}}]}
   ```

## VRAM sizing cheat sheet for 27B hybrid-attention (Qwen3.8 arch)

| Config | Weights | KV cache | Total | Fits 24GB? |
|--------|---------|----------|-------|------------|
| Q4_K_M @ 64K q4_0 | 17.0 GB | ~1.1 GB | 18.1 GB | ✅ |
| UD-Q4_K_XL @ 64K q4_0 | 17.9 GB | ~1.1 GB | 19.0 GB | ✅ |
| UD-Q4_K_XL @ 128K q4_0 | 17.9 GB | ~2.2 GB | 21.4 GB | ✅ (2.4GB free) |
| UD-Q4_K_XL @ 128K q8_0 | 17.9 GB | ~4.3 GB | 23.5 GB | ✅ (tight, 0.5GB) |
| UD-Q5_K_XL @ 128K q4_0 | 20.2 GB | ~2.2 GB | 23.7 GB | ❌ (no headroom) |

**Key insight:** KV cache is small because only 16/64 layers are full-attention. The 48 DeltaNet
layers use linear attention with fixed-size state. This is why Qwen3.8-27B fits at 128K when
other 27B models would OOM.

## Switching between llama-server and Ollama

Both can run simultaneously on different ports (8080 vs 11434). The VRAM cost is zero —
whichever loads the model owns the 24GB pool. To switch:

```bash
# Stop llama-server (frees VRAM)
sudo systemctl stop llama-server.service

# Load model via Ollama
ollama run qwen3.8:27b-132k

# OR: stop Ollama and start llama-server
ollama stop qwen3.8:27b-132k
sudo systemctl start llama-server.service
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `status=127` | Shared lib not found | Copy all `.so*` from build, `ldconfig` |
| `error: invalid argument: --fa` | Flag renamed | Use `--flash-attn 1` |
| `error: invalid argument: --no-think` | Flag doesn't exist | Remove it |
| `failed to allocate CUDA1 buffer` | VRAM exceeded | Reduce `-c` or switch to q4_0 KV cache |
| `failed to create MTP context` | MTP head OOM | Remove `--spec-type draft-mtp` |
| `Restart counter 100+` | Unit file has wrong flags | Stop, fix, `daemon-reload`, start |
| `503 Loading model` | Still loading | Wait 30-60s, model is 17GB on NTFS |
| Process exits silently | Missing GGUF file | Check `-m` path exists |

## Disk cleanup after failed pulls

Ollama pulls that fail mid-stream leave partial blobs that fill root disk:
```bash
# Check
ls -lh /var/lib/ollama/blobs/*-partial*

# Clean
sudo rm -f /var/lib/ollama/blobs/sha256-*-partial*
```
Always `df -h /` before and after any large model operation.
