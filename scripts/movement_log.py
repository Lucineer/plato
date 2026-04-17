#!/usr/bin/env python3
"""
PLATO Harbor — Movement Logger

Manual and automated vessel movement logging with timestamp ticks.
Creates tiles in harbor_dock and harbor_log rooms.

Usage:
  python3 scripts/movement_log.py arrive VESSEL-NAME berth-3
  python3 scripts/movement_log.py depart VESSEL-NAME berth-3
  python3 scripts/movement_log.py shift VESSEL-NAME berth-3 berth-5
  python3 scripts/movement_log.py list --position berth-3
  python3 scripts/movement_log.py list --vessel VESSEL-NAME
  python3 scripts/movement_log.py status  # Show all current berths
"""

import argparse, json, os, sys
from datetime import datetime, timezone


TILES_DIR = os.environ.get("PLATO_TILES_DIR", "data/tiles")


def load_tiles(room_id: str) -> list:
    path = os.path.join(TILES_DIR, f"{room_id}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def save_tiles(room_id: str, tiles: list):
    os.makedirs(TILES_DIR, exist_ok=True)
    with open(os.path.join(TILES_DIR, f"{room_id}.json"), "w") as f:
        json.dump(tiles, f, indent=2, default=str)


def add_tile(room_id: str, question: str, answer: str, source: str = "logger",
             tags: list = None) -> str:
    import hashlib
    tiles = load_tiles(room_id)
    tile = {
        "tile_id": hashlib.sha256(f"{room_id}:{question}:{datetime.now().isoformat()}".encode()).hexdigest()[:12],
        "room_id": room_id,
        "question": question,
        "answer": answer,
        "source": source,
        "tags": tags or [],
        "context": f"Movement log entry",
        "score": 0.5,
        "feedback_positive": 0,
        "feedback_negative": 0,
        "created": datetime.now(timezone.utc).isoformat()
    }
    tiles.append(tile)
    save_tiles(room_id, tiles)
    return tile["tile_id"]


def log_movement(movement_type: str, vessel: str, position: str, destination: str = None):
    """Log a vessel movement."""
    timestamp = datetime.now(timezone.utc)
    tick = "✓"

    if movement_type == "arrive":
        action = f"ARRIVED at {position}"
    elif movement_type == "depart":
        action = f"DEPARTED from {position}"
    elif movement_type == "shift":
        action = f"SHIFTED from {position} to {destination}"
    else:
        action = movement_type

    log_entry = (
        f"{tick} {timestamp.strftime('%Y-%m-%d %H:%M UTC')} — "
        f"{vessel} {action}"
    )

    # Add to harbor_log
    tile_id = add_tile(
        "harbor_log",
        f"Movement log entry for {vessel}",
        log_entry,
        tags=["movement", movement_type, vessel.lower(), position]
    )

    # Add to harbor_dock
    add_tile(
        "harbor_dock",
        f"Current status of {vessel}",
        f"{tick} {vessel} — {action} ({timestamp.strftime('%H:%M UTC')})",
        tags=["vessel", vessel.lower(), position, movement_type]
    )

    # Update berth assignment
    if movement_type in ("arrive", "shift"):
        berth_tiles = load_tiles("harbor_berths")
        # Remove any existing assignment for this berth
        berth_tiles = [t for t in berth_tiles if position not in t.get("tags", [])]
        berth_tiles.append({
            "tile_id": f"berth-{position}",
            "room_id": "harbor_berths",
            "question": f"Who is at {position}?",
            "answer": f"{vessel} — assigned {timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
            "source": "logger",
            "tags": ["berth", position, vessel.lower(), "active"],
            "score": 0.5,
            "feedback_positive": 0,
            "feedback_negative": 0,
            "created": timestamp.isoformat()
        })
        save_tiles("harbor_berths", berth_tiles)

    elif movement_type == "depart":
        berth_tiles = load_tiles("harbor_berths")
        berth_tiles = [t for t in berth_tiles if not (
            position in t.get("tags", []) and vessel.lower() in t.get("tags", [])
        )]
        # Add empty berth entry
        berth_tiles.append({
            "tile_id": f"berth-{position}",
            "room_id": "harbor_berths",
            "question": f"Who is at {position}?",
            "answer": f"Empty — {vessel} departed {timestamp.strftime('%H:%M UTC')}",
            "source": "logger",
            "tags": ["berth", position, "empty"],
            "score": 0.5,
            "feedback_positive": 0,
            "feedback_negative": 0,
            "created": timestamp.isoformat()
        })
        save_tiles("harbor_berths", berth_tiles)

    status = "🟢" if movement_type == "arrive" else "🔴" if movement_type == "depart" else "🟡"
    print(f"{status} {log_entry}")
    return tile_id


def list_movements(filters: dict):
    """List movement log entries."""
    tiles = load_tiles("harbor_log")
    results = tiles

    if filters.get("vessel"):
        v = filters["vessel"].lower()
        results = [t for t in results if v in t.get("answer", "").lower()]
    if filters.get("position"):
        p = filters["position"].lower()
        results = [t for t in results if p in t.get("answer", "").lower()]
    if filters.get("limit"):
        results = results[-int(filters["limit"]):]

    if not results:
        print("No movements found.")
        return

    print(f"\n📋 Movement Log ({len(results)} entries):")
    print("─" * 80)
    for t in results:
        print(f"  {t['answer']}")
    print()


def show_status():
    """Show current berth assignments."""
    berth_tiles = load_tiles("harbor_berths")
    dock_tiles = load_tiles("harbor_dock")

    print("\n⚓ Harbor Status")
    print("─" * 80)

    # Show berths
    berths = {}
    for t in berth_tiles:
        if "berth" in t.get("tags", []):
            pos = next((tag for tag in t["tags"] if tag.startswith("berth-")), "unknown")
            if pos != "berth":
                berths[pos] = t["answer"]

    for berth, status in sorted(berths.items()):
        occupied = "empty" not in status.lower()
        icon = "🟢" if occupied else "⚪"
        print(f"  {icon} {berth.replace('berth-', 'Berth ')}: {status}")

    # Recent movements
    recent = dock_tiles[-5:] if dock_tiles else []
    if recent:
        print("\n  Recent:")
        for t in recent:
            print(f"    {t['answer'][:70]}")

    print()


def main():
    parser = argparse.ArgumentParser(description="PLATO Harbor Movement Logger")
    sub = parser.add_subparsers(dest="command")

    # Movement commands
    for mt in ["arrive", "depart", "shift"]:
        p = sub.add_parser(mt, help=f"Log a {mt}")
        p.add_argument("vessel", help="Vessel name")
        p.add_argument("position", help="Berth or dock position")
        if mt == "shift":
            p.add_argument("destination", help="Destination position")

    # List
    list_p = sub.add_parser("list", help="List movements")
    list_p.add_argument("--vessel", help="Filter by vessel name")
    list_p.add_argument("--position", help="Filter by position")
    list_p.add_argument("--limit", type=int, default=20, help="Max entries")

    # Status
    sub.add_parser("status", help="Show current harbor status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        list_movements(vars(args))
    elif args.command == "status":
        show_status()
    else:
        dest = args.destination if hasattr(args, "destination") else None
        log_movement(args.command, args.vessel, args.position, dest)


if __name__ == "__main__":
    main()
