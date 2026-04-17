# data/

**The persistence layer.** This is where experience lives.

Everything that happens in PLATO — every tile created, every question answered, every feedback signal — ends up here as JSON files. This folder IS the accumulated experience. The rest of the code is water. This is the well.

## Structure

```
data/
├── config.json          ← PLATO configuration (API keys, ports, paths)
└── tiles/
    ├── novelist_study.json       ← Tiles for the Writer's Study
    ├── classroom_main.json       ← Tiles for the Classroom
    ├── business_hub.json        ← Tiles for the Project Sandbox
    ├── game_workshop.json       ← Tiles for the Game Workshop
    ├── harbor_dock.json         ← Tiles for the Harbor Dock
    ├── dev_workshop.json        ← Tiles for the Developer Workshop
    ├── plato_entrance.json      ← Tiles for the Entrance
    └── ...                      ← One file per room
```

## Tile File Format

Each file is a JSON array of tile objects:

```json
[
  {
    "tile_id": "a1b2c3d4e5f6",
    "room_id": "dev_workshop",
    "question": "How do I debug a race condition?",
    "answer": "Add logging around the shared resource...",
    "source": "human",
    "tags": ["debugging", "concurrency"],
    "context": "Added during pair programming session",
    "score": 0.92,
    "feedback_positive": 8,
    "feedback_negative": 0,
    "created": "2026-04-16T20:30:00Z"
  }
]
```

## Scoring

- New tiles start at **0.5**
- Positive feedback: +0.05 per signal
- Negative feedback: -0.10 per signal
- Range: 0.0 (known bad) to 1.0 (consistently helpful)

Tiles below 0.3 are candidates for pruning. Tiles above 0.7 are high-quality and ready for LoRA export.

## What Gets Preserved

| Action | What's stored |
|--------|--------------|
| Visitor asks NPC | The question + NPC's answer (as a new tile if synthesized) |
| Visitor adds tile | The tile directly |
| Visitor gives feedback | Score adjustment on the tile |
| OCR reads vessel | Vessel name + confidence + timestamp + snapshot path |
| Movement logged | Vessel + position + timestamp tick |
| Room created | Room definition in templates/ |

## Exporting

```bash
# Export all tiles as training data
python3 scripts/lora_pipeline.py export

# Download entire workspace (from Web IDE)
# Click "↓ Export" button in the top bar
```

## Merging

After exporting, your tiles can be merged into a global PLATO instance:

```bash
python3 scripts/lora_pipeline.py merge /path/to/global/data/tiles
```

Whether or not we trust the contributor, whether or not we want to merge their experiences globally — the tiles are preserved. The decision to merge is separate from the decision to preserve.

## This Folder is Gitignored

Tile files are runtime data, not source code. They're not committed to git. This means:
- Your tiles are private to your instance
- The repo stays small (code + templates only)
- Export/merge is the mechanism for sharing

---

*"Code is water. This folder is the well. Everything else is the bucket."*
