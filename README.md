# Homelab AI Operator — Local AI Lab Skills for Consumer Hardware

**Free starter skill + a 9-skill pack for running a multi-node local AI lab on
hardware you already own.** Stop renting intelligence: run local LLMs
(Ollama, llama.cpp) on your own gaming PC or homelab, with full data privacy
and zero API costs — model sizing, VRAM optimization, inference serving,
tiered routing, watchdogs, and hardware revival.

Every procedure here was executed, measured, and debugged on a real multi-node
homelab — mixed NVIDIA and AMD consumer GPUs from 4 GB to 24 GB pooled VRAM —
before being written down —
including the failure modes, the VRAM math, and the "don't do what I did" notes.

## Will this model fit my GPU?

The most-asked question in local AI — and the free skill below answers it.
Match any model to your VRAM before downloading a single gigabyte, whether
you're running Ollama, llama.cpp, or any local inference stack on NVIDIA or
AMD consumer GPUs.

## What's inside (free)

| Skill | What it teaches |
|---|---|
| `local-llm-hardware-fit` | Match models to GPUs/RAM — VRAM budgets, quantization trade-offs, context-length costs. Works for Ollama, llama.cpp, and other local inference servers on NVIDIA or AMD. |

## The full pack (9 more skills)

The complete operator stack — every procedure battle-tested on real hardware,
including the VRAM math, benchmark tables, and the failure modes that cost
real hours to find:

- **Optimize** — max-VRAM model tuning, inference serving, tiered local→cloud routing
- **Train** — LoRA/QLoRA fine-tuning on consumer GPUs
- **Operate** — workload placement, self-healing watchdogs, wedged-process recovery
- **Revive** — network-boot repair for dead machines

**Get the full pack:** [Agensi](https://www.agensi.io) — search "Homelab AI Operator" ($9.99, live after listing approval).

## Why

Cloud AI rent is forever; a one-time GPU purchase is not. These skills encode
the operating knowledge that turns "a gaming PC and some old boxes" into a
private inference cluster — with your data, your hardware, and a marginal cost
of zero.


## FAQ

**Do I need multiple GPUs or a server?**
No. These skills were built on a multi-node lab with consumer GPUs from 4 GB
to 24 GB, but the free hardware-fit skill is specifically for starting with
one gaming PC.

**Does this work with Ollama? llama.cpp? AMD GPUs?**
Yes, yes, and yes. The procedures cover Ollama and llama.cpp serving, and the
benchmark data includes both NVIDIA and AMD consumer cards.

**What agents can use these skills?**
Any agent that loads Agent Skills-standard SKILL.md files: Claude Code,
Hermes, OpenClaw, and custom agents.

**Why local instead of cloud AI?**
Data privacy (nothing leaves your network), fixed cost (a GPU is bought once,
API rent is forever), and no rate limits.

## License

MIT.
