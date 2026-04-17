# Deployment Guide

## Quick Reference

| Method | Command | Ports |
|--------|---------|-------|
| Bare metal (telnet) | `python3 -m plato` | 4040 |
| Bare metal (web) | `python3 -m plato --web` | 8080 |
| Bare metal (both) | `python3 -m plato --both` | 4040 + 8080 |
| Docker | `docker compose up` | 4040 + 8080 |
| GitHub Actions | Push to repo | Git-based |
| Codespaces | `docker compose up` → click globe | 8080 |

## Prerequisites

- Python 3.10+
- `pyyaml` (`pip install pyyaml`)

That's it. Everything else is optional.

## Bare Metal

### Installation

```bash
git clone https://github.com/Lucineer/plato.git
cd plato
pip install pyyaml
```

### First-Time Setup

```bash
python3 -m plato --setup
```

Interactive wizard asks:
1. Do you have an LLM API endpoint? (y/n)
2. If yes: endpoint URL, API key, model name, tiny model name
3. Telnet port (default: 4040)

Creates `data/config.json` with your settings.

### Running

```bash
# Telnet only
python3 -m plato

# Web UI only
python3 -m plato --web

# Both simultaneously
python3 -m plato --both

# Custom ports
python3 -m plato --both --port 9000 --web-port 3000

# Specific theme only
python3 -m plato --theme harbor
```

### Connecting

```bash
# Telnet
telnet localhost 4040

# Or
nc localhost 4040

# Web
open http://localhost:8080
```

## Docker

### Quick Start

```bash
docker compose up
```

That's it. Telnet on 4040, web on 8080.

### With API Keys

```bash
# Option 1: Environment file
echo "PLATO_MODEL_ENDPOINT=https://api.deepseek.com/v1/chat/completions" > .env
echo "PLATO_MODEL_KEY=your-key-here" >> .env
echo "PLATO_MODEL_NAME=deepseek-chat" >> .env
docker compose up

# Option 2: Export
export PLATO_MODEL_ENDPOINT=https://api.deepseek.com/v1/chat/completions
export PLATO_MODEL_KEY=your-key-here
docker compose up
```

### Persistent Tiles

Tiles are stored in a Docker volume (`plato-data`). They persist across container restarts.

### Custom Build

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir pyyaml
EXPOSE 4040 8080
CMD ["sh", "-c", "python3 -m plato --web & python3 -m plato"]
```

## With LLM API (Full NPC Mode)

### Supported Providers

PLATO uses OpenAI-compatible chat completion endpoints. Any provider works:

```bash
# DeepSeek
export PLATO_MODEL_ENDPOINT=https://api.deepseek.com/v1/chat/completions
export PLATO_MODEL_KEY=sk-your-key
export PLATO_MODEL_NAME=deepseek-chat

# OpenAI
export PLATO_MODEL_ENDPOINT=https://api.openai.com/v1/chat/completions
export PLATO_MODEL_KEY=sk-your-key
export PLATO_MODEL_NAME=gpt-4o-mini

# Any OpenAI-compatible
export PLATO_MODEL_ENDPOINT=https://your-provider.com/v1/chat/completions
export PLATO_MODEL_KEY=your-key
export PLATO_MODEL_NAME=your-model
```

### Tiny Model (Optional)

For the mid-tier NPC synthesis, you can use a separate (cheaper) model:

```bash
export PLATO_TINY_MODEL=phi-4  # or any model name
```

### Without API Keys

PLATO works in **tile-only mode**. NPCs pattern-match against existing tiles. No API calls. No cost. Works great once you have enough tiles.

## Self-Hosted (No Docker)

### systemd Service

```ini
# ~/.config/systemd/user/plato.service
[Unit]
Description=PLATO Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/user/plato
ExecStart=/usr/bin/python3 -m plato --both
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable plato
systemctl --user start plato
```

### File Watcher (Turn Processing)

For git-native MUD rooms, use `inotifywait`:

```bash
#!/bin/bash
while inotifywait -e modify,create world/commands/; do
    python3 bridges/process_turns.py
    git add world/
    git commit -m "turn: $(date)"
    git push
done
```

### Bare Git Hook

For self-hosted git repos:

```bash
# /path/to/repo.git/hooks/post-receive
#!/bin/bash
GIT_WORK_TREE=/path/to/working-dir git checkout -f
cd /path/to/working-dir
python3 bridges/process_turns.py
git add world/
git commit -m "turn: $(date)"
```

## GitHub Codespaces

1. Open https://github.com/Lucineer/plato in Codespaces
2. Terminal: `docker compose up`
3. Click the globe icon on port 8080
4. Your PLATO is live at `https://xxxx-8080.app.github.dev/`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATO_MODEL_ENDPOINT` | (none) | OpenAI-compatible API endpoint |
| `PLATO_MODEL_KEY` | (none) | API key |
| `PLATO_MODEL_NAME` | `deepseek-chat` | Model for mid-tier NPC |
| `PLATO_TINY_MODEL` | (none) | Separate model for tiny tier |
| `PLATO_TELNET_PORT` | `4040` | Telnet server port |
| `PLATO_WEB_PORT` | `8080` | Web UI port |
| `PLATO_TILES_DIR` | `data/tiles` | Tile storage directory |

## Troubleshooting

### Port already in use
```bash
# Find what's using the port
lsof -i :4040
# Use a different port
python3 -m plato --port 9000
```

### Room not loading
- Check YAML syntax: `python3 -c "import yaml; yaml.safe_load(open('templates/your-theme/rooms.yaml'))"`
- Check room_id matches between rooms and exits

### No tiles found
- Tiles are created on first visitor interaction
- Seed tiles load automatically from YAML when room is first visited
- Check `data/tiles/` directory exists

### API calls failing
- Check endpoint URL includes `/chat/completions`
- Check API key is valid
- PLATO works without API keys in tile-only mode

### Tiles not persisting
- Check write permissions on `data/tiles/`
- Check disk space
- `data/tiles/*.json` are gitignored (runtime data, not committed)
