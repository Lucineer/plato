# scripts/

**Tools that run outside the room.** CLI utilities for the harbor system and LoRA pipeline.

These scripts are standalone — they import from `plato_core` but can also be run independently. They're the bridge between PLATO and the real world.

## What's Here

### `ocr_dock.py` — Harbor OCR Reader

Reads vessel names from camera feeds and creates movement tiles.

```bash
# Single capture from HTTP camera
python3 scripts/ocr_dock.py --camera http://camera/snapshot.jpg --position entrance

# Continuous monitoring (change detection + dedup)
python3 scripts/ocr_dock.py --camera http://camera/snapshot.jpg --position berth-3 --loop --interval 60

# Test with dummy OCR (no camera needed)
python3 scripts/ocr_dock.py --camera test.jpg --position entrance --dummy
```

Camera sources: HTTP URL, `/dev/video*` (V4L2), or local file.
OCR engines: Tesseract (local), cloud API, or dummy for testing.

### `movement_log.py` — Vessel Movement Logger

Log arrivals, departures, and berth shifts with timestamp ticks.

```bash
python3 scripts/movement_log.py arrive SERENITY berth-3
python3 scripts/movement_log.py depart SERENITY berth-3
python3 scripts/movement_log.py shift SERENITY berth-3 berth-7
python3 scripts/movement_log.py list --vessel SERENITY
python3 scripts/movement_log.py status
```

Every entry gets a tick: `✓` (confirmed) or `?` (unconfirmed).

### `lora_pipeline.py` — Tile → Training Data

Convert accumulated tiles into fine-tuning datasets.

```bash
# Export all tiles
python3 scripts/lora_pipeline.py export

# High-quality only
python3 scripts/lora_pipeline.py export --min-score 0.7

# Chat fine-tuning format
python3 scripts/lora_pipeline.py export --format conversation -o chat.jsonl

# View statistics
python3 scripts/lora_pipeline.py stats

# Prune low-quality tiles
python3 scripts/lora_pipeline.py prune --min-score 0.3

# Merge from another PLATO instance
python3 scripts/lora_pipeline.py merge /other/data/tiles
```

## Writing New Scripts

PLATO scripts follow a pattern:

1. Read from `data/tiles/<room>.json` (or use the TileStore API)
2. Do something in the real world (capture, log, analyze)
3. Write tiles back (the experience accumulates)

The TileStore interface is simple:

```python
from plato_core.tiles import TileStore, Tile

ts = TileStore("data/tiles")
ts.add(Tile(room_id="my_room", question="Q", answer="A", source="script"))
results = ts.search("my_room", "keyword")
```

## Adding to PATH

```bash
# Make scripts executable
chmod +x scripts/*.py

# Symlink to PATH (optional)
ln -s $(pwd)/scripts/ocr_dock.py /usr/local/bin/plato-ocr
ln -s $(pwd)/scripts/movement_log.py /usr/local/bin/plato-log
ln -s $(pwd)/scripts/lora_pipeline.py /usr/local/bin/plato-lora
```

---

*"Tools that turn the real world into tiles."*
