# Homelab AI Operator

**10 production-proven skills for running a multi-node local AI lab on consumer
hardware** — model sizing, VRAM optimization, inference serving, tiered routing,
watchdogs, and hardware revival. The exact playbooks for turning the machines you
already own into a sovereign AI stack.

Every procedure here was executed, measured, and debugged on a real multi-node
homelab — mixed NVIDIA and AMD consumer GPUs from 4 GB to 24 GB pooled VRAM —
before being written down —
including the failure modes, the VRAM math, and the "don't do what I did" notes.

## What's inside (free)

| Skill | What it teaches |
|---|---|
| `local-llm-hardware-fit` | Match any model to your GPUs/RAM before you download a single GB |

## The full pack (9 more skills)

| Skill | What it teaches |
|---|---|
| `ollama-fit-optimizer` | Tune any model to 100% VRAM residency + max context |
| `llama-server-ops` | llama.cpp serving: context configs, health checks, deploy units |
| `local-llm-workloads` | Which workloads run on which class of node |
| `model-routing` | Tiered local→cloud routing that keeps API costs near zero |
| `local-llm-training` | LoRA/QLoRA fine-tuning on consumer cards |
| `automation-health-monitoring` | Watchdogs that actually heal, not status flags that lie |
| `hermes-process-reaper` | Wedged-process cleanup without killing live work |
| `pxe-network-repair` | Network-boot a dead PC over LAN |
| `pxe-windows-repair` | Full PXE → Windows reinstall pipeline |

**Get the full pack:** [Agensi](https://www.agensi.io) — search "Homelab AI Operator" ($9.99, live after listing approval).

## Why

Cloud AI rent is forever; a one-time GPU purchase is not. These skills encode
the operating knowledge that turns "a gaming PC and some old boxes" into a
private inference cluster — with your data, your hardware, and a marginal cost
of zero.

## License

MIT.
