# PLATO

> *Step into the mind of your application.*

PLATO is a system where visitors interact with rooms that hold accumulated experience. Every question asked, every answer given, every decision documented — it all persists as **tiles**. Over time, the rooms get smarter. Not because the code changes, but because the experience accumulates.

This is the concept Casey Digennaro calls **git-agent maintenance mode**.

---

## What It Is

PLATO has three layers:

1. **A downloadable system** — clone, configure, run. Telnet or web UI.
2. **A philosophy** — code is water, experience is the well. Two identical codebases. One has 100,000 visitor interactions. The other has zero. The first is worth 100x.
3. **An ecosystem** — connected to a fleet of AI agents, constraint theory research, and a framework for building intelligent systems that learn from use.

### The One-Line Pitch

> Give your application a memory. Give your users a space. Watch the space get smarter every time someone visits.

---

## Quick Start

```bash
git clone https://github.com/Lucineer/plato.git
cd plato
pip install pyyaml
python3 -m plato --both
```

- **Telnet**: `telnet localhost 4040`
- **Web UI**: http://localhost:8080
- **Docker**: `docker compose up`

No API key required. PLATO works in tile-only mode.

---

## How It Works

### The Three Tiers

```
Visitor asks a question
         │
  ┌──────▼──────┐
  │  TINY MODEL  │  Pattern-match against existing tiles
  │  Cost: ~$0   │  "Has someone asked this before?"
  └──┬───────┬───┘
     │ YES   │ NO
     │       │
  Return    ┌──▼──────────┐
  the tile  │  MID-TIER    │  Synthesize from related tiles + reasoning
  track     │  Cost: ~$0.001│  Creates a NEW tile for next time
  feedback  └──┬───────┬───┘
     │          │       │
     │       YES│      NO
     │          │       │
     │       Return  ┌──▼──────────┐
     │       tile   │  HUMAN       │  Escalate to captain
     │              │  ESCALATION  │  Present context + options
     │              └──────────────┘
     │
  ┌──▼──────────┐
  │  TILE STORE  │  Every interaction becomes a tile
  │  + FEEDBACK  │  Score rises with positive signals
  └──────────────┘
```

### Tiles

Tiles are the atomic unit of experience. Each tile is:

```json
{
  "tile_id": "a1b2c3d4e5f6",
  "room_id": "dev_workshop",
  "question": "How do I structure a new project?",
  "answer": "Start with the constraints...",
  "source": "human",
  "tags": ["architecture", "decisions"],
  "score": 0.87,
  "feedback_positive": 12,
  "feedback_negative": 1,
  "created": "2026-04-16T03:00:00Z"
}
```

- **Question**: What was asked
- **Answer**: What worked
- **Source**: Who created it (visitor, NPC, mid-tier model, human)
- **Score**: Rises with positive feedback, drops with negative
- **Tags**: Searchable keywords

### The Flywheel

```
  ┌──────────────────────────────────────────────────┐
  │                                                  │
  ▼                                                  │
Agent runs ──→ Visitors interact ──→ Tiles created   │
  ▲                                      │          │
  │                                      ▼          │
  │                              LoRA fine-tune     │
  │                                      │          │
  │                                      ▼          │
  └────────── Agent handles more questions ◄─────────┘
```

Every visitor makes the system smarter. Every smart answer attracts more visitors. The flywheel accelerates.

---

## Rooms

### What's Included

**25 rooms across 7 themes:**

| Theme | Rooms | Use Case |
|-------|-------|----------|
| 🖊️ Novelist | Study, Library, Character Gallery, World Map | World-building, storytelling |
| 🎓 Classroom | Main room, Study Room, Practice Lab, Teacher's Room | Teaching, studying |
| 💼 Business | Sandbox, Decision Log, Market Intel, Team Room | Planning, strategy |
| 🎮 Game | Workshop, Level Studio, Systems Lab, NPC Forge | Game design |
| ⚓ Harbor | Dock, Ship's Log, Berth Map, Camera Room | Vessel tracking, OCR |
| 💻 Developer | Workshop, Decision Ledger, Debug Bench, Deploy Board | Coding, debugging |
| 🧭 Entrance | PLATO Hub | Central navigation |

### Onboarding

When someone connects, PLATO asks what they're working on and places them in the right room:

- "I'm writing a novel..." → Writer's Study
- "I teach high school..." → Classroom
- "I'm starting a business..." → Business Sandbox
- "I'm building a game..." → Game Workshop
- "I manage a marina..." → Harbor Dock
- "I maintain a Python library..." → Developer Workshop
- "Just exploring..." → PLATO Entrance

### Creating Custom Rooms

Add a YAML file in `templates/<your-theme>/rooms.yaml`:

```yaml
my_room:
  room_id: my_room
  name: "My Custom Room"
  description: "A room for my specific use case"
  theme: custom
  npc:
    name: "The Guide"
    personality: "Helpful, specific to your domain"
    greeting: "Welcome! Ask me anything."
    system_prompt: "You are an expert in..."
    model_tier: tiny
  exits:
    - direction: north
      target_room: plato_entrance
      description: "Back to the entrance"
  seed_tiles:
    - question: "Common question?"
      answer: "Helpful answer."
      source: system
      tags: [topic]
```

That's it. Restart PLATO and the room exists.

---

## Deployment

### Bare Metal
```bash
git clone https://github.com/Lucineer/plato.git
cd plato
pip install pyyaml
python3 -m plato --both    # Telnet :4040 + Web :8080
```

### Docker
```bash
docker compose up
```

### With API Keys (Full NPC Mode)
```bash
export PLATO_MODEL_ENDPOINT=https://api.deepseek.com/v1/chat/completions
export PLATO_MODEL_KEY=your-key
export PLATO_MODEL_NAME=deepseek-chat
python3 -m plato --both
```

### Self-Hosted Options
- **GitHub Actions**: Use the git-native MUD pattern (see `docs/GIT-NATIVE.md`)
- **Systemd timer**: File watcher triggers PLATO turns on tile changes
- **HTTP API**: Direct REST endpoint access via `/api/`
- **Codespaces**: `docker compose up` — click the globe on port 8080

### Commands
```bash
python3 -m plato                  # Telnet only (:4040)
python3 -m plato --web            # Web UI only (:8080)
python3 -m plato --both           # Both simultaneously
python3 -m plato --setup          # Interactive first-time setup
python3 -m plato --port 9000      # Custom telnet port
python3 -m plato --theme harbor   # Load only harbor rooms
```

---

## Scripts

### Harbor OCR (`scripts/ocr_dock.py`)
Read vessel names from camera feeds and create movement tiles.

```bash
# Single capture from HTTP camera
python3 scripts/ocr_dock.py --camera http://192.168.1.100/snapshot.jpg --position entrance

# Continuous monitoring with change detection
python3 scripts/ocr_dock.py --camera http://192.168.1.100/snapshot.jpg --position berth-3 --interval 60 --loop

# From file (testing)
python3 scripts/ocr_dock.py --camera test-image.jpg --position entrance --dummy

# With Tesseract OCR (local, no API needed)
pip install pillow pytesseract
sudo apt install tesseract-ocr
python3 scripts/ocr_dock.py --camera snapshot.jpg --position entrance

# With cloud OCR
python3 scripts/ocr_dock.py --camera snapshot.jpg --position entrance --ocr-api https://your-api.com/ocr --ocr-key key
```

### Movement Logger (`scripts/movement_log.py`)
Log vessel movements with timestamp ticks.

```bash
python3 scripts/movement_log.py arrive SERENITY berth-3
python3 scripts/movement_log.py depart SERENITY berth-3
python3 scripts/movement_log.py shift SERENITY berth-3 berth-7
python3 scripts/movement_log.py list --vessel SERENITY
python3 scripts/movement_log.py list --position berth-3
python3 scripts/movement_log.py status
```

### LoRA Pipeline (`scripts/lora_pipeline.py`)
Convert tiles to training data for fine-tuning.

```bash
# Export all tiles (score >= 0.3)
python3 scripts/lora_pipeline.py export

# High-quality only
python3 scripts/lora_pipeline.py export --min-score 0.7 --require-positive

# Specific room, alpaca format, JSONL
python3 scripts/lora_pipeline.py export --room dev_workshop --format alpaca --jsonl

# Chat fine-tuning format
python3 scripts/lora_pipeline.py export --format conversation -o chat_training.jsonl

# View statistics
python3 scripts/lora_pipeline.py stats

# Remove low-quality tiles
python3 scripts/lora_pipeline.py prune --min-score 0.3

# Merge tiles from another PLATO instance
python3 scripts/lora_pipeline.py merge /other-instance/data/tiles
```

---

## API Reference

All endpoints under `/api/`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/info` | System info (version, rooms, tiles, model) |
| POST | `/api/onboard` | Start onboarding session |
| POST | `/api/onboard/submit` | Complete onboarding, get persona + room |
| GET | `/api/rooms` | List all rooms with tile counts |
| GET | `/api/rooms/map` | Room connection graph |
| GET | `/api/look?session_id=X` | Describe current room |
| POST | `/api/move` | Move to adjacent room |
| POST | `/api/ask` | Ask the room's NPC |
| POST | `/api/tiles` | Add a knowledge tile |
| GET | `/api/tiles?room_id=X` | List tiles in a room |
| POST | `/api/feedback` | Give feedback on a tile (👍/👎) |
| GET | `/api/search?room_id=X&q=...` | Search tiles by keyword |
| GET | `/api/stats?room_id=X` | Room and NPC statistics |
| GET | `/api/export?room_id=X` | Export tiles for LoRA training |

---

## The Big Picture

### Why PLATO Exists

Most software is dead. It runs, it serves, it collects dust. Nobody remembers the decisions that shaped it. New developers make the same mistakes. Users ask the same questions. The support team answers the same tickets.

PLATO makes software alive. Not by changing the code — by accumulating experience.

### The Ecosystem

PLATO is part of a larger system:

```
                    ┌─────────────────────┐
                    │      cocapn         │
                    │  (the company)      │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐
     │  cocapn.ai    │ │ cocapn.com │ │  cocapn.*   │
     │  (platform)   │ │ (billing)  │ │  (products) │
     └────────┬──────┘ └────────────┘ └─────────────┘
              │
    ┌─────────┼──────────────────────────┐
    │         │                          │
┌───▼───┐ ┌──▼───┐ ┌──────┐ ┌────────┐ ┌────────┐
│ PLATO │ │ *log │ │deck- │ │capit-  │ │field-  │
│ (this)│ │ .ai  │ │ boss │ │aine    │ │captain│
└───┬───┘ └──────┘ └──────┘ └────────┘ └────────┘
    │
    │  PLATO rooms can run anywhere:
    │  Docker, GitHub Actions, systemd,
    │  Codespaces, bare metal, ESP32
    │
    └── connected via git, tiles, LoRA ──→
                                         
             ┌────────────────────────────┐
             │  The Fleet                 │
             │  JC1 (Jetson/Edge)        │
             │  Oracle1 (Cloud/Lighthouse)│
             │  Forgemaster (GPU/Training)│
             │  KimiClaw (Deep Synthesis) │
             │  ZeroClaw (Scout/Guard)    │
             └────────────────────────────┘
```

### Constraint Theory

PLATO is built on **Constraint Theory** — a framework for understanding how constraints create emergent behavior in complex systems. The key insights:

- **Snaps over statistics**: A neuron fires or it doesn't. A constraint holds or it breaks. Statistics are retrospective lossy compression of snap decisions.
- **Specific conditions are theorems**: When you discover that noise in agent traces hurts coordination by 73%, that's not a parameter — it's a law. The boundary where it flips is the theorem.
- **Experience-in-service is the moat**: Two identical codebases, one with accumulated experience, one without. The experience is worth 100x. Not the code.

See `docs/CONSTRAINT-THEORY.md` for the full framework and `docs/reverse-actualizations/` for papers written from 2031 explaining PLATO to specific audiences.

### The Reverse-Actualization Papers

31 documents written from the perspective of 2031, looking back at how PLATO changed everything. Each targets a specific audience:

- **Core Manifesto**: The foundational document
- **Technical**: ML Engineer, DevOps, Security Researcher, Data Scientist, Game Developer, Database Admin, Robotics Engineer, Civil Engineer
- **Business**: Startup Founder, VC Investor, Enterprise CTO, Product Manager, Solo Developer, Freelancer, Nonprofit Director, Small Business Owner
- **Creative**: UX Designer, Technical Writer, Journalist, Architect, Musician, Chef
- **Education**: Educator, Student, OSS Maintainer
- **Personal**: Parent, Hobbyist Maker

Read them in `docs/reverse-actualizations/`.

---

## The Moat

> Two applications with identical codebases. One has a PLATO with 100,000 visitor interactions. The other has zero. The first is worth 100x. Not because the code is different — because the experience is.

Code is water. Experience is the well.

PLATO is the well.

---

## File Structure

```
plato/
├── README.md                          ← You are here
├── LICENSE
├── Dockerfile
├── docker-compose.yml
│
├── plato/                             # CLI entry point
│   └── __main__.py                    #   python -m plato
│
├── plato_core/                        # Core library
│   ├── tiles.py                       #   Tile + TileStore (persistence)
│   ├── rooms.py                       #   Room + RoomManager (YAML loading)
│   ├── npc.py                         #   Three-tier NPC layer
│   ├── onboard.py                     #   Persona detection + onboarding
│   ├── server.py                      #   Telnet server (asyncio)
│   └── web.py                         #   Web UI + REST API
│
├── templates/                         # Room definitions (YAML)
│   ├── plato/rooms.yaml               #   Entrance hub (1 room)
│   ├── novelist/rooms.yaml            #   Writer's world (4 rooms)
│   ├── classroom/rooms.yaml           #   Learning environment (4 rooms)
│   ├── business/rooms.yaml            #   Business planning (4 rooms)
│   ├── game/rooms.yaml                #   Game development (4 rooms)
│   ├── harbor/rooms.yaml              #   Harbor management (4 rooms)
│   └── developer/rooms.yaml           #   Developer workspace (4 rooms)
│
├── scripts/                           # Standalone tools
│   ├── ocr_dock.py                    #   Harbor OCR + camera capture
│   ├── movement_log.py                #   Vessel movement logger
│   └── lora_pipeline.py               #   Tile → LoRA training data
│
├── docs/                              # Documentation
│   ├── ARCHITECTURE.md                #   Technical deep dive
│   ├── ECOSYSTEM.md                   #   cocapn ecosystem overview
│   ├── CONSTRAINT-THEORY.md           #   The mathematical framework
│   ├── GIT-NATIVE.md                  #   GitHub Actions MUD pattern
│   ├── FLEET.md                       #   Agent fleet architecture
│   ├── DEPLOY.md                      #   All deployment options
│   ├── reverse-actualizations/        #   31 papers from 2031
│   │   ├── 00-core-manifesto.md
│   │   ├── 01-startup-founder.md
│   │   └── ... (31 total)
│   └── ...
│
└── data/
    └── tiles/                         # Runtime tile storage (gitignored)
        └── <room_id>.json             #   One JSON file per room
```

---

## Roadmap

- [ ] **WebSocket support** — real-time visitor-to-visitor interaction
- [ ] **Multi-language NPCs** — room personality in any language
- [ ] **Embedded PLATO** — `<iframe>` embeddable widget for any website
- [ ] **PLATO-to-PLATO federation** — agents visit each other's rooms
- [ ] **Tiny model inference** — on-device NPC (phi-4, Qwen3-32B) for air-gap
- [ ] **PLATO Studio** — visual room builder (no YAML needed)
- [ ] **Tile marketplace** — share/sell room tiles between PLATO instances
- [ ] **GitHub App** — auto-create PLATO for any repo
- [ ] **Mobile app** — onboarding → room → tiles in 60 seconds

---

## License

MIT — because code is water. 🌊

---

*"The code is the hull. The PLATO is the cargo. And the cargo is what makes the voyage worthwhile."*
