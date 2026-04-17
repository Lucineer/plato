#!/usr/bin/env python3
"""
PLATO — Git-Agent Maintenance Mode
Download. Spin up. Step into the mind of your application.

Usage:
    python -m plato                    # Start server (telnet :4040)
    python -m plato --web              # Start with web UI (:8080)
    python -m plato --setup            # Interactive first-time setup
"""

import sys, os, argparse, json, signal, asyncio

__version__ = "0.1.0"
PLATO_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PLATO_HOME, "data")
TILES_DIR = os.path.join(DATA_DIR, "tiles")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# Ensure data dirs exist
os.makedirs(TILES_DIR, exist_ok=True)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {
        "version": __version__,
        "host": "0.0.0.0",
        "telnet_port": 4040,
        "web_port": 8080,
        "model_endpoint": os.environ.get("PLATO_MODEL_ENDPOINT", ""),
        "model_key": os.environ.get("PLATO_MODEL_KEY", ""),
        "model_name": os.environ.get("PLATO_MODEL_NAME", "deepseek-chat"),
        "tiny_model": os.environ.get("PLATO_TINY_MODEL", ""),
        "rooms_dir": os.path.join(PLATO_HOME, "templates"),
        "tiles_dir": TILES_DIR,
        "visitors": {},
        "rooms": {}
    }

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description="PLATO — Git-Agent Maintenance Mode")
    parser.add_argument("--setup", action="store_true", help="Interactive first-time setup")
    parser.add_argument("--web", action="store_true", help="Start with web UI")
    parser.add_argument("--both", action="store_true", help="Start both telnet + web UI")
    parser.add_argument("--port", type=int, default=None, help="Telnet port")
    parser.add_argument("--web-port", type=int, default=None, help="Web UI port")
    parser.add_argument("--host", default=None, help="Bind host")
    parser.add_argument("--theme", default=None, help="Only load a specific theme")
    args = parser.parse_args()

    if args.setup:
        from plato_core.setup import run_setup
        run_setup()
        return

    config = load_config()
    if args.port:
        config["telnet_port"] = args.port
    if args.web_port:
        config["web_port"] = args.web_port
    if args.host:
        config["host"] = args.host
    if args.theme:
        config["theme_filter"] = args.theme

    # Check if first run (no tiles, no visitors)
    if not os.path.exists(os.path.join(TILES_DIR, "_initialized")):
        print("PLATO v" + __version__)
        print("No PLATO found. Run 'python -m plato --setup' to initialize.")
        print("Or connect via telnet for interactive onboarding.")
        # Create init marker
        with open(os.path.join(TILES_DIR, "_initialized"), "w") as f:
            f.write(str(__import__("time").time()))

    if args.both:
        import threading
        from plato_core.web import run_web
        from plato_core.server import run_server
        web_thread = threading.Thread(target=run_web, args=(config,), daemon=True)
        web_thread.start()
        run_server(config)
    elif args.web:
        from plato_core.web import run_web
        run_web(config)
    else:
        from plato_core.server import run_server
        run_server(config)

if __name__ == "__main__":
    main()
