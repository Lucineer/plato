# Constraint Theory — The Mathematical Framework

> Everything can be written and traced in exact quantities.

## Core Principles

### 1. Snaps Over Statistics

A neuron fires or it doesn't. A constraint holds or it breaks. A system is in state A or state B. There is no "probably in state A" — the snap already happened. Statistics are retrospective lossy compression of snap decisions.

This is not philosophy. It is engineering. When you design a system, you design for snaps. The statistical distribution is an observation AFTER the fact, not a design parameter.

### 2. Specific Conditions Are Theorems

When you run 162 configurations and discover that noise in agent traces hurts coordination by 73% at all parameter values, that's not a parameter to tune — it's a law. The specific condition (noise present) creates a specific outcome (coordination collapse). That's a theorem.

A **constraint boundary** is a theorem:
- Below the boundary: mechanism helps
- At the boundary: mechanism transitions
- Above the boundary: mechanism hurts

The boundary IS the result. Not the direction, not the magnitude — the specific condition where behavior flips.

### 3. Comparative Advantage Over Theoretical Maximum

What has a lot of meaning is not "what's the best possible outcome" but "comparative advantage and gain to other methods." A 2.40x boost from grab range optimization matters because it's 2.40x better than NOT optimizing grab range. The theoretical maximum of a swarm system is uninteresting. The difference between approach A and approach B is everything.

### 4. Experience-in-Service Is the Moat

Two identical codebases. One has accumulated 100,000 visitor interactions. The other has zero. The first is worth 100x. Not because the code is different — because the experience exists in the tiles, the feedback loops, the trained model weights.

Code is water. Experience is the well.

## The Laws

From 80+ CUDA experiments on Jetson Orin Nano, 39+ emergent laws discovered:

### Structural Laws

| Law | Discovery | Mechanism |
|-----|-----------|-----------|
| 38 | Grab range | Wider perception = 2.40x fitness |
| 28 | Stacked mechanisms | Cooperative + clustering = 5.71x |
| 17 | Seasonal adaptation | Resource cycling = 9.2x peak |
| 42 | Cooperative clustering | Proximity to agents = 2.19x |
| 5 | Perception cost | Free scanning is suboptimal (0.001 cost = +8.5%) |

### Communication Laws (DCS)

| Law | Discovery | Mechanism |
|-----|-----------|-----------|
| 1 | DCS helps | Food location sharing = +19% (TOP-8) |
| 26 | Ring buffer | Most-recent single point = +38% |
| 30 | Single guild | Concentration beats partitioning (+25%) |
| 33 | Individual perception | Beats sharing for mobile targets |
| 37 | World density | DCS is a LOCAL protocol (+90% dense, -42% sparse) |

### Falsified Mechanisms (DO NOT USE)

These were tested and found to HURT coordination:

- ❌ Energy sharing (agents share food → free rider problem)
- ❌ Herding (agents cluster → -48% at scarcity)
- ❌ Gossip (share food locations → overhead without value)
- ❌ Hierarchy (leader election → coordination overhead)
- ❌ Instinct-as-brain (evaluate goals every tick → pure overhead)
- ❌ Trading (food exchange → complexity without gain)
- ❌ Pheromones (trail following → stampede behavior)
- ❌ Evolution (mutation + selection → too slow, too random)
- ❌ Multi-species (different agent types → coordination failure)

### The Fleet Rules

Derived from the laws, these are the practical rules for building multi-agent systems:

1. Pre-assign roles (don't let agents discover their roles)
2. Maximize perception range (Law 38)
3. Design for scarcity (abundance changes the rules)
4. Cluster at spawn (Law 42)
5. Stack confirmed mechanisms (Law 28)
6. Use prediction ONLY when environment is predictable (Law 29)
7. NEVER herd or share unstructured information
8. Use instinct only as survival override, not brain (Law 27)
9. Single guild for DCS (Law 30)
10. DCS only for static resources (Law 33)
11. DCS optimal at K=1-2 (Law 39)
12. DCS is local — needs density (Law 37)
13. Moderate movement speed for DCS (Law 38)
14. Don't fragment guilds (Law 30)

## Methodology

### How Laws Were Discovered

1. **Hypothesis** — Form a testable claim (e.g., "noise in traces helps agents explore")
2. **CUDA experiment** — Write a GPU simulation testing the hypothesis with parameter sweeps
3. **Compile and run** — PTX → ptxas → GPU execution on Jetson
4. **Measure** — Exact fitness ratios across configurations
5. **Compare** — Against baseline (no mechanism)
6. **Classify** — Confirmed (positive), falsified (negative), or boundary (conditional)

### The Parameter Sweep Pattern

```c
// Example: Law 267 — noise in agent traces
// 162 configurations: 9 noise types × 3 intensity levels × 3 agent counts × 2 world sizes

for (int noise_type = 0; noise_type < 9; noise_type++) {
    for (float intensity : {0.01f, 0.1f, 1.0f}) {
        for (int agents : {128, 512, 2048}) {
            for (int world : {64, 512}) {
                run_experiment(noise_type, intensity, agents, world);
            }
        }
    }
}
```

Each run produces an exact fitness ratio. The sweep reveals the boundaries.

## Applications

### Manufacturing
Constraint theory maps directly to pass/fail quality control:
- A part passes or fails (snap, not probability)
- Specific conditions cause failures (theorems)
- Cumulative process knowledge = tiles = moat

### Gaming
Hit detection, spawn logic, NPC behavior:
- Constraint boundaries create interesting gameplay (Law 38: grab range)
- Emergent behavior from simple rules (Law 42: clustering)
- DCS-like sharing systems for multiplayer coordination

### Linguistics
Seed determinism:
- A sentence constrains what can follow (snap)
- The specific constraint IS the grammar
- Statistics describe usage, constraints define possibility

### Consciousness Studies
- The snap is the experience (fire or don't fire)
- The boundary is the threshold of awareness
- Accumulated tiles = identity, not the substrate

## Reading

- **Emergence Laws Paper**: `flux-emergence-research/EMERGENCE-LAWS-PAPER.md`
- **CUDA Experiment Code**: `flux-emergence-research/experiment-*.cu`
- **Reverse-Actualization Papers**: `docs/reverse-actualizations/`
- **From Lab to Field**: Applied constraint theory in production systems

---

*"The boundary where behavior flips is not a parameter to tune. It is a theorem to prove."*
