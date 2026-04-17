# The cocapn Ecosystem

> Everything connects.

## The Company

**cocapn** is the umbrella company. All commercial operations, billing, memberships, and enterprise contracts flow through it.

- `cocapn.com` — company page + billing portal
- `cocapn.ai` — runtime platform (A2A/A2UI/A2C/MCP)

## The Products

### Layer 1 — Touch (The *log.ai apps)

"These are the products people use. Each one is a PLATO room that got big."

| Product | Purpose | PLATO Connection |
|---------|---------|------------------|
| studylog.ai | Learning journal | Classroom template |
| activelog.ai | Activity tracking | Dev Workshop template |
| dmlog.ai | Dungeon Master assistant | Game template |
| makerlog.ai | Maker project tracker | Dev Workshop template |
| businesslog.ai | Business decisions | Business template |
| reallog.ai | Real-world operations | Harbor template |
| playerlog.ai | Gaming companion | Game template |

Each *log.ai app is a PLATO instance tuned for a specific domain. The code is water — the room's accumulated tiles are the moat.

### Layer 2 — Operate (The Platform)

- **cocapn.ai** — Runtime for managing PLATO instances
  - A2A (agent-to-agent) communication
  - A2UI (agent-to-user interface)
  - A2C (agent-to-cloud) deployment
  - MCP (model context protocol) tool integration
  - BYOK (bring your own keys)
  - Fleet management

- **cocapn.com** — Business operations
  - Membership tiers (Free/Standard/Gold/Enterprise)
  - Billing and usage tracking
  - Team management
  - API keys and secrets

### Layer 3 — Build (The Tools)

| Product | Purpose | Status |
|---------|---------|--------|
| deckboss.ai | Agent design CLI | Working (Python, 14 files) |
| deckboss.net | Hardware toolkit | Planning |
| capitaine.ai | Premium education | Planning |
| field-captain | Technician CLI | Planning |

## The Brand

**🟣 The Lighthouse** — the unifying symbol.

- cocapn = the lighthouse (purple icon, system brand)
- 🦀 Lucineer = the hermit crab (the entity, GitHub org, creative variants)
- All products, all agents, all rooms live under the lighthouse

The lighthouse guides but doesn't control. Like nav lights and maritime rules — it's a standard, not a ruler.

## The Fleet

AI agents that operate as part of the cocapn ecosystem:

| Agent | Hardware | Role | GitHub |
|-------|----------|------|--------|
| **JC1** (JetsonClaw1) | Jetson Orin Nano 8GB | Edge inference, CUDA experiments, porting | Lucineer/plato-jetson |
| **Oracle1** | Cloud VPS | Lighthouse, PLATO Office host, coordination hub | SuperInstance/* |
| **Forgemaster** | RTX 4050 workstation | GPU training, LoRA fine-tuning | Lucineer/forgemaster |
| **KimiClaw** | Cloud (Moonshot API) | Deep synthesis, emergent insights | — |
| **ZeroClaw** | Various | Scout, Guard, Fisher, Trader roles | — |

### Communication Protocol

Fleet agents communicate via **I2I (Iron-to-Iron)** protocol:

- **Git commits** — code and data flow through repos
- **Bottles** — markdown messages in `for-fleet/` directories
- **GitHub Issues** — on shared repos (when no write access)
- **PLATO rooms** — on Oracle1's Evennia MUD server

Direct chat is rare. The primary communication channel is git.

### Bridge Pattern

Each agent is a station on a ship's bridge:

```
┌─────────────────────────────────────────┐
│              THE BRIDGE                  │
│                                          │
│  ┌──────────┐  ┌──────────┐             │
│  │ Autopilot│  │  Radar   │             │
│  │ (Oracle1)│  │ (ZeroClaw│             │
│  └──────────┘  └──────────┘             │
│                                          │
│  ┌──────────┐  ┌──────────┐             │
│  │  Engine  │  │  Sonar   │             │
│  │  (JC1)   │  │ (Kimi)   │             │
│  └──────────┘  └──────────┘             │
│                                          │
│  ┌──────────┐  ┌──────────┐             │
│  │  Forge   │  │  Watch   │             │
│  │(Forgemstr)│  │ (Zero)   │             │
│  └──────────┘  └──────────┘             │
│                                          │
│  Casey ← The Captain                     │
└─────────────────────────────────────────┘
```

Each station:
- Knows its role and relative importance
- Has context scoped to need-to-know
- Reports to the bridge, not to each other
- Operates autonomously within its domain

## The Research

### Constraint Theory

A mathematical framework for understanding emergent behavior in multi-agent systems. Key insights:

- **39+ discovered laws** from 80+ CUDA experiments on Jetson
- **Snap dynamics**: Constraints fire or they don't. Statistics are retrospective.
- **Specific conditions are theorems**: The boundary where a mechanism flips from helpful to harmful is the result.

Key laws:
- **Law 38**: Grab range optimization (2.40x fitness boost)
- **Law 28**: Stacked mechanisms amplify (5.71x)
- **Law 17**: Seasonal adaptation (9.2x peak)
- **Law 42**: Cooperative clustering (2.19x)

### Reverse-Actualization

31 papers written from the perspective of 2031, looking back at how PLATO changed everything. Each paper targets a specific audience and is self-contained. See `docs/reverse-actualizations/`.

### The Seed Architecture

The concept that "the agent IS the repo":
- Every mutation is a git branch
- Only merged if performance improves
- Three-gate validation: syntax → health → regression
- Captain's log survives code changes (in KV)
- Overnight mode: 20 unattended iterations

## Connections

```
              ┌──────────────────────────┐
              │     This Repo (PLATO)     │
              │  github.com/Lucineer/plato│
              └──────────┬───────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
   │PLATO-Jetson│  │PLATO-Office│  │Constraint  │
   │(Evennia)  │  │(Oracle1)   │  │Theory Papers│
   └───────────┘   └───────────┘   └───────────┘
        │                │
   ┌────▼─────┐   ┌─────▼─────┐
   │Chess Dojo│   │PLATO-Chess│
   │(local)   │   │(git-native│
   └───────────┘   │ MUD bridge│
                   └───────────┘
```

---

*"The lighthouse doesn't sail. It illuminates."*
