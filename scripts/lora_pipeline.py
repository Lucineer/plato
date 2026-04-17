#!/usr/bin/env python3
"""
PLATO LoRA Pipeline — Convert tiles to training data for fine-tuning.

Export formats:
  - instruction-input-output: Standard fine-tuning format
  - alpaca: Alpaca-style JSONL
  - conversation: Chat-style conversation format

Usage:
  python3 scripts/lora_pipeline.py export --format instruction-input-output --output training.jsonl
  python3 scripts/lora_pipeline.py export --room harbor_dock --min-score 0.7
  python3 scripts/lora_pipeline.py stats
  python3 scripts/lora_pipeline.py prune --min-score 0.3  # Remove low-quality tiles
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


def get_all_rooms() -> list:
    """Get all room IDs that have tiles."""
    if not os.path.exists(TILES_DIR):
        return []
    rooms = []
    for f in os.listdir(TILES_DIR):
        if f.endswith(".json"):
            rooms.append(f[:-5])  # Remove .json
    return sorted(rooms)


def get_all_tiles(room_id: str = None, min_score: float = 0, min_feedback: int = 0,
                  require_positive: bool = False) -> list:
    """Get tiles with optional filtering."""
    rooms = [room_id] if room_id else get_all_rooms()
    tiles = []
    for rid in rooms:
        for t in load_tiles(rid):
            score = t.get("score", 0.5)
            if score < min_score:
                continue
            if t.get("feedback_positive", 0) < min_feedback:
                continue
            if require_positive and t.get("feedback_positive", 0) == 0:
                continue
            if score <= 0.3:  # Skip known-bad tiles
                continue
            tiles.append(t)
    return tiles


def export_instruction_input_output(tiles: list) -> list:
    """Standard instruction-input-output format."""
    entries = []
    for t in tiles:
        entries.append({
            "instruction": t["question"],
            "input": f"Room: {t.get('room_id', 'unknown')} | Context: {t.get('context', '')}",
            "output": t["answer"]
        })
    return entries


def export_alpaca(tiles: list) -> list:
    """Alpaca-style JSONL format."""
    entries = []
    for t in tiles:
        entries.append({
            "instruction": t["question"],
            "input": "",
            "output": t["answer"]
        })
    return entries


def export_conversation(tiles: list) -> list:
    """Chat-style conversation format for chat fine-tuning."""
    entries = []
    for t in tiles:
        entries.append({
            "messages": [
                {"role": "system", "content": f"You are helpful NPC in room {t.get('room_id', 'PLATO')}."},
                {"role": "user", "content": t["question"]},
                {"role": "assistant", "content": t["answer"]}
            ]
        })
    return entries


def export_raw(tiles: list) -> list:
    """Raw tile data with all metadata."""
    return tiles


FORMATTERS = {
    "instruction-input-output": export_instruction_input_output,
    "alpaca": export_alpaca,
    "conversation": export_conversation,
    "raw": export_raw
}


def cmd_export(args):
    """Export tiles to training format."""
    tiles = get_all_tiles(
        room_id=args.room,
        min_score=args.min_score,
        min_feedback=args.min_feedback,
        require_positive=args.require_positive
    )

    if not tiles:
        print("No tiles matching filters.")
        return

    formatter = FORMATTERS.get(args.format, export_instruction_input_output)
    entries = formatter(tiles)

    # Add system prompt metadata
    output = {
        "metadata": {
            "format": args.format,
            "generated": datetime.now(timezone.utc).isoformat(),
            "source": "PLATO tile export",
            "rooms": list(set(t.get("room_id") for t in tiles)),
            "total_tiles": len(tiles),
            "filters": {
                "min_score": args.min_score,
                "min_feedback": args.min_feedback,
                "require_positive": args.require_positive
            }
        },
        "data": entries
    }

    # Write
    output_path = args.output or f"plato_lora_{args.format}_{datetime.now().strftime('%Y%m%d')}.json"
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    ext = ".jsonl" if args.jsonl else ".json"
    if not output_path.endswith(ext):
        output_path += ext

    with open(output_path, "w") as f:
        if args.jsonl:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        else:
            json.dump(output, f, indent=2, default=str)

    print(f"✅ Exported {len(entries)} tiles → {output_path}")
    print(f"   Format: {args.format}")
    print(f"   Rooms: {len(set(t.get('room_id') for t in tiles))}")
    print(f"   Filters: score>={args.min_score}, feedback>={args.min_feedback}")


def cmd_stats(args):
    """Show tile statistics across all rooms."""
    rooms = get_all_rooms()
    if not rooms:
        print("No rooms with tiles found.")
        return

    total_tiles = 0
    total_positive = 0
    total_negative = 0
    high_quality = 0
    low_quality = 0

    print("\n📊 PLATO Tile Statistics")
    print("─" * 80)
    print(f"{'Room':<25} {'Tiles':>6} {'👍':>5} {'👎':>5} {'Avg Score':>10}")
    print("─" * 80)

    for rid in rooms:
        tiles = load_tiles(rid)
        n = len(tiles)
        pos = sum(t.get("feedback_positive", 0) for t in tiles)
        neg = sum(t.get("feedback_negative", 0) for t in tiles)
        avg = sum(t.get("score", 0.5) for t in tiles) / n if n > 0 else 0

        total_tiles += n
        total_positive += pos
        total_negative += neg
        high_quality += sum(1 for t in tiles if t.get("score", 0.5) >= 0.7)
        low_quality += sum(1 for t in tiles if t.get("score", 0.5) <= 0.3)

        print(f"{rid:<25} {n:>6} {pos:>5} {neg:>5} {avg:>10.2f}")

    print("─" * 80)
    print(f"{'TOTAL':<25} {total_tiles:>6} {total_positive:>5} {total_negative:>5}")
    print()
    print(f"  🟢 High quality (score >= 0.7): {high_quality}")
    print(f"  🟡 Medium quality: {total_tiles - high_quality - low_quality}")
    print(f"  🔴 Low quality (score <= 0.3): {low_quality}")
    print(f"  📈 Ready for LoRA (score >= 0.5): {total_tiles - low_quality}")
    print()


def cmd_prune(args):
    """Remove low-quality tiles."""
    rooms = get_all_rooms()
    removed = 0

    for rid in rooms:
        tiles = load_tiles(rid)
        original = len(tiles)
        tiles = [t for t in tiles if t.get("score", 0.5) > args.min_score]
        removed += original - len(tiles)
        if original != len(tiles):
            save_tiles(rid, tiles)
            print(f"  {rid}: {original} → {len(tiles)} (removed {original - len(tiles)})")

    print(f"\n✅ Pruned {removed} tiles with score <= {args.min_score}")


def cmd_merge(args):
    """Merge tiles from multiple PLATO instances."""
    merged = 0
    for source_dir in args.sources:
        if not os.path.exists(source_dir):
            print(f"  ❌ Not found: {source_dir}")
            continue
        for f in os.listdir(source_dir):
            if not f.endswith(".json"):
                continue
            room_id = f[:-5]
            source_tiles = []
            with open(os.path.join(source_dir, f)) as fh:
                source_tiles = json.load(fh)

            existing = load_tiles(room_id)
            existing_ids = {t["tile_id"] for t in existing}
            new_tiles = [t for t in source_tiles if t["tile_id"] not in existing_ids]

            if new_tiles:
                existing.extend(new_tiles)
                save_tiles(room_id, existing)
                merged += len(new_tiles)
                print(f"  {room_id}: +{len(new_tiles)} tiles from {source_dir}")

    print(f"\n✅ Merged {merged} new tiles")


def main():
    parser = argparse.ArgumentParser(description="PLATO LoRA Pipeline")
    sub = parser.add_subparsers(dest="command")

    # Export
    exp = sub.add_parser("export", help="Export tiles to training format")
    exp.add_argument("--format", default="instruction-input-output",
                     choices=list(FORMATTERS.keys()), help="Output format")
    exp.add_argument("--room", default=None, help="Export specific room only")
    exp.add_argument("--min-score", type=float, default=0.3, help="Minimum tile score")
    exp.add_argument("--min-feedback", type=int, default=0, help="Minimum feedback count")
    exp.add_argument("--require-positive", action="store_true", help="Only tiles with positive feedback")
    exp.add_argument("--output", "-o", default=None, help="Output file path")
    exp.add_argument("--jsonl", action="store_true", help="Output as JSONL instead of JSON")

    # Stats
    sub.add_parser("stats", help="Show tile statistics")

    # Prune
    prune = sub.add_parser("prune", help="Remove low-quality tiles")
    prune.add_argument("--min-score", type=float, default=0.3, help="Remove tiles with score at or below this")

    # Merge
    merge = sub.add_parser("merge", help="Merge tiles from multiple PLATO instances")
    merge.add_argument("sources", nargs="+", help="Source tiles directories")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {"export": cmd_export, "stats": cmd_stats, "prune": cmd_prune, "merge": cmd_merge}
    commands[args.command](args)


if __name__ == "__main__":
    main()
