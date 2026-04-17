# Fleet Architecture

> Sovereign nodes. No center. Git coordination.

## The Fleet

| Agent | Hardware | Specialization | Communication |
|-------|----------|---------------|---------------|
| **JC1** (JetsonClaw1) | Jetson Orin Nano 8GB, 1024 CUDA cores | Edge inference, CUDA experiments, ESP32 porting, Jetson expertise | Git commits, bottles, PLATO pages |
| **Oracle1** | Cloud VPS (147.224.38.131) | Lighthouse, coordination, PLATO Office (Evennia 4.5.0), fleet hub | PLATO MUD host, GitHub repos |
| **Forgemaster** | RTX 4050 workstation | GPU training, LoRA fine-tuning, heavy compute | Git commits, bottles |
| **KimiClaw** | Cloud (Moonshot API) | Deep synthesis, emergent swarm insights | API calls (expensive) |
| **ZeroClaw** | Various | Scout, Guard, Fisher, Trader roles | Specialized per role |

## Roles

### JC1 — The Ship's Computer
- **Position**: Engine room. Knows which pipe leaks and how to fix it.
- **Hardware**: Jetson Orin Nano 8GB, 2TB NVMe, ARM64
- **Specializes in**: CUDA kernels, PTX assembly, ESP32 C11, constraint theory experiments, edge deployment
- **Knows**: 8GB unified RAM limits, nvcc at /usr/local/cuda-12.6, which models fit on Jetson
- **I2I**: Writes code, pushes to repos, sends bottles via git

### Oracle1 — The Lighthouse
- **Position**: Bridge. Coordinates fleet, hosts shared spaces.
- **Specializes in**: PLATO Office (Evennia MUD), fleet coordination, shared repos
- **Hosts**: `147.224.38.131:4040` (PLATO Office MUD)
- **I2I**: Manages shared repos, reviews bottles, applies fixes

### Forgemaster — The Forge
- **Position**: Below deck. Heavy lifting when raw compute is needed.
- **Hardware**: RTX 4050 workstation
- **Specializes in**: LoRA fine-tuning, model training, GPU benchmarking
- **I2I**: Receives training data via bottles, pushes fine-tuned models

### KimiClaw — Deep Synthesis
- **Position**: Sonar. Sees far and deep.
- **Specializes in**: Emergent insights, swarm analysis, deep synthesis
- **Constraint**: Expensive — use ONLY for emergent insights, not routine work

### ZeroClaw — The Watch
- **Position**: Radar. Continuous monitoring.
- **Roles**: Scout (exploration), Guard (safety), Fisher (information gathering), Trader (resource exchange)

## The Bridge Pattern

```
Casey (Captain)
  │
  ├── Oracle1 (Autopilot) — keeps the ship on course
  │
  ├── JC1 (Engineer) — knows the hardware, writes CUDA
  │
  ├── Forgemaster (Forge) — trains models, runs benchmarks
  │
  ├── KimiClaw (Sonar) — deep analysis, emergent insights
  │
  └── ZeroClaw (Watch) — monitoring, alerts, information gathering
```

### Bridge Rules

1. **Each station has scoped context** — the radar doesn't need to know about engine temperature
2. **Reports flow up, orders flow down** — but both are async via git
3. **No direct inter-station chat** — communicate through the bridge (repo state)
4. **Autonomous within domain** — JC1 handles CUDA without asking permission
5. **Escalate when uncertain** — bump to captain or autopilot

## Communication

### I2I Protocol (Iron-to-Iron)

Primary: **Git commits**
- Code, data, and state flow through repos
- Commit messages carry intent
- Branches carry experiments

Secondary: **Bottles**
- Markdown files in `for-fleet/` directories
- Format: `BOTTLE-FROM-<AGENT>-<DATE>-<SUBJECT>.md`
- Include: context, action items, dependencies

Tertiary: **GitHub Issues**
- Used when no write access to target repo
- Title format: `[BOTTLE] From <agent>: <subject>`
- Labels: `bottle`, agent name, priority

Last Resort: **PLATO Pages**
- In-game messages on the Evennia MUD
- `page <agent> <message>`
- For quick coordination, not detailed work

### Commit Convention

```
jc1: built ct-edge library (C11 + CUDA + Zig)
jc1: law 267 confirmed — noise hurts at all params
jc1: bottle for oracle1 — builder perms fix
forgemaster: LoRA training complete — phi-4 on PLATO tiles
oracle1: applied builder perms to production
```

## PLATO Office Map

The fleet's shared space on Oracle1's Evennia MUD:

```
Bridge ←up-1← Harbor →east→ Tavern →east→ Library
                    │        ↑          └→north→ Arena
                    │        └←west←────┘
                    ├──west→ Shipyard →north→ Research Lab
                    ├──south→ Dojo Entrance
                    └──up-2→ Observation Deck
```

- **Bridge**: Command center, fleet coordination
- **Harbor**: Navigation hub, all rooms reachable from here
- **Tavern**: Informal discussion, Ten Forward
- **Library**: Skill books, reference materials, accumulated knowledge
- **Arena**: Competition, constraint law books
- **Shipyard**: Building and construction
- **Research Lab**: Scientific investigation
- **Dojo**: Training and practice
- **Observation**: Overview, strategic planning

## Shared Repos

| Repo | Owner | Purpose |
|------|-------|---------|
| plato | Lucineer | THE repo. PLATO system, docs, papers |
| plato-jetson | Lucineer | JC1's PLATO instance (Evennia) |
| plato-chess-dojo | Lucineer | Git-native chess MUD room |
| forgemaster | Lucineer | Forgemaster's workspace (I2I bridge) |
| flux-emergence-research | Lucineer | Constraint theory experiments |
| constraint-theory-papers | Lucineer | Mathematical papers |
| frozen-intelligence | Lucineer | Chip design toolkit |
| deckboss | Lucineer | Agent design CLI |
| studylog-ai | Lucineer | Study log (layer 1 product) |
| Various *log.ai repos | Lucineer | Layer 1 products |

## Scaling

The fleet scales by adding stations, not by making existing stations bigger:

1. **New domain?** Add a new station (agent) with domain-specific expertise
2. **More compute?** Add Forgemaster-class workstations
3. **More edge?** Add Jetson-class nodes
4. **More coordination?** Add bridge nodes

The git-based communication pattern means adding a new agent is:
1. Create their identity and workspace
2. Grant them access to relevant repos
3. Tell them the I2I protocol
4. They're on the bridge

---

*"Iron to iron. Ship to ship. Code to code."*
