#!/usr/bin/env bash
# Single-GPU fit-test: load one GGUF at one ctx on ONE gpu, measure VRAM, smoke-prompt, kill.
# Caller is responsible for stopping any resident LLM service first (safety gate) and
# restoring it after. Usage: fittest.sh <gguf> <ctx> [gpu_idx] [port] [mmproj_path]
GGUF="$1"; CTX="${2:-65536}"; GPU="${3:-1}"; PORT="${4:-18081}"; MMPROJ="$5"
LOG=/tmp/fittest_$$.log
MMFLAG=""; [ -n "$MMPROJ" ] && MMFLAG="--mmproj $MMPROJ"
echo "=== FITTEST $GGUF ctx=$CTX gpu=$GPU mmproj=${MMPROJ:-none} ==="
CUDA_VISIBLE_DEVICES=$GPU llama-server -m "$GGUF" $MMFLAG --host 127.0.0.1 --port "$PORT" \
  -ngl 99 -c "$CTX" -fa on --cache-type-k q8_0 --cache-type-v q8_0 > "$LOG" 2>&1 &
TPID=$!
OK=0
for i in $(seq 1 75); do
  sleep 2
  kill -0 $TPID 2>/dev/null || { echo "RESULT: PROCESS_DIED"; tail -5 "$LOG"; exit 1; }
  grep -qi listening "$LOG" && { OK=1; break; }
done
[ $OK -eq 1 ] || { echo "RESULT: NO_LISTEN"; tail -8 "$LOG"; kill -9 $TPID 2>/dev/null; exit 1; }
sleep 2
echo "VRAM_WHILE_LOADED gpu$GPU: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader -i $GPU)"
# Smoke: arithmetic + thinking explicitly off (thinking models otherwise burn the budget)
RESP=$(curl -s --max-time 180 "http://127.0.0.1:$PORT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is 17*23? Answer with just the number."}],"max_tokens":200,"reasoning_effort":"none","chat_template_kwargs":{"enable_thinking":false}}')
echo "SMOKE_REPLY: $(echo "$RESP" | head -c 300)"
# Optional vision check when mmproj is set: 1x1 red PNG through the image path
if [ -n "$MMPROJ" ]; then
  IMG="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
  printf '{"messages":[{"role":"user","content":"What color is this image? One word.","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,%s"}}]}],"max_tokens":50}' "$IMG" \
    > /tmp/fittest_vreq.json
  echo "VISION_REPLY: $(curl -s --max-time 180 "http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' -d @/tmp/fittest_vreq.json | head -c 300)"
fi
echo "VRAM_AFTER gpu$GPU: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader -i $GPU)"
kill $TPID 2>/dev/null; sleep 3; kill -9 $TPID 2>/dev/null
echo "=== FITTEST END ==="
