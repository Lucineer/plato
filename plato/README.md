# plato/

**The CLI.** One command and you're running.

```
python3 -m plato --both
```

That's it. Telnet on :4040, Web IDE on :8080.

## What this does

1. Loads room templates from `../templates/`
2. Seeds empty rooms with starter tiles from `../data/tiles/`
3. Starts the telnet server (asyncio, handles multiple visitors)
4. Starts the web IDE (HTTP, browser-based PLATO)
5. Opens the door for AI agents to board via telnet

## Files

| File | Purpose |
|------|---------|
| `__main__.py` | Entry point. Parses args, loads config, starts servers. |
| `__init__.py` | Package marker. |

## Flags

| Flag | What it does |
|------|-------------|
| `--both` | Telnet + Web IDE simultaneously (the default experience) |
| `--web` | Web IDE only |
| *(none)* | Telnet only |
| `--port N` | Custom telnet port |
| `--web-port N` | Custom web port |
| `--theme X` | Load only one theme's rooms |
| `--setup` | Interactive first-time wizard |

## How it connects to everything else

```
__main__.py
  ├── plato_core/server.py   → telnet :4040
  └── plato_core/ide.py      → web :8080
        ├── plato_core/rooms.py  → loads templates/*.yaml
        ├── plato_core/tiles.py  → reads/writes data/tiles/*.json
        └── plato_core/npc.py    → three-tier NPC layer
```

The user never touches this folder. They run `python3 -m plato` and everything starts.
