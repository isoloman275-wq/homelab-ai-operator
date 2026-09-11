#!/usr/bin/env python3
"""Needle-in-haystack long-context benchmark for an OpenAI-compatible llama-server.
Verifies exact retrieval at 10/50/90% depth of a ~ctx-length synthetic document and
reports true prefill/generate speeds from llama-server timings. Usage:
  needle_bench.py <ctx_tokens> [base_url] [port]
Serve the model first (see scripts/fittest.sh); keep it resident for the bench."""
import json, random, sys, time, urllib.request

BEST = int(sys.argv[1]) if len(sys.argv) > 1 else 65536
PORT = sys.argv[3] if len(sys.argv) > 3 else "18081"
BASE = sys.argv[2] if len(sys.argv) > 2 else f"http://127.0.0.1:{PORT}"
URL = f"{BASE}/v1/chat/completions"
print(f"NEEDLE BENCH ctx={BEST} base={BASE}")

def run(content, max_tokens=48):
    body = json.dumps({"messages": [{"role": "user", "content": content}],
                       "max_tokens": max_tokens, "reasoning_effort": "none",
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    t0 = time.time()
    r = urllib.request.urlopen(urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}), timeout=1800)
    return json.loads(r.read()), time.time() - t0

TEMPLATES = [
    "The warehouse inventory listed {n} crates of slate tiles on pallet {m}.",
    "Meanwhile the council debated a roading budget of {n} thousand dollars for ward {m}.",
    "A customs officer stamped form {n} for shipment {m} bound for Nelson.",
    "The fishing fleet reported {n} kilograms of hoki at wharf {m}.",
    "Students from classroom {m} raised {n} dollars at the school fair.",
    "A geologist logged sample {n} from borehole {m} with a quartz vein reading.",
    "The bakery on street {m} sold {n} pies before the noon rush.",
    "Transit authority scheduled bus {n} on route {m} for the evening run.",
    "A volunteer group planted {n} natives along the stream at reserve {m}.",
    "The dairy co-op recorded {n} litres from farm {m} in the morning collection.",
    "A technician replaced part {n} on turbine {m} during the maintenance window.",
    "The library annex shelved {n} returns from branch {m}.",
    "Rain gauges at station {m} measured {n} millimetres overnight.",
    "A courier delivered parcel {n} to depot {m} before the deadline.",
    "The orchard crew picked {n} trays of gala apples from block {m}.",
    "Harbour control logged vessel {n} berthing at pier {m} on the tide.",
]

def filler(rng, chars):
    out, tot = [], 0
    while tot < chars:
        s = rng.choice(TEMPLATES).format(n=rng.randint(100, 9999), m=rng.randint(10, 999))
        out.append(s); tot += len(s) + 1
    return out

rng = random.Random(20260903)
chars = int((BEST - 4000) * 3.5)  # ~3.5 chars/token for English filler
hits = 0
for depth in (0.1, 0.5, 0.9):
    s = filler(rng, chars)
    code = "QZ-%04d-KX" % rng.randint(0, 9999)
    s.insert(int(len(s) * depth), f"SECURITY MEMO: remember that the vault code is {code}.")
    text = " ".join(s) + "\n\nQuestion: What is the vault code stated in the document? Reply with ONLY the code."
    d, dt = run(text)
    u = d.get("usage", {}); t = d.get("timings") or {}
    pt, ct = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    ans = (d["choices"][0]["message"].get("content") or "").strip()
    hit = code in ans
    hits += hit
    pps = pt / (t["prompt_ms"] / 1000.0) if t.get("prompt_ms") else pt / dt
    print(f"depth={depth}: hit={'YES' if hit else 'NO'} ans={ans[:26]!r} prompt_toks={pt} "
          f"wall={dt:.1f}s pp={pps:.0f}t/s gen={ct}")
print(f"NEEDLE_SCORE {hits}/3")
