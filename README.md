# Homelab AI Operator

**10 production-proven skills for running a multi-node local AI lab on consumer
hardware** — model sizing, VRAM optimization, inference serving, tiered routing,
watchdogs, and hardware revival. The exact playbooks for turning the machines you
already own into a sovereign AI stack.

Every procedure here was executed, measured, and debugged on a real 3-node
homelab (2× RTX 3060, RX 5700 XT 8GB, RX 580 4GB) before being written down —
including the failure modes, the VRAM math, and the "don't do what I did" notes.

## What's inside

### Fit & optimize
| Skill | What it teaches |
|---|---|
| `local-llm-hardware-fit` | Match models to GPUs/RAM before you download a single GB |
| `ollama-fit-optimizer` | Tune any Ollama model to 100% VRAM residency + max context |
| `llama-server-ops` | llama.cpp serving: context configs, health checks, deploy units |

### Operate
| Skill | What it teaches |
|---|---|
| `local-llm-workloads` | What workloads run on which class of node (brain / worker / aux) |
| `model-routing` | Tiered local→cloud routing that keeps API costs near zero |
| `local-llm-training` | LoRA/QLoRA fine-tuning on consumer cards |
| `automation-health-monitoring` | Watchdogs that actually heal — not status flags that lie |
| `hermes-process-reaper` | Stale/wedged process cleanup without killing live work |

### Revive
| Skill | What it teaches |
|---|---|
| `pxe-network-repair` | Network-boot a dead PC over LAN for repair |
| `pxe-windows-repair` | Full PXE → Windows reinstall pipeline |

## Why

Cloud AI rent is forever; a one-time GPU purchase is not. These skills encode
the operating knowledge that turns "a gaming PC and some old boxes" into a
private inference cluster — with your data, your hardware, and a marginal cost
of zero.

## Install

Works with any agent that supports the [Agent Skills standard](https://agentskills.io)
(Claude Code, Hermes, OpenClaw, and others):

```
# Claude Code
/plugin marketplace add <seller>/homelab-ai-operator

# Hermes
hermes skills tap add <seller>/homelab-ai-operator
hermes skills install <skill-name>
```

## Design principles

- **Replicable bodies** — generic node names (`gpu-node-2`, `aux-node`), no
  lab-specific IPs or paths. Map them onto your own network in minutes.
- **Numbers, not vibes** — VRAM tables, tok/s measurements, context ceilings,
  all measured on the actual hardware class you're likely running.
- **Failure modes are content** — the OOM configs, the wedged-load patterns,
  the "trust behavior over SMART" lessons are in the files.

## License

MIT.
