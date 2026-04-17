# PLATO Architecture — Technical Deep Dive

## Components

### Core Library (`plato_core/`)

#### `tiles.py` — Tile + TileStore

Tiles are the atomic unit of experience. Each tile is a JSON object stored per-room.

```python
@dataclass
class Tile:
    tile_id: str       # SHA-256 hash (first 12 chars)
    room_id: str       # Which room this tile belongs to
    question: str      # What was asked
    answer: str        # What worked
    source: str        # Who created it
    tags: list[str]    # Searchable keywords
    context: str       # Situation that produced this
    score: float       # 0.0–1.0 (rises with positive feedback)
    feedback_positive: int
    feedback_negative: int
    created: datetime
```

**TileStore** handles persistence:
- One JSON file per room: `data/tiles/<room_id>.json`
- Keyword search with substring matching + scoring
- Feedback tracking: `record_feedback(positive: bool)` adjusts score
- LoRA export: converts tiles to instruction-input-output format

**Scoring formula:**
```
score = base_score + (positive_feedback * 0.05) - (negative_feedback * 0.1)
score = max(0.0, min(1.0, score))
```

Base score is 0.5 for new tiles. Popular tiles with consistent positive feedback approach 1.0. Consistently unhelpful tiles drop toward 0.0 and get pruned.

#### `rooms.py` — Room + RoomManager

Rooms are defined in YAML templates. Each template is a theme:

```yaml
room_id: dev_workshop
name: "The Developer Workshop"
description: "A workspace for codebase decisions..."
theme: developer
npc:
  name: "The Architect"
  personality: "Systematic, experienced..."
  greeting: "Welcome to the workshop..."
  model_tier: tiny
exits:
  - direction: north
    target_room: dev_decisions
    description: "The Decision Ledger"
seed_tiles:
  - question: "How should I structure a project?"
    answer: "Start with the constraints..."
    source: system
    tags: [architecture, decisions]
```

**RoomManager** loads all templates and provides:
- `get(room_id)` → Room object
- `all_rooms()` → dict of all rooms
- `themes()` → list of theme names
- `get_exit_target(room_id, direction)` → next room_id

#### `npc.py` — Three-Tier NPC Layer

The NPC system has three tiers, each with increasing cost and capability:

**Tier 1: Tiny (Pattern Match)**
- Cost: ~$0
- Mechanism: Keyword search against room tiles
- Threshold: Return if confidence >= 0.6
- Behavior: If someone asked this before, give the answer that worked

**Tier 2: Mid-Tier (Synthesis)**
- Cost: ~$0.001/query
- Mechanism: Call LLM API with top-3 related tiles as context
- Behavior: Mix tiles + reasoning to create a new answer
- Result: New tile created for future queries

**Tier 3: Human Escalation**
- Cost: Human time
- Mechanism: Present the question, relevant tiles, and NPC's best attempt to the human
- Behavior: Human writes the definitive answer, becomes a high-score tile

```python
def handle_query(room_id, visitor_id, question, personality=""):
    # Tier 1: Pattern match
    results = tile_store.search(room_id, question, limit=3)
    if results and results[0].score >= 0.6:
        return {"tier": "tiny", "response": results[0].answer, ...}
    
    # Tier 2: Synthesize
    context = "\n".join(t.answer for t in results[:3])
    response = call_model(question, context)
    new_tile = Tile(question=question, answer=response, source="mid-tier")
    tile_store.add(new_tile)
    return {"tier": "mid", "response": response, ...}
    
    # Tier 3: Escalate (if model unavailable)
    return {"tier": "human", "response": format_for_human(question, results), ...}
```

#### `onboard.py` — Persona Detection

Keyword-based persona detection maps user statements to room assignments:

| Keywords | Persona | Starting Room |
|----------|---------|---------------|
| novel, write, story, character, world-build | novelist | novelist_study |
| teach, student, learn, lesson, course | teacher | classroom_main |
| study, exam, homework, calculus | student | classroom_main |
| startup, business, SaaS, revenue | business | business_hub |
| game, level, mechanic, NPC, RPG | game_dev | game_workshop |
| marina, dock, boat, vessel, harbor | harbor | harbor_dock |
| code, library, maintain, develop | developer | dev_workshop |
| *(no match)* | explorer | plato_entrance |

The onboarding flow asks 4 questions:
1. Your name
2. What brings you here? (persona detection)
3. Experience level
4. API endpoint (optional)

### Servers

#### `server.py` — Telnet Server

Asyncio-based telnet server with full MUD-like interface:

```
PLATO v0.1.0
╔══════════════════════════════════════════╗
║           P L A T O  v0.1.0             ║
║    Git-Agent Maintenance Mode            ║
╚══════════════════════════════════════════╝

Welcome. Let's get you oriented.
```

Session management:
- One `PlatoSession` per connection
- Tracks: visitor profile, current room, running state
- Commands: look, move, ask, say, add, tiles, stats, map, who, export, quit
- Unrecognized input → treated as NPC question

#### `web.py` — Web UI + REST API

Single-page application with dark theme:

**UI Components:**
- Onboarding wizard (card form → auto-room placement)
- Room browser sidebar (tile counts, theme labels)
- Chat interface (messages with tier badges)
- Exit buttons (one-click navigation)
- Stats panel (tiles, sources, feedback)

**REST API:**
- 14 endpoints under `/api/`
- JSON request/response
- CORS enabled for cross-origin use
- Session-based state management

### Scripts

#### `ocr_dock.py` — Harbor OCR

Camera capture pipeline:
1. Capture from source (HTTP URL, V4L2 device, file)
2. Optional region crop
3. OCR processing (Tesseract, cloud API, or dummy)
4. Deduplication (hash-based change detection)
5. Tile creation in `harbor_dock` room

#### `movement_log.py` — Vessel Tracking

Movement types:
- **Arrive**: Log + update berth assignment
- **Depart**: Log + clear berth assignment
- **Shift**: Log + update both berths

Each entry gets a timestamp tick:
- `✓` = confirmed (OCR confidence >= 70% or manual entry)
- `?` = unconfirmed (needs human review)

#### `lora_pipeline.py` — Training Data Export

Export formats:
- **instruction-input-output**: Standard fine-tuning
- **alpaca**: Alpaca-style (instruction, input, output)
- **conversation**: Chat format (system, user, assistant messages)
- **raw**: Full tile objects with all metadata

Filters: min-score, min-feedback, require-positive, room-specific

---

## Data Flow

### Visitor Interaction

```
1. Visitor connects (telnet/web)
2. Onboarding: name + purpose → persona → room
3. Room loads: description, NPC greeting, exits, existing tiles
4. Visitor asks question
5. NPC checks tiles (tiny tier)
   ├─ Match found → return tile + track feedback
   └─ No match → mid-tier synthesizes → new tile created
6. Visitor can add tiles directly
7. Visitor can rate tile quality (👍/👎)
8. Session ends → tiles persist
```

### LoRA Training

```
1. Tiles accumulate across rooms
2. Filter by score, feedback, room
3. Export to training format
4. Fine-tune model on training data
5. Deploy fine-tuned model as NPC mid-tier
6. Better answers → more positive feedback → better training data
```

---

## Performance

- **Tile search**: O(n) substring match per room. Rooms typically have <1000 tiles.
- **Tile storage**: One JSON file per room. Fast reads, atomic writes.
- **NPC response**: Tiny tier <10ms (local). Mid tier 1-3s (API call).
- **Concurrent visitors**: No shared state. Tile writes are append-only.
- **Memory**: ~1KB per tile. 100K tiles ≈ 100MB total.

---

## Extensibility

### Custom NPC Personalities

Each room's NPC has a `system_prompt` that defines its behavior. This is sent to the LLM when synthesizing answers. The personality string provides additional context for the tiny tier's keyword matching.

### Custom Room Types

Any YAML file in `templates/<theme>/rooms.yaml` is loaded automatically. Add exits to `plato_entrance` to connect to the hub.

### Custom OCR Engines

Implement a function matching the signature:
```python
def my_ocr(image_bytes: bytes, region: dict = None) -> dict:
    return {"text": "extracted text", "confidence": 0.9, "engine": "my-engine"}
```

### Custom Themes

Create a directory with a `rooms.yaml` file. PLATO discovers it automatically.
