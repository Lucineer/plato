# PLATO Admin Guide — System Administration

*Running, monitoring, and troubleshooting a PLATO instance.*

## System Overview

PLATO is a Python asyncio application with two interfaces:
- **Telnet** :4040 — interactive MUD-like interface
- **Web** :8080 — HTTP API for programmatic access

Six runtime modules process every visitor query:

```
Visitor Question
    │
    ▼
┌─────────────┐
│  State Machine │ ← Mermaid diagram routing
└──────┬──────┘
       ▼
┌─────────────┐
│  Assertions   │ ← Safety guardrails (MUST/SHOULD/WHEN)
└──────┬──────┘
       ▼
┌─────────────┐
│  JIT Context  │ ← Token-efficient prompt building (84% reduction)
│  + Anchors    │ ← [WordAnchor] resolution
│  + Episodes   │ ← Muscle memory recall
└──────┬──────┘
       ▼
┌─────────────┐
│  Tile Search  │ ← Find matching knowledge
└──────┬──────┘
       ▼
  Gear 1 (tile match) OR Gear 2 (LLM synthesis) OR Gear 3 (human)
       │
       ▼
  Response + Feedback Loop → Episode Recording
```

## Starting and Stopping

```bash
# Start
systemctl --user start plato.service

# Stop
systemctl --user stop plato.service

# Restart (after code changes)
systemctl --user restart plato.service

# Check status
systemctl --user status plato.service

# View logs
journalctl --user -u plato.service -f
```

## Configuration

Main config: `~/.openclaw/workspace/plato-deploy/config.yaml`

Key settings:
```yaml
host: "0.0.0.0"
telnet_port: 4040
web_port: 8080
rooms_dir: "templates/custom"
tiles_dir: "data/tiles"
model_endpoint: ""          # LLM API URL (empty = tile-only mode)
model_key: ""                # LLM API key
model_name: "deepseek-chat"  # Model identifier
jit_tier1_tokens: 500        # Max tokens for Tier 1 (always loaded)
jit_tier2_tokens: 2000       # Max tokens for Tier 2 (on-demand)
jit_max_tiles: 5             # Max tiles in JIT context
```

## Data Directory Structure

```
plato-deploy/
├── data/
│   ├── tiles/           ← Tile storage (JSON per room)
│   │   ├── room-id.json
│   │   └── ...
│   ├── audit/           ← Audit trails (one file per room per day)
│   │   ├── room-id/
│   │   │   ├── 2026-04-17.log
│   │   │   └── ...
│   ├── episodes/        ← Muscle memory (one file per room)
│   │   ├── room-id.json
│   │   └── ...
│   └── anchors/         ← Word anchor registry
│       └── room-id.json
├── templates/
│   └── custom/
│       ├── rooms.yaml   ← Room definitions
│       └── ...
├── plato_core/          ← Runtime modules
│   ├── tiles.py
│   ├── npc.py
│   ├── server.py
│   ├── statemachine.py
│   ├── assertions.py
│   ├── jit_context.py
│   ├── episodes.py
│   ├── word_anchors.py
│   ├── audit.py
│   ├── rooms/
│   └── onboard.py
└── docs/
    ├── VISITOR-GUIDE.md
    ├── BUILDER-GUIDE.md
    └── ADMIN-GUIDE.md   ← You are here
```

## HTTP API

Base URL: `http://localhost:8080`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/info` | GET | System info (version, rooms, tiles) |
| `/api/rooms` | GET | List all rooms |
| `/api/rooms/:id` | GET | Room details |
| `/api/rooms/:id/tiles` | GET | Tiles in a room |
| `/api/rooms/:id/ask` | POST | Ask a question (JSON: `{query, visitor_id}`) |
| `/api/rooms/:id/health` | GET | Room health score |

Example:
```bash
# System info
curl http://localhost:8080/api/info

# Ask a question programmatically
curl -X POST http://localhost:8080/api/rooms/medical-triage/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "I have a headache", "visitor_id": "admin"}'

# Room health
curl http://localhost:8080/api/rooms/medical-triage/health
```

## Monitoring

### Health Check
```
telnet localhost 4040
→ health
```

Key metrics:
- **Overall score** (0-100): composite of tile count, feedback ratio, escalation rate
- **Tiles**: total, positive/negative feedback
- **NPC stats**: query count, hit rates by tier
- **Episodes**: learned interactions with decay
- **State machine**: active/inactive, current state
- **Assertions**: count, hard vs soft
- **JIT**: token efficiency metrics

### Audit Trail
```
→ audit 50
```
Shows last 50 events for the room. Each event is timestamped and categorized:
- `SESSION_START` / `SESSION_END`
- `QUERY` / `NO_MATCH`
- `TILE_MATCH` (with score and tier)
- `ASSERTION_VIOLATION` (with severity)
- `STATE_TRANSITION` (from → to)
- `NEW_TILE` (source)
- `FEEDBACK` (positive/negative)
- `EPISODE_RECALL` (lines recalled)
- `WORD_ANCHORS` (tiles pulled)
- `CLUNK_SIGNAL` (query + iterations)
- `MODEL_CALL` (model, tokens, latency)

### Clunk Signals
```
→ clunks
```
Queries that took 3+ iterations. These indicate gaps in the room's knowledge. Each clunk should trigger a tile addition.

## Troubleshooting

### Room not loading state machine
- Check `rooms.yaml` for `state_diagram:` field
- Verify Mermaid syntax: `stateDiagram-v2` (not `stateDiagram`)
- Run `!state` to verify it loaded

### Assertions not firing
- Check `assertions_md:` field in room config
- Verify severity keywords: `[MUST]`, `[MUST NOT]`, `[SHOULD]`, `[WHEN]`
- v1 uses word matching — assertion words must appear in NPC responses
- Check `!assertions` for violation counts (if 0, words don't match)

### High escalation rate (too many HUMAN tier responses)
- Room needs more tiles
- Check `clunks` for specific questions to address
- Consider broadening tile questions to match more queries

### LLM not responding (stuck on MID tier)
- Check `model_endpoint` and `model_key` in config
- Test API directly: `curl -H "Authorization: Bearer KEY" ENDPOINT`
- Room works in tile-only mode (TINY tier) without LLM

### Memory usage
- Episodes are capped at 500 per room (auto-pruned)
- Tiles have no hard cap but large rooms slow search
- Audit logs are rotated daily

### Port already in use
```bash
# Check what's using the port
ss -tlnp | grep 4040

# Kill stale process
systemctl --user stop plato.service
# Then restart
systemctl --user start plato.service
```

## Performance Tuning

### JIT Context (biggest impact on token usage)
Default: 500 tokens Tier 1 + 2000 tokens Tier 2 + 5 tiles max.
- Reduce `jit_tier2_tokens` for constrained environments (Jetson)
- Reduce `jit_max_tiles` if LLM context window is small
- 84% reduction benchmarked with defaults (50 tiles: 2736→440 tokens)

### Episode Decay
Default: 10% per week. Episodes below strength 0.1 are pruned.
- Increase decay for fast-changing domains
- Decrease decay for stable knowledge bases

### Tile Search
Uses word overlap scoring. No external dependencies.
- Add more specific tile questions for better matching
- Use word anchors to connect related concepts
- `search` command to test matching quality

## Backup and Recovery

### Tiles (the knowledge)
```bash
cp -r data/tiles/ backup/tiles-$(date +%Y%m%d)/
```

### Episodes (muscle memory)
```bash
cp -r data/episodes/ backup/episodes-$(date +%Y%m%d)/
```

### Room Config
```bash
cp templates/custom/rooms.yaml backup/rooms-$(date +%Y%m%d).yaml
```

### Full Backup
```bash
tar czf plato-backup-$(date +%Y%m%d).tar.gz data/ templates/custom/
```

---

*PLATO v0.3.0 — The room remembers. The room improves. The room persists.*
