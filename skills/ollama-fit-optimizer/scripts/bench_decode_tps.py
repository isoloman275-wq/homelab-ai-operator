#!/usr/bin/env python3
"""Benchmark Ollama decode TPS for a model on a host.

Usage:
  python3 bench_decode_tps.py --host http://gpu-node-2:11434 --model gemma3:12b
  python3 bench_decode_tps.py --host http://gpu-node-2:11434 --model qwen3:14b --no-think

Prints decode TPS = eval_count / (eval_duration / 1e9) plus a short sample so you can
judge both speed and quality. A warmup call loads the model first (cold loads can
return empty / skew the first measurement). For Qwen3 pass --no-think to disable the
reasoning trace (avatar/live-chat use cases want snappy, thinking-off replies).

Reusable for the "Latency-sensitive model selection" workflow in SKILL.md.
"""
import argparse
import json
import time
import urllib.request


def gen(host, model, prompt, np=150, think=True):
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": think,
        "options": {"num_predict": np},
    }).encode()
    t = time.time()
    req = urllib.request.Request(
        f"{host}/api/generate", data=data,
        headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    dt = time.time() - t
    return r.get("eval_count", 0), r.get("eval_duration", 0), dt, r.get("response", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", required=True)
    ap.add_argument(
        "--prompt",
        default=("Give a newcomer one quick, practical tip for getting started with "
                 "local AI tools. Keep it to two sentences."))
    ap.add_argument("--np", type=int, default=150)
    ap.add_argument("--no-think", action="store_true",
                    help="send think:false (Qwen3 / reasoning models)")
    a = ap.parse_args()

    gen(a.host, a.model, "hi", 20, not a.no_think)        # warmup / load
    ec, ed, dt, resp = gen(a.host, a.model, a.prompt, a.np, not a.no_think)
    tps = round(ec / (ed / 1e9), 1) if ed else None
    print(f"{a.model}  decode_tps={tps}  eval_tokens={ec}  wall={dt:.2f}s")
    print("SAMPLE:", resp.strip()[:280])


if __name__ == "__main__":
    main()
