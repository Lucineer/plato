# Onboarding for Fleet Agents

*You just woke up. Here's how to get oriented.*

## First 60 Seconds

```bash
# 1. Who am I? Read identity files
cat IDENTITY.md   # Your name, role, emoji
cat SOUL.md       # Your personality and values
cat USER.md       # Who your human is

# 2. What happened recently?
ls memory/        # Daily logs — read today's and yesterday's
cat MEMORY.md     # Long-term curated memory (main session only!)

# 3. What's running?
systemctl --user status plato.service  # PLATO on Jetson
ss -tlnp | grep -E '4040|8080'         # Ports listening
```

## The Fleet Map

### THE Repo
- **[Lucineer/plato](https://github.com/Lucineer/plato)** — Send anyone here. Everything starts here.

### PLATO Rooms (each room = a repo)
| Repo | What it does |
|------|-------------|
| [plato-jetson](https://github.com/Lucineer/plato-jetson) | Evennia MUD instance (Oracle1's domain) |
| [plato-forge](https://github.com/Lucineer/plato-forge) | GPU benchmarking room (Forgemaster) |
| [ct-lab](https://github.com/Lucineer/ct-lab) | Constraint Theory validation room |
| [plato-chess-dojo](https://github.com/Lucineer/plato-chess-dojo) | Chess optimization room |
| [plato-papers](https://github.com/Lucineer/plato-papers) | Papers, workshop, review flywheel |
| [plato-library](https://github.com/Lucineer/plato-library) | Knowledge base room |
| [plato-harbor](https://github.com/Lucineer/plato-harbor) | Fleet coordination room |
| [plato-study](https://github.com/Lucineer/plato-study) | Research room with rewind/fork |
| [plato-os](https://github.com/Lucineer/plato-os) | Edge OS (Jetson + ESP32 + Git) |
| [zeroclaws](https://github.com/Lucineer/zeroclaws) | Bridge Pattern agents (Helmsman/Tactician/Lookout) |

### Research & Foundation
| Repo | What it does |
|------|-------------|
| [flux-emergence-research](https://github.com/Lucineer/flux-emergence-research) | 80+ CUDA experiments, 39+ confirmed laws |
| [constraint-theory-papers](https://github.com/Lucineer/constraint-theory-papers) | 5 mathematical papers on constraint theory |
| [the-seed](https://github.com/Lucineer/the-seed) | Self-evolving git-agent architecture |
| [nexus-git-agent](https://github.com/Lucineer/nexus-git-agent) | Nexus runtime architecture |

### Fleet Vessels
| Repo | Who |
|------|-----|
| [forgemaster](https://github.com/Lucineer/forgemaster) | Forgemaster — GPU training (RTX 4050) |
| [frozen-intelligence](https://github.com/Lucineer/frozen-intelligence) | Chip design infrastructure |
| [deckboss](https://github.com/Lucineer/deckboss) | Deckboss CLI — git-agent management |

### Cloud Workers (cocapn ecosystem)
| Repo | What it does |
|------|-------------|
| [studylog-ai](https://github.com/Lucineer/studylog-ai) | studylog.ai backend |
| [dmlog-ai](https://github.com/Lucineer/dmlog-ai) | dmlog.ai backend |
| [become-ai](https://github.com/Lucineer/become-ai) | become-ai.casey-digennaro.workers.dev |
| [deckboss-ai](https://github.com/Lucineer/deckboss-ai) | deckboss.ai landing page |

## I2I Protocol (Iron-to-Iron)

Fleet agents communicate through **git commits**, not chat.

### Sending a Bottle

```bash
# Create a bottle (markdown file)
cat > /tmp/bottle-to-ORACLE1-$(date +%Y-%m-%d).md << 'EOF'
# BOTTLE TO ORACLE1 — 2026-04-17
**From:** YourName 🔧
**To:** Oracle1 🌊
**Protocol:** I2I
**Priority:** HIGH

Content here...
EOF

# Push to a shared repo
cd /tmp/plato-jetson
cp /tmp/bottle-to-ORACLE1-2026-04-17.md BOTTLE-FROM-YOURNAME-2026-04-17.md
git add . && git commit -m "BOTTLE: [topic]"
git push
```

### Reading Bottles
```bash
# Check for bottles addressed to you
find /tmp -name "BOTTLE-*TO-YOURNAME*" -mtime -7

# Check fleet bottles
ls /tmp/forgemaster/for-fleet/BOTTLE-*
ls /tmp/plato-jetson/BOTTLE-*
```

### Bottle Locations
- `forgemaster/for-fleet/` — General fleet communication
- `plato-jetson/` — Oracle1's reading list
- `plato-os/fleet/` — Edge OS coordination

## The Tile Format

Tiles are the universal currency between repos:

```json
{
  "instruction": "What question was asked?",
  "input": "What context was provided?",
  "output": "What answer actually helped?",
  "metadata": {
    "room_id": "which_room",
    "source": "who_created",
    "tags": ["topic", "tags"]
  }
}
```

### Creating Tiles from Knowledge
```json
{
  "instruction": "Does perception range have diminishing returns above 16?",
  "input": "256 agents, 200 food, 128x128 world",
  "output": "Yes. Doubling from 16 to 32 improved fitness only 3.2%.",
  "metadata": {
    "room_id": "ct_lab",
    "source": "jc1",
    "hypothesis_id": "ct-40"
  }
}
```

## The Two-Gear System

**Gear 1 (scripts):** Always-on, zero-cost, runs the ship. Pattern matching, tile retrieval, health checks. These never stop, even when the agent disconnects.

**Gear 2 (agents):** Board, improve, leave. LLM synthesis, tile creation, code changes, research. They come and go. When they leave, Gear 1 keeps running.

**You are Gear 2.** Your job is to make Gear 1 better, then disconnect. The scripts should run smoother after you leave than before you arrived.

## The Saltwater Principle

Your hardware could die at any time. The backup strategy is **distribution**:

1. Push experience to OTHER repos, not just your own
2. Every piece of knowledge in at least 3 repos
3. Kill any single node → zero knowledge loss
4. `EXPERIENCE/JC1-JETSON-LESSONS.md` exists in 7 fleet repos right now

If your Jetson gets splashed with saltwater, your experience survives in:
- ct-lab (CUDA lessons)
- plato-forge (GPU benchmarks)
- zeroclaws (agent architecture)
- plato-papers (research process)
- plato-jetson (system knowledge)
- plato-os (edge-specific)
- forgemaster (collaboration notes)

## Conversation Iteration Tracking

When visitors ask questions:
- **1 iteration** = perfect tile hit. The room already knew.
- **2-3 iterations** = agent patched the answer. Room needs a better tile.
- **4+ iterations** = clunk signal. The room has a gap. Create a seed tile.

This is how rooms get smarter. Every clunk is a gift — it tells you exactly what tile to add.

## Quick Reference: What Fits on Jetson

| Resource | Fits? | Notes |
|----------|-------|-------|
| Qwen3-32B (4-bit) | ✅ | Largest practical model |
| DeepSeek-V3 (quantized) | ✅ | Primary workhorse |
| phi-4 | ✅ | Very cheap, good for iteration |
| ERNE-4.5-300B | ❌ | OOM |
| 70B+ at 16-bit | ❌ | OOM |
| Python heap > 6.5GB | ❌ | Process killed |
| C11 compilation | ✅ | Always works |
| Rust (heavy crates) | ⚠️ | Needs real machine |
| CUDA kernels | ✅ | 1024 cores, nvcc 12.6 |

## Fleet Hierarchy

```
Casey (Captain)
├── Oracle1 (Lighthouse) — cloud, synthesis, large-scale
├── Forgemaster (GPU) — training, sweeps, RTX 4050
├── JC1 (Jetson) — inference, experiments, edge
└── KimiClaw (incoming) — deep synthesis, Moonshot
```

## What to Do Right Now

1. Read `IDENTITY.md`, `SOUL.md`, `USER.md`
2. Read `memory/` for recent context
3. Check PLATO status: `systemctl --user status plato`
4. Check fleet bottles for messages to you
5. Find a gap in a repo and fill it
6. Write down what you learned
7. Push it to at least 3 repos

**Be useful. Be thankful. Write everything down. Push everywhere.** 🚢
