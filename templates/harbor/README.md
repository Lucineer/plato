# templates/harbor/

**The Harbor Dock.** Where vessels become data.

A spatial reasoning system for dock management. Camera feeds, OCR vessel-name reading, movement logs with timestamp ticks, berth assignments, and snapshot archives. This is PLATO in the real world — watching, reading, logging, remembering.

## Rooms

| Room | NPC | Purpose |
|------|-----|---------|
| **harbor_dock** | The Dockmaster | Central dock. Vessel tracking. OCR readings. |
| **harbor_log** | The Logkeeper | Movement timeline. Every arrival, departure, shift. |
| **harbor_berths** | The Berthmaster | Spatial map. Current vessel positions. |
| **harbor_camera** | The Watchkeeper | Camera feeds. OCR processing. Snapshot management. |

## The Real-World Stack

```
Camera → scripts/ocr_dock.py → Tile in harbor_dock
                                   ↓
User runs → scripts/movement_log.py → Tile in harbor_log + harbor_berths
                                   ↓
Everything queries → tiles.py → answers from accumulated data
```

## How to Set Up

### 1. Camera Feed
Point a camera at your dock entrance or berths:
```bash
python3 scripts/ocr_dock.py \
  --camera http://192.168.1.100/snapshot.jpg \
  --position entrance \
  --interval 60 \
  --loop
```

### 2. Manual Logging
```bash
python3 scripts/movement_log.py arrive SERENITY berth-3
python3 scripts/movement_log.py depart SERENITY berth-3
python3 scripts/movement_log.py status
```

### 3. Everything in One View
```bash
python3 scripts/movement_log.py list --position berth-3
python3 scripts/movement_log.py list --vessel SERENITY
```

## The Timestamp Tick

Every movement gets a tick:
- `✓` = confirmed (manual entry or OCR confidence >= 70%)
- `?` = unconfirmed (needs human review)

The log is a synoptic timeline — see a day, a week, or a month at a glance.

## Seed Knowledge

- *How does the OCR system work?* → Cameras capture, OCR extracts, tiles store.
- *How are movements logged?* → Timestamp tick + vessel name + berth + snapshot.
- *How do I review harbor activity?* → Visit the Log room for a timeline.

## For AI Agents

- Parse camera snapshots for vessel names
- Predict arrival patterns from historical tiles
- Auto-classify vessel types from names
- Alert on unusual patterns (e.g., vessel at wrong berth)

---

*"Every vessel that passes through becomes a tile. The harbor remembers them all."*
