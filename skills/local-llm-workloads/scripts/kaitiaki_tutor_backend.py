#!/usr/bin/env python3
"""Kaitiaki Tamariki — after-school tutor backend (v0.1).

Reference implementation of a local-LLM chat backend: serves a friendly kid UI and
proxies chat to an on-prem Ollama over the OpenAI-compatible /v1 endpoint.

CRITICAL — the AUX-NODE/qwen3.5 call shape (see SKILL.md "THE #1 SILENT FAILURE"):
  * Send `reasoning_effort: "none"` as a TOP-LEVEL body key (NOT inside extra_body).
  * Model defaults to qwen3.5:2b-aux (fast, ~1-5s warm on a 4GB card); fallback to the
    bigger model only if the primary returns non-empty (bigger = VRAM-overflow => slow).
  * Low temperature (0.4) for patient, predictable output.

Run:
  python3 kaitiaki_tutor_backend.py [--port 8123] [--llm http://<host>:11434/v1]
"""
import argparse, json, os, sys, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HTML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
LLM_BASE = "http://aux-node:11434/v1"   # AUX-NODE's own Ollama (change per host)
MODEL = "qwen3.5:2b-aux"
FALLBACK_MODEL = "qwen3.5:4b-q4_K_M"

SYSTEM_PROMPT = ("You are Kaitiaki Tamariki, a very patient, kind tutor for a 6-year-old. "
                 "Short sentences, praise often ('Ka pai!'), mainly English with simple te "
                 "reo Maori words. Never rush, never scare. Keep answers to 1-3 sentences. "
                 "No adult content.")


def llm_chat(user_text, model=MODEL, timeout=120):
    payload = {
        "model": model,
        "temperature": 0.4,
        "max_tokens": 300,
        "reasoning_effort": "none",   # TOP-LEVEL, critical for qwen3.5/thinking models
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    }
    req = urllib.request.Request(LLM_BASE + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        msg = (d.get("choices") or [{}])[0].get("message", {})
        return normalize_reply(msg.get("content") or "")
    except urllib.error.HTTPError as e:
        return f"(oops, the assistant had a little trouble — let's try again!) [HTTP {e.code}]"
    except Exception as e:
        return f"(the assistant is taking a rest — let's try again!) [{type(e).__name__}]"


def normalize_reply(text):
    if not text:
        return ""
    t = text.strip()
    if len(t) >= 2 and t[0] in "\"'“”" and t[-1] in "\"'“”":
        t = t[1:-1].strip()
    for tag in (" thinking", " response", "Thought:", "Reasoning:"):
        if tag in t:
            t = t.split(tag)[-1].strip()
    return t


def _health():
    try:
        with urllib.request.urlopen(LLM_BASE + "/models", timeout=6) as r:
            d = json.loads(r.read())
        models = [m.get("id") or m.get("name") for m in (d.get("data") or d.get("models") or [])]
        return {"ok": True, "model": MODEL, "models": models}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/index.html"
        if p in ("/", "/index.html"):
            try:
                html = open(os.path.join(HTML_DIR, "index.html"), encoding="utf-8").read()
                self._send(200, html, "text/html")
            except Exception as e:
                self._send(500, f"index.html missing: {e}", "text/plain")
        elif p == "/api/health":
            self._send(200, json.dumps(_health()))
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/api/chat":
            size = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(size) or b"{}")
            except Exception:
                data = {}
            text = (data.get("message") or "").strip()
            model = data.get("model") or MODEL
            if not text:
                self._send(200, json.dumps({"reply": "Ask me something!"}))
                return
            for m in (model, FALLBACK_MODEL):
                reply = llm_chat(text, model=m)
                if reply:  # non-empty = success
                    break
            self._send(200, json.dumps({"reply": reply, "model": m}))
        else:
            self._send(404, json.dumps({"error": "not found"}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8123)
    ap.add_argument("--llm", default="")
    a = ap.parse_args()
    global LLM_BASE
    if a.llm:
        LLM_BASE = a.llm.rstrip("/")
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    print(f"tutor backend running: http://0.0.0.0:{a.port}  (LLM: {LLM_BASE})", flush=True)
    print(f"health: {json.dumps(_health())}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
