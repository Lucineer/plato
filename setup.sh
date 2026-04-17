#!/usr/bin/env bash
# PLATO Setup — Interactive first-time configuration
set -e

echo "╔══════════════════════════════════════════╗"
echo "║       P L A T O  Setup Wizard            ║"
echo "║    Git-Agent Maintenance Mode             ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 required. Install it first."
    exit 1
fi

# Check for pyyaml
echo "Checking dependencies..."
python3 -c "import yaml" 2>/dev/null || {
    echo "Installing pyyaml..."
    pip3 install pyyaml
}

# Create data directory
mkdir -p data/tiles

# Ask about model endpoint
echo ""
echo "🔧 Model Configuration"
echo "PLATO works in two modes:"
echo "  1. Tile-only mode (no API needed) — NPC pattern-matches against tiles"
echo "  2. Full mode (API endpoint) — NPC uses tiny/mid-tier models for synthesis"
echo ""
read -p "Do you have an LLM API endpoint? (y/n) [n]: " has_api
has_api=${has_api:-n}

if [ "$has_api" = "y" ]; then
    read -p "API endpoint (e.g., https://api.deepseek.com/v1/chat/completions): " endpoint
    read -p "API key: " api_key
    read -p "Model name (e.g., deepseek-chat): " model_name
    read -p "Tiny model name for NPC layer (optional): " tiny_model
else
    endpoint=""
    api_key=""
    model_name=""
    tiny_model=""
    echo "Tile-only mode selected. NPCs will use pattern matching only."
fi

read -p "Telnet port [4040]: " port
port=${port:-4040}

# Write config
cat > data/config.json << EOF
{
    "version": "0.1.0",
    "host": "0.0.0.0",
    "telnet_port": $port,
    "web_port": 8080,
    "model_endpoint": "$endpoint",
    "model_key": "$api_key",
    "model_name": "$model_name",
    "tiny_model": "$tiny_model",
    "rooms_dir": "templates",
    "tiles_dir": "data/tiles",
    "visitors": {},
    "rooms": {}
}
EOF

echo ""
echo "✅ PLATO configured!"
echo ""
echo "Room templates loaded:"
for theme_dir in templates/*/; do
    theme=$(basename "$theme_dir")
    count=$(grep -c "room_id:" "$theme_dir/rooms.yaml" 2>/dev/null || echo 0)
    echo "  📁 $theme ($count rooms)"
done

echo ""
echo "🚀 Start PLATO:"
echo "   python3 -m plato"
echo ""
echo "Then connect:"
echo "   telnet localhost $port"
echo ""
echo "Or for interactive onboarding:"
echo "   python3 -m plato --setup"
