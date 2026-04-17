# PLATO — Git-Agent Maintenance Mode

> *Step into the mind of your application.*

PLATO is a system where code is water and experience is the well. Every git-agent
can spin up a PLATO instance as a way to do maintenance. Visitors step in, ask
questions, leave tiles (knowledge), and every interaction makes the system smarter.

## Quick Start

```bash
git clone https://github.com/Lucineer/plato.git
cd plato
pip install pyyaml
python3 -m plato --setup    # First-time configuration
python3 -m plato            # Start server (telnet :4040)
telnet localhost 4040        # Connect
```

## What Happens When You Connect

1. **Onboarding** — PLATO asks what you're working on
2. **Persona Detection** — Automatically places you in the right room:
   - 🖊️ **Novelist** → Writer's Study (world-building, characters, story library)
   - 🎓 **Teacher/Student** → Classroom (lessons, study room, practice lab)
   - 💼 **Business** → Project Sandbox (decisions, market intel, team knowledge)
   - 🎮 **Game Developer** → Game Workshop (levels, mechanics, NPC forge)
   - ⚓ **Harbor Master** → Harbor Dock (OCR vessel tracking, movement logs, berth map)
   - 💻 **Developer** → Dev Workshop (codebase decisions, debugging, deployment)
   - 🧭 **Explorer** → PLATO Entrance (first-time exploration)
3. **Ask questions** — The NPC in each room answers from accumulated tiles
4. **Add tiles** — Your knowledge becomes permanent, helping future visitors
5. **Leave** — Your tiles persist. The system is smarter because you visited.

## Architecture

### The Three Tiers

```
Visitor asks a question
         ↓
  TINY MODEL (tile-only)     Pattern-matches against prior tiles
  Cost: ~$0                  "Has someone asked this before?"
         ↓ YES                      ↓ NO
  Return the tile           MID-TIER MODEL (synthesis)
  Track feedback            Cost: ~$0.001/query
                            Mixes tiles + reasoning
                            Creates NEW tile for next time
         ↓                           ↓ NO
  Response sent         HUMAN ESCALATION
                            Present context + options to captain
```

### Tiles

Tiles are the atomic unit of experience. Each tile has:
- **Question** — what was asked
- **Answer** — what worked
- **Source** — who created it (visitor, NPC, mid-tier, human)
- **Feedback** — positive/negative signals from visitors
- **Context** — the situation that produced this knowledge

### The Flywheel

```
Agent runs → visitors interact → tiles created → LoRA fine-tuned
     ↑                                            ↓
     ←←←←← agent handles more questions ←←←←←←←←←
```

## Room Templates

### 🖊️ Novelist's World
- **Writer's Study** — Creative workspace with The Librarian NPC
- **Story Library** — Fragments, drafts, and reference materials
- **Character Gallery** — Character development with The Portraitist
- **World Map** — World-building with The Cartographer

### 🎓 Studylog Classroom
- **The Classroom** — Main teaching space with The Tutor
- **Study Room** — Quiet reference space with The Researcher
- **Practice Lab** — Hands-on experiments with The Lab Assistant
- **Teacher's Room** — Planning space with The Mentor

### 💼 Business Sandbox
- **Project Sandbox** — Central planning with The Strategist
- **Decision Log** — Every choice documented with The Historian
- **Market Intelligence** — Competitive analysis with The Analyst
- **Team Room** — Knowledge management with The Coordinator

### 🎮 Game Workshop
- **Game Workshop** — Central design space with The Designer
- **Level Studio** — Level design with The Architect
- **Systems Lab** — Game mechanics with The Engineer
- **NPC Forge** — Character behavior with The Voice Actor

### ⚓ Harbor & Docks
- **Harbor Dock** — Vessel tracking with The Dockmaster
- **Ship's Log** — Movement timeline with The Logkeeper
- **Berth Map** — Spatial vessel positions with The Berthmaster
- **Camera Room** — OCR feeds with The Watchkeeper

## Configuration

### Environment Variables
```bash
PLATO_MODEL_ENDPOINT=https://api.deepseek.com/v1/chat/completions
PLATO_MODEL_KEY=your-key
PLATO_MODEL_NAME=deepseek-chat
PLATO_TINY_MODEL=phi-4  # Optional: separate tiny model for NPCs
```

### Tile-Only Mode
No API key? PLATO works in tile-only mode. NPCs pattern-match against
existing tiles. Add enough tiles and the experience is still excellent.

### Adding Custom Rooms
Create a YAML file in `templates/<theme>/rooms.yaml`:
```yaml
my_room:
  room_id: my_room
  name: "My Custom Room"
  description: "A room for my specific use case"
  theme: custom
  npc:
    name: "The Guide"
    greeting: "Welcome to my room."
    model_tier: tiny
  exits:
    - direction: north
      target_room: plato_entrance
  seed_tiles:
    - question: "Common question?"
      answer: "Helpful answer."
      source: system
      tags: [topic]
```

## The Moat

Two applications with identical codebases. One has a PLATO with 100,000
visitor interactions. The other has zero. The first is worth 100x.

Not because the code is different — because the experience is.

Code is water. Experience is the well.

## License

MIT — because code is water. 🌊

---

*"The code is the hull. The PLATO is the cargo. And the cargo is what makes
the voyage worthwhile."*
