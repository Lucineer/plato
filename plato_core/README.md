# plato_core/

**The engine room.** Every neuron of the PLATO system lives here.

This is where tiles get stored, rooms get loaded, NPCs think, and visitors get oriented. You don't need to touch this folder to use PLATO. But if you want to understand how it works — or extend it — this is the place.

## Architecture

```
plato_core/
├── tiles.py      ← Memory. The tile data structure + TileStore (JSON persistence)
├── rooms.py      ← World. Room definitions loaded from YAML templates
├── npc.py        ← Brain. Three-tier NPC layer (tiny → mid → human)
├── onboard.py    ← Doorway. Persona detection + onboarding flow
├── server.py     ← Telnet. Asyncio MUD-style server
└── ide.py        ← Browser. Web IDE + REST API + workspace export
```

## The Core Loop

Every visitor interaction follows the same path:

```
Visitor arrives → onboard.py detects persona → rooms.py places in room
                                                ↓
Visitor asks → npc.py checks tiles.py (pattern match)
                  ├─ found → return tile (tiny tier, $0)
                  └─ miss → synthesize new answer (mid tier, ~$0.001)
                            └─ creates new tile in tiles.py
```

## Tiles (tiles.py)

The atomic unit of experience. One JSON file per room, one tile per knowledge fragment.

```python
Tile(
    tile_id="a1b2c3d4e5f6",    # SHA-256, first 12 chars
    room_id="dev_workshop",     # Which room
    question="How do I debug?", # What was asked
    answer="Binary search...",  # What worked
    source="human",            # Who created it
    tags=["debugging"],        # Searchable
    score=0.87                 # Rises with feedback
)
```

Key methods:
- `search(room_id, query, limit)` → keyword match with scoring
- `add(tile)` → append to room's JSON file
- `export_for_lora(room_id)` → training data format
- `room_stats(room_id)` → counts and scores

## Rooms (rooms.py)

Rooms are data. They come from YAML templates. The RoomManager discovers all `templates/*/rooms.yaml` files and loads them into Room objects.

```python
Room(
    room_id="dev_workshop",
    name="The Developer Workshop",
    description="...",
    theme="developer",
    npc=NPC(name="The Architect", greeting="..."),
    exits=[Exit(direction="north", target_room="dev_decisions")],
    seed_tiles=[{"question": "...", "answer": "..."}]
)
```

## NPC (npc.py)

Three tiers. Each with increasing cost and capability.

| Tier | Cost | Method | When |
|------|------|--------|------|
| **tiny** | $0 | Pattern-match tiles | Score >= 0.6 |
| **mid** | ~$0.001 | LLM + tile context | No good match |
| **human** | Human time | Escalate with context | API unavailable |

## Onboarding (onboard.py)

Keyword-based persona detection. Maps what people say to the right room.

"I'm writing a novel" → `novelist` → `novelist_study`
"I manage a marina" → `harbor` → `harbor_dock`
"I maintain a library" → `developer` → `dev_workshop`

8 personas, 25 rooms, automatic placement.

## Server (server.py)

Asyncio telnet server. Full MUD experience from a terminal. Commands: look, ask, say, add, move, tiles, stats, map, export, quit.

## IDE (ide.py)

The Web IDE. Single-page application. REST API. Room editor. Tile manager. Workspace export/download. Activity logging. Agent boarding status.

20+ API endpoints. Everything the web UI needs, everything an API consumer needs.

---

*"The code is the hull. This folder is the engine."*
